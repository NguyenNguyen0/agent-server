from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health() -> dict[str, str]:
    """Simple liveness endpoint."""
    return {"status": "ok"}
