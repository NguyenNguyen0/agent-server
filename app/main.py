from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.mongo import close_client, get_client
from app.exceptions import AuthError, LLMRateLimitError, SessionNotFoundError
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.sessions import router as sessions_router
from app.routers.users import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage MongoDB connection lifecycle."""
    _ = app
    if settings.app_env != "test":
        client = get_client()
        await client.admin.command("ping")
    yield
    await close_client()


app = FastAPI(title="agent-server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(users_router)


@app.exception_handler(SessionNotFoundError)
async def session_not_found_handler(
    request: Request,
    exc: SessionNotFoundError,
) -> JSONResponse:
    """Map SessionNotFoundError to HTTP 404."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(LLMRateLimitError)
async def rate_limit_handler(
    request: Request,
    exc: LLMRateLimitError,
) -> JSONResponse:
    """Map LLMRateLimitError to HTTP 429."""
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Retry later."},
    )


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    """Map AuthError to HTTP 401."""
    return JSONResponse(status_code=401, content={"detail": str(exc)})
