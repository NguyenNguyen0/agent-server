from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.dependencies import get_chat_service
from app.middleware.auth import get_current_user
from app.models.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/sessions/{session_id}", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def invoke_chat(
    session_id: str,
    payload: ChatRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: ChatService = Depends(get_chat_service),  # noqa: B008
) -> ChatResponse:
    """Run one chat turn and return full response."""
    return await service.chat(
        user_id=str(current_user["id"]),
        session_id=session_id,
        request=payload,
    )


@router.post("/chat/stream")
async def stream_chat(
    session_id: str,
    payload: ChatRequest,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: ChatService = Depends(get_chat_service),  # noqa: B008
) -> StreamingResponse:
    """Run one chat turn and stream SSE tokens."""
    return StreamingResponse(
        service.stream_chat(
            user_id=str(current_user["id"]),
            session_id=session_id,
            request=payload,
        ),
        media_type="text/event-stream",
    )
