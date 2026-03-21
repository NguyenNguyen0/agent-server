from typing import Any

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import AsyncClient

from app.dependencies import get_supabase_client

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),  # noqa: B008
    db: AsyncClient = Depends(get_supabase_client),  # noqa: B008
) -> dict[str, Any]:
    """Validate Supabase JWT and return current user data."""
    try:
        user_response = await db.auth.get_user(credentials.credentials)
        if user_response is None or user_response.user is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_response.user.model_dump()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials",
        ) from exc
