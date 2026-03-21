from typing import Any, TypeVar, cast

from supabase import AsyncClient

T = TypeVar("T")


class BaseRepository[T]:
    """Shared CRUD primitives for Supabase repositories."""

    def __init__(self, client: AsyncClient, table_name: str) -> None:
        self._client = client
        self._table = table_name

    async def find_by_id(self, item_id: str) -> T | None:
        """Fetch a single row by id."""
        result = await (
            self._client.table(self._table)
            .select("*")
            .eq("id", item_id)
            .maybe_single()
            .execute()
        )
        if result is None:
            return None
        return cast(T | None, result.data)

    async def create(self, data: dict[str, Any]) -> T:
        """Insert one row and return it."""
        result = await self._client.table(self._table).insert(data).execute()
        rows = cast(list[T], result.data)
        return rows[0]

    async def delete(self, item_id: str) -> None:
        """Delete one row by id."""
        await self._client.table(self._table).delete().eq("id", item_id).execute()
