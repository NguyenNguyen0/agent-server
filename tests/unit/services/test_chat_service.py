from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from app.models.chat import ChatOutput, ChatRequest
from app.services.chat_service import ChatService


async def _iter_tokens(tokens: list[str]) -> AsyncIterator[str]:
    for token in tokens:
        yield token


@pytest.mark.asyncio
async def test_chat_verifies_ownership_before_agent_call() -> None:
    session_service = AsyncMock()
    message_repo = AsyncMock()
    message_repo.find_by_session.return_value = []
    message_repo.create_message.side_effect = [{"id": "m-user"}, {"id": "m-assistant"}]

    chatbot_agent = AsyncMock()
    chatbot_agent.ainvoke.return_value = ChatOutput(
        content="reply",
        session_id="session-1",
        message_id="",
        agent_type="chatbot",
    )

    service = ChatService(
        session_service=session_service,
        message_repo=message_repo,
        chatbot_agent=chatbot_agent,
        rag_agent=AsyncMock(),
        vector_service=AsyncMock(has_context=AsyncMock(return_value=False)),
    )

    response = await service.chat(
        user_id="user-1",
        session_id="session-1",
        request=ChatRequest(message="hello"),
    )

    assert response.content == "reply"
    session_service.get_session.assert_awaited_once_with("user-1", "session-1")
    chatbot_agent.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_saves_user_and_assistant_messages() -> None:
    session_service = AsyncMock()
    message_repo = AsyncMock()
    message_repo.find_by_session.return_value = []
    message_repo.create_message.side_effect = [{"id": "m-user"}, {"id": "m-assistant"}]

    chatbot_agent = AsyncMock()
    chatbot_agent.ainvoke.return_value = ChatOutput(
        content="assistant output",
        session_id="session-1",
        message_id="",
        agent_type="chatbot",
    )

    service = ChatService(
        session_service=session_service,
        message_repo=message_repo,
        chatbot_agent=chatbot_agent,
        rag_agent=AsyncMock(),
        vector_service=AsyncMock(has_context=AsyncMock(return_value=False)),
    )

    response = await service.chat(
        user_id="user-1",
        session_id="session-1",
        request=ChatRequest(message="hello"),
    )

    assert response.message_id == "m-assistant"
    assert message_repo.create_message.await_count == 2


@pytest.mark.asyncio
async def test_stream_chat_yields_sse_and_persists_full_response() -> None:
    session_service = AsyncMock()
    message_repo = AsyncMock()
    message_repo.find_by_session.return_value = []
    message_repo.create_message.side_effect = [{"id": "m-user"}, {"id": "m-assistant"}]

    chatbot_agent = AsyncMock()
    chatbot_agent.astream.return_value = _iter_tokens(["Hel", "lo"])

    service = ChatService(
        session_service=session_service,
        message_repo=message_repo,
        chatbot_agent=chatbot_agent,
        rag_agent=AsyncMock(),
        vector_service=AsyncMock(has_context=AsyncMock(return_value=False)),
    )

    chunks = [
        chunk
        async for chunk in service.stream_chat(
            user_id="user-1",
            session_id="session-1",
            request=ChatRequest(message="hello"),
        )
    ]

    assert chunks[0] == 'data: {"token": "Hel"}\n\n'
    assert chunks[1] == 'data: {"token": "lo"}\n\n'
    assert chunks[2] == "data: [DONE]\n\n"
    message_repo.create_message.assert_any_await(
        "session-1",
        "assistant",
        "Hello",
        tool_calls=None,
    )


@pytest.mark.asyncio
async def test_chat_uses_rag_agent_when_context_exists() -> None:
    session_service = AsyncMock()
    message_repo = AsyncMock()
    message_repo.find_by_session.return_value = []
    message_repo.create_message.side_effect = [{"id": "m-user"}, {"id": "m-assistant"}]

    chatbot_agent = AsyncMock()
    rag_agent = AsyncMock()
    rag_agent.ainvoke.return_value = ChatOutput(
        content="rag reply",
        session_id="session-1",
        message_id="",
        agent_type="rag",
    )
    vector_service = AsyncMock()
    vector_service.has_context.return_value = True

    service = ChatService(
        session_service=session_service,
        message_repo=message_repo,
        chatbot_agent=chatbot_agent,
        rag_agent=rag_agent,
        vector_service=vector_service,
    )

    response = await service.chat(
        user_id="user-1",
        session_id="session-1",
        request=ChatRequest(message="hello"),
    )

    assert response.content == "rag reply"
    rag_agent.ainvoke.assert_awaited_once()
    chatbot_agent.ainvoke.assert_not_called()
