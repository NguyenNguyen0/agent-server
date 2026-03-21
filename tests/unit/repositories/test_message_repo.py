from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.message_repo import MessageRepository


@pytest.fixture
def message_repo_with_mocks() -> tuple[MessageRepository, MagicMock, MagicMock]:
    client = MagicMock()
    query = MagicMock()

    client.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.insert.return_value = query
    query.execute = AsyncMock(return_value=SimpleNamespace(data=[]))

    repo = MessageRepository(client=client)
    return repo, client, query


@pytest.mark.asyncio
async def test_find_by_session_returns_rows_sorted(
    message_repo_with_mocks: tuple[MessageRepository, MagicMock, MagicMock],
) -> None:
    repo, _, query = message_repo_with_mocks
    query.execute.return_value = SimpleNamespace(data=[{"id": "m1"}])

    result = await repo.find_by_session("session-1")

    assert result == [{"id": "m1"}]
    query.eq.assert_called_with("session_id", "session-1")
    query.order.assert_called_with("created_at")


@pytest.mark.asyncio
async def test_create_message_returns_inserted_row(
    message_repo_with_mocks: tuple[MessageRepository, MagicMock, MagicMock],
) -> None:
    repo, _, query = message_repo_with_mocks
    query.execute.return_value = SimpleNamespace(data=[{"id": "m1"}])

    result = await repo.create_message(
        session_id="session-1",
        role="user",
        content="hello",
    )

    assert result["id"] == "m1"
    query.insert.assert_called_once()
