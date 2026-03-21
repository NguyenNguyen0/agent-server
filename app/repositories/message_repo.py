from typing import Any, cast

from supabase import AsyncClient

from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository[dict[str, Any]]):
    """Repository for chat messages."""

    def __init__(self, client: AsyncClient) -> None:
        super().__init__(client, "messages")

    async def find_by_session(self, session_id: str) -> list[dict[str, Any]]:
        """Return all messages in chronological order."""
        result = await (
            self._client.table(self._table)
            .select("*")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        if result is None or result.data is None:
            return []
        return cast(list[dict[str, Any]], result.data)

    async def create_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a message row for a session."""
        payload: dict[str, Any] = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "tool_calls": tool_calls,
        }
        result = await self._client.table(self._table).insert(payload).execute()
        rows = cast(list[dict[str, Any]], result.data)
        return rows[0]
