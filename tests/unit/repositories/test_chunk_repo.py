import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient
from pymongo.errors import OperationFailure

from app.repositories.chunk_repo import ChunkRepository


@pytest.fixture
def chunk_repo() -> ChunkRepository:
    client = AsyncMongoMockClient()
    db = client["agent_server_test"]
    return ChunkRepository(collection=db["chunks"])


@pytest.mark.asyncio
async def test_delete_by_file_removes_only_target_file_chunks(
    chunk_repo: ChunkRepository,
) -> None:
    await chunk_repo.insert_many(
        [
            {
                "file_id": "file-a",
                "session_id": "s1",
                "user_id": "u1",
                "content": "a",
                "chunk_index": 0,
                "embedding": [0.1, 0.2],
            },
            {
                "file_id": "file-a",
                "session_id": "s1",
                "user_id": "u1",
                "content": "b",
                "chunk_index": 1,
                "embedding": [0.2, 0.3],
            },
            {
                "file_id": "file-b",
                "session_id": "s1",
                "user_id": "u1",
                "content": "c",
                "chunk_index": 0,
                "embedding": [0.3, 0.4],
            },
        ]
    )

    deleted = await chunk_repo.delete_by_file("file-a")
    remaining = await chunk_repo.count_by_session("s1")

    assert deleted == 2
    assert remaining == 1


@pytest.mark.asyncio
async def test_count_by_session_returns_zero_when_empty(
    chunk_repo: ChunkRepository,
) -> None:
    count = await chunk_repo.count_by_session("missing-session")
    assert count == 0


class _AsyncCursor:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def __aiter__(self) -> "_AsyncCursor":
        return self

    async def __anext__(self) -> dict:
        if not self._rows:
            raise StopAsyncIteration
        return self._rows.pop(0)


@pytest.mark.asyncio
async def test_vector_search_retries_when_mongot_temporarily_unavailable(
    chunk_repo: ChunkRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    async def _no_sleep(_: float) -> None:
        return None

    def _aggregate(_: list[dict]) -> _AsyncCursor:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OperationFailure(
                "HostUnreachable: Error connecting to localhost:27027 "
                ":: caused by :: Connection refused",
                code=6,
            )
        return _AsyncCursor(
            [
                {
                    "_id": ObjectId(),
                    "file_id": "f1",
                    "session_id": "s1",
                    "content": "chunk",
                    "score": 0.99,
                }
            ]
        )

    monkeypatch.setattr(chunk_repo._col, "aggregate", _aggregate)
    monkeypatch.setattr("app.repositories.chunk_repo.asyncio.sleep", _no_sleep)

    rows = await chunk_repo.vector_search([0.1, 0.2], "s1")

    assert calls["count"] == 2
    assert len(rows) == 1
    assert rows[0]["id"] != ""


@pytest.mark.asyncio
async def test_vector_search_falls_back_to_local_similarity_after_retry_limit(
    chunk_repo: ChunkRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_sleep(_: float) -> None:
        return None

    def _aggregate(_: list[dict]) -> _AsyncCursor:
        raise OperationFailure(
            "HostUnreachable: Error connecting to localhost:27027 "
            ":: caused by :: Connection refused",
            code=6,
        )

    monkeypatch.setattr(chunk_repo._col, "aggregate", _aggregate)
    monkeypatch.setattr("app.repositories.chunk_repo.asyncio.sleep", _no_sleep)

    await chunk_repo.insert_many(
        [
            {
                "file_id": "file-local",
                "session_id": "s1",
                "user_id": "u1",
                "content": "fallback chunk",
                "chunk_index": 0,
                "embedding": [0.1, 0.2],
            }
        ]
    )

    rows = await chunk_repo.vector_search([0.1, 0.2], "s1")

    assert len(rows) == 1
    assert rows[0]["content"] == "fallback chunk"
