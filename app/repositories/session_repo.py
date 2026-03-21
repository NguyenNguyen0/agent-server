from typing import Any, cast

from supabase import AsyncClient

from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[dict[str, Any]]):
    """Repository for session persistence and ownership checks."""

    def __init__(self, client: AsyncClient) -> None:
        super().__init__(client, "sessions")

    async def find_by_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return all sessions owned by a user."""
        result = await (
            self._client.table(self._table)
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        if result is None or result.data is None:
            return []
        return cast(list[dict[str, Any]], result.data)

    async def find_by_user_and_id(
        self,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Return one session only when it belongs to the user."""
        result = await (
            self._client.table(self._table)
            .select("*")
            .eq("user_id", user_id)
            .eq("id", session_id)
            .maybe_single()
            .execute()
        )
        if result is None:
            return None
        return cast(dict[str, Any] | None, result.data)
