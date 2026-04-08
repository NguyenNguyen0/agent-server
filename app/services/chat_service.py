import inspect
import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_groq import ChatGroq

from app.agents.chatbot_agent import ChatbotAgent
from app.agents.rag_agent import RagAgent
from app.agents.tool_agent import ToolAgent
from app.models.chat import ChatInput, ChatRequest, ChatResponse
from app.repositories.message_repo import MessageRepository
from app.services.mcp_service import MCPClient, MCPService
from app.services.session_service import SessionService
from app.services.vector_service import VectorService
from app.tools.mcp_tool import create_mcp_tool


class ChatService:
    """Business logic for chat invocation and streaming."""

    def __init__(
        self,
        session_service: SessionService,
        message_repo: MessageRepository,
        chatbot_agent: ChatbotAgent,
        rag_agent: RagAgent,
        vector_service: VectorService,
        mcp_service: MCPService | None = None,
        llm: ChatGroq | None = None,
    ) -> None:
        self._session_service = session_service
        self._message_repo = message_repo
        self._chatbot_agent = chatbot_agent
        self._rag_agent = rag_agent
        self._vector_service = vector_service
        self._mcp_service = mcp_service
        self._llm = llm

    async def _build_tool_agent(
        self, user_id: str, mcp_server_ids: list[str]
    ) -> ToolAgent | None:
        """Build a ToolAgent from the requested MCP server ids."""
        if not self._mcp_service or not self._llm or not mcp_server_ids:
            return None
        tool_infos = await self._mcp_service.get_tools_for_servers(
            user_id, mcp_server_ids
        )
        if not tool_infos:
            return None
        # Build one MCPClient per unique server URL to avoid redundant connections.
        clients: dict[str, MCPClient] = {}
        tools = []
        for info in tool_infos:
            server_url = info["server_url"]
            if server_url not in clients:
                clients[server_url] = MCPClient(
                    url=server_url, headers=info.get("server_headers", {})
                )
            tools.append(create_mcp_tool(info, call_tool=clients[server_url].call_tool))
        return ToolAgent(llm=self._llm, tools=tools)

    async def _select_agent(
        self,
        user_id: str,
        session_id: str,
        mcp_server_ids: list[str],
    ) -> ChatbotAgent | RagAgent | ToolAgent:
        """
        Agent selection priority:
        1. MCP server ids provided → ToolAgent
        2. Session has file context → RagAgent
        3. Fallback → ChatbotAgent
        """
        if mcp_server_ids:
            tool_agent = await self._build_tool_agent(user_id, mcp_server_ids)
            if tool_agent:
                return tool_agent

        has_context = await self._vector_service.has_context(session_id)
        return self._rag_agent if has_context else self._chatbot_agent

    def _to_langchain_history(self, rows: list[dict[str, Any]]) -> list[BaseMessage]:
        """Convert persisted message rows into LangChain message objects."""
        history: list[BaseMessage] = []
        for row in rows:
            role = str(row.get("role", ""))
            content = str(row.get("content", ""))
            if role == "assistant":
                history.append(AIMessage(content=content))
            else:
                history.append(HumanMessage(content=content))
        return history

    async def chat(
        self,
        user_id: str,
        session_id: str,
        request: ChatRequest,
    ) -> ChatResponse:
        """Run one full chat turn and persist both user and assistant messages."""
        await self._session_service.get_session(user_id, session_id)

        rows = await self._message_repo.find_by_session(session_id)
        history = self._to_langchain_history(rows)
        agent = await self._select_agent(user_id, session_id, request.mcp_server_ids)

        await self._message_repo.create_message(
            session_id,
            "user",
            request.message,
            tool_calls=None,
        )
        output = await agent.ainvoke(
            ChatInput(message=request.message, session_id=session_id, history=history)
        )
        assistant = await self._message_repo.create_message(
            session_id,
            "assistant",
            output.content,
            tool_calls=None,
        )

        return ChatResponse(
            content=output.content,
            session_id=session_id,
            message_id=str(assistant["id"]),
        )

    async def stream_chat(
        self,
        user_id: str,
        session_id: str,
        request: ChatRequest,
    ) -> AsyncIterator[str]:
        """Stream chat response in SSE format and persist final assistant text."""
        await self._session_service.get_session(user_id, session_id)

        rows = await self._message_repo.find_by_session(session_id)
        history = self._to_langchain_history(rows)
        agent = await self._select_agent(user_id, session_id, request.mcp_server_ids)

        await self._message_repo.create_message(
            session_id,
            "user",
            request.message,
            tool_calls=None,
        )

        chunks: list[str] = []
        stream = agent.astream(
            ChatInput(message=request.message, session_id=session_id, history=history)
        )
        if inspect.isawaitable(stream):
            stream = await stream
        async for token in stream:  # ty:ignore[not-iterable]
            chunks.append(token)
            yield f"data: {json.dumps({'token': token})}\n\n"

        full_response = "".join(chunks)
        await self._message_repo.create_message(
            session_id,
            "assistant",
            full_response,
            tool_calls=None,
        )
        yield "data: [DONE]\n\n"
