from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.session_repo import SessionRepository


@pytest.fixture
def session_repo_with_mocks() -> tuple[SessionRepository, MagicMock, MagicMock]:
    client = MagicMock()
    query = MagicMock()

    client.table.return_value = query
    query.select.return_value = query
    query.eq.return_value = query
    query.order.return_value = query
    query.maybe_single.return_value = query
    query.execute = AsyncMock(return_value=SimpleNamespace(data=[]))

    repo = SessionRepository(client=client)
    return repo, client, query


@pytest.mark.asyncio
async def test_find_by_user_returns_rows(
    session_repo_with_mocks: tuple[SessionRepository, MagicMock, MagicMock],
) -> None:
    repo, _, query = session_repo_with_mocks
    query.execute.return_value = SimpleNamespace(data=[{"id": "s1"}])

    result = await repo.find_by_user("user-1")

    assert result == [{"id": "s1"}]
    query.eq.assert_called_with("user_id", "user-1")


@pytest.mark.asyncio
async def test_find_by_user_and_id_returns_none_when_not_found(
    session_repo_with_mocks: tuple[SessionRepository, MagicMock, MagicMock],
) -> None:
    repo, _, query = session_repo_with_mocks
    query.execute.return_value = SimpleNamespace(data=None)

    result = await repo.find_by_user_and_id("user-1", "session-1")

    assert result is None
    assert query.eq.call_count == 2
