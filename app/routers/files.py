from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)

from app.dependencies import get_file_service
from app.middleware.auth import get_current_user
from app.models.file import FileListResponse, FileResponse
from app.services.file_service import FileService

router = APIRouter(prefix="/sessions/{session_id}", tags=["files"])


@router.post("/files", response_model=FileResponse)
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),  # noqa: B008
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: FileService = Depends(get_file_service),  # noqa: B008
) -> FileResponse:
    """Upload one file into a session for RAG context."""
    try:
        row = await service.upload_file(str(current_user["id"]), session_id, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(**row)


@router.get("/files", response_model=FileListResponse)
async def list_files(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: FileService = Depends(get_file_service),  # noqa: B008
) -> FileListResponse:
    """List uploaded files in one session for current user."""
    rows = await service.list_files(str(current_user["id"]), session_id)
    items = [FileResponse(**row) for row in rows]
    return FileListResponse(files=items, total=len(items))


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    session_id: str,
    file_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    service: FileService = Depends(get_file_service),  # noqa: B008
) -> Response:
    """Delete one uploaded file and related chunks."""
    try:
        await service.delete_file(str(current_user["id"]), session_id, file_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
