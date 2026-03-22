from typing import Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.chatbot_agent import ChatbotAgent
from app.db.mongo import get_db
from app.repositories.message_repo import MessageRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.session_service import SessionService
from app.utils.llm import get_llm


def get_database() -> AsyncIOMotorDatabase[dict[str, Any]]:
    """Provide MongoDB database dependency."""
    return get_db()


def get_session_repository(
    db: AsyncIOMotorDatabase[dict[str, Any]] = Depends(get_database),  # noqa: B008
) -> SessionRepository:
    """Build session repository dependency."""
    return SessionRepository(collection=db["sessions"])


def get_message_repository(
    db: AsyncIOMotorDatabase[dict[str, Any]] = Depends(get_database),  # noqa: B008
) -> MessageRepository:
    """Build message repository dependency."""
    return MessageRepository(collection=db["messages"])


def get_user_repository(
    db: AsyncIOMotorDatabase[dict[str, Any]] = Depends(get_database),  # noqa: B008
) -> UserRepository:
    """Build user repository dependency."""
    return UserRepository(collection=db["users"])


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),  # noqa: B008
) -> AuthService:
    """Build auth service dependency."""
    return AuthService(user_repo=user_repo)


def get_chatbot_agent() -> ChatbotAgent:
    """Build chatbot agent dependency."""
    return ChatbotAgent(llm=get_llm(streaming=True))


def get_session_service(
    session_repo: SessionRepository = Depends(get_session_repository),  # noqa: B008
    message_repo: MessageRepository = Depends(get_message_repository),  # noqa: B008
) -> SessionService:
    """Build session service dependency."""
    return SessionService(session_repo=session_repo, message_repo=message_repo)


def get_chat_service(
    session_service: SessionService = Depends(get_session_service),  # noqa: B008
    message_repo: MessageRepository = Depends(get_message_repository),  # noqa: B008
    chatbot_agent: ChatbotAgent = Depends(get_chatbot_agent),  # noqa: B008
) -> ChatService:
    """Build chat service dependency."""
    return ChatService(
        session_service=session_service,
        message_repo=message_repo,
        chatbot_agent=chatbot_agent,
    )
