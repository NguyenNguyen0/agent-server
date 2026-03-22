import inspect
import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agents.chatbot_agent import ChatbotAgent
from app.models.chat import ChatInput, ChatRequest, ChatResponse
from app.repositories.message_repo import MessageRepository
from app.services.session_service import SessionService


class ChatService:
    """Business logic for chat invocation and streaming."""

    def __init__(
        self,
        session_service: SessionService,
        message_repo: MessageRepository,
        chatbot_agent: ChatbotAgent,
    ) -> None:
        self._session_service = session_service
        self._message_repo = message_repo
        self._chatbot_agent = chatbot_agent

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

        await self._message_repo.create_message(
            session_id,
            "user",
            request.message,
            tool_calls=None,
        )
        output = await self._chatbot_agent.ainvoke(
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

        await self._message_repo.create_message(
            session_id,
            "user",
            request.message,
            tool_calls=None,
        )

        chunks: list[str] = []
        stream = self._chatbot_agent.astream(
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
