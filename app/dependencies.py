from supabase import AsyncClient, create_async_client

from app.config import settings


async def get_supabase_client() -> AsyncClient:
    """Create a Supabase async client for request-scoped dependencies."""
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
