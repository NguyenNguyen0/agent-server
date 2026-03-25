import asyncio
import math
from typing import Any, cast

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.errors import OperationFailure

from app.db.mongo import to_str_id
from app.repositories.base import BaseRepository

MAX_VECTOR_SEARCH_RETRIES = 5
VECTOR_SEARCH_RETRY_DELAY_SECONDS = 1.0


class ChunkRepository(BaseRepository[dict[str, Any]]):
    """Repository for text chunks and vector embeddings."""

    def __init__(self, collection: AsyncIOMotorCollection[dict[str, Any]]) -> None:
        super().__init__(collection)

    async def insert_many(self, rows: list[dict[str, Any]]) -> int:
        """Insert multiple chunks and return inserted count."""
        if not rows:
            return 0
        result = await self._col.insert_many(rows)
        return len(result.inserted_ids)

    async def vector_search(
        self,
        embedding: list[float],
        session_id: str,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Run Atlas vector search and return chunks above threshold."""
        pipeline: list[dict[str, Any]] = [
            {
                "$vectorSearch": {
                    "index": "chunk_embedding_index",
                    "path": "embedding",
                    "queryVector": embedding,
                    "numCandidates": top_k * 10,
                    "limit": top_k,
                    "filter": {"session_id": session_id},
                }
            },
            {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
            {"$match": {"score": {"$gte": threshold}}},
            {"$project": {"embedding": 0}},
        ]
        for attempt in range(MAX_VECTOR_SEARCH_RETRIES):
            try:
                cursor = self._col.aggregate(pipeline)
                rows = [to_str_id(doc) async for doc in cursor]
                return cast(list[dict[str, Any]], rows)
            except OperationFailure as exc:
                if not self._is_transient_mongot_startup_error(exc):
                    raise
                if attempt == MAX_VECTOR_SEARCH_RETRIES - 1:
                    return await self._local_vector_search(
                        embedding,
                        session_id,
                        top_k,
                        threshold,
                    )
                await asyncio.sleep(VECTOR_SEARCH_RETRY_DELAY_SECONDS)

        return []

    async def _local_vector_search(
        self,
        query_embedding: list[float],
        session_id: str,
        top_k: int,
        threshold: float,
    ) -> list[dict[str, Any]]:
        """Fallback search by computing cosine similarity in Python."""
        cursor = self._col.find({"session_id": session_id})
        scored: list[dict[str, Any]] = []

        async for row in cursor:
            raw_embedding = row.get("embedding")
            if not isinstance(raw_embedding, list):
                continue
            if not raw_embedding:
                continue

            score = self._cosine_similarity(query_embedding, raw_embedding)
            if score < threshold:
                continue

            row["score"] = score
            row.pop("embedding", None)
            serialized = to_str_id(row)
            if serialized is not None:
                scored.append(serialized)

        scored.sort(key=lambda item: cast(float, item.get("score", 0.0)), reverse=True)
        return scored[:top_k]

    @staticmethod
    def _cosine_similarity(query: list[float], candidate: list[Any]) -> float:
        """Compute cosine similarity for two vectors."""
        if len(query) != len(candidate):
            return -1.0

        query_norm = math.sqrt(sum(value * value for value in query))
        candidate_values = [float(value) for value in candidate]
        candidate_norm = math.sqrt(sum(value * value for value in candidate_values))

        if query_norm == 0 or candidate_norm == 0:
            return -1.0

        dot = sum(q * c for q, c in zip(query, candidate_values, strict=False))
        return dot / (query_norm * candidate_norm)

    @staticmethod
    def _is_transient_mongot_startup_error(exc: OperationFailure) -> bool:
        """Return True for temporary Atlas Local mongot startup/connectivity errors."""
        message = str(exc).lower()
        is_host_unreachable = exc.code == 6 or "hostunreachable" in message
        return (
            is_host_unreachable
            and "27027" in message
            and ("connection refused" in message or "localhost" in message)
        )

    async def count_by_session(self, session_id: str) -> int:
        """Count chunks by session id."""
        return int(await self._col.count_documents({"session_id": session_id}))

    async def delete_by_file(self, file_id: str) -> int:
        """Delete all chunks for a file id and return deleted count."""
        result = await self._col.delete_many({"file_id": file_id})
        return int(result.deleted_count)
