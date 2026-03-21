from fastapi import Depends
from supabase import AsyncClient, create_async_client

from app.config import settings
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService
from app.services.session_service import SessionService


async def get_supabase_client() -> AsyncClient:
    """Create a Supabase async client for request-scoped dependencies."""
    return await create_async_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )


async def get_session_repository(
    db: AsyncClient = Depends(get_supabase_client),  # noqa: B008
) -> SessionRepository:
    """Build session repository dependency."""
    return SessionRepository(client=db)


async def get_message_repository(
    db: AsyncClient = Depends(get_supabase_client),  # noqa: B008
) -> MessageRepository:
    """Build message repository dependency."""
    return MessageRepository(client=db)


async def get_user_repository(
    db: AsyncClient = Depends(get_supabase_client),  # noqa: B008
) -> UserRepository:
    """Build user repository dependency."""
    return UserRepository(client=db)


async def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),  # noqa: B008
) -> AuthService:
    """Build auth service dependency."""
    return AuthService(user_repo=user_repo)


async def get_session_service(
    session_repo: SessionRepository = Depends(get_session_repository),  # noqa: B008
    message_repo: MessageRepository = Depends(get_message_repository),  # noqa: B008
) -> SessionService:
    """Build session service dependency."""
    return SessionService(session_repo=session_repo, message_repo=message_repo)
