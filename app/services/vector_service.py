from typing import Any, Protocol

from app.repositories.chunk_repo import ChunkRepository


class QueryEmbedder(Protocol):
    """Protocol for embedding a single query string."""

    async def aembed_query(self, text: str) -> list[float]:
        """Return embedding vector for query text."""


class VectorService:
    """Service layer for embedding and vector retrieval."""

    def __init__(self, chunk_repo: ChunkRepository, embedder: QueryEmbedder) -> None:
        self._chunk_repo = chunk_repo
        self._embedder = embedder

    async def similarity_search(
        self,
        query: str,
        session_id: str,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Embed query text then run vector search in chunk repository."""
        embedding = await self._embedder.aembed_query(query)
        return await self._chunk_repo.vector_search(
            embedding,
            session_id,
            top_k,
            threshold,
        )

    async def has_context(self, session_id: str) -> bool:
        """Return True when at least one chunk exists in the session."""
        return (await self._chunk_repo.count_by_session(session_id)) > 0
