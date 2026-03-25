from unittest.mock import AsyncMock

import pytest

from app.services.vector_service import VectorService


@pytest.mark.asyncio
async def test_similarity_search_embeds_query_then_calls_repository() -> None:
    chunk_repo = AsyncMock()
    chunk_repo.vector_search.return_value = [{"content": "doc", "score": 0.9}]

    embedder = AsyncMock()
    embedder.aembed_query.return_value = [0.1, 0.2, 0.3]

    service = VectorService(chunk_repo=chunk_repo, embedder=embedder)

    result = await service.similarity_search(
        query="What is LangGraph?",
        session_id="s1",
        top_k=3,
        threshold=0.6,
    )

    assert result == [{"content": "doc", "score": 0.9}]
    embedder.aembed_query.assert_awaited_once_with("What is LangGraph?")
    chunk_repo.vector_search.assert_awaited_once_with([0.1, 0.2, 0.3], "s1", 3, 0.6)


@pytest.mark.asyncio
async def test_has_context_returns_true_when_count_above_zero() -> None:
    chunk_repo = AsyncMock()
    chunk_repo.count_by_session.return_value = 2

    service = VectorService(chunk_repo=chunk_repo, embedder=AsyncMock())

    assert await service.has_context("s1") is True


@pytest.mark.asyncio
async def test_has_context_returns_false_when_count_is_zero() -> None:
    chunk_repo = AsyncMock()
    chunk_repo.count_by_session.return_value = 0

    service = VectorService(chunk_repo=chunk_repo, embedder=AsyncMock())

    assert await service.has_context("s1") is False
