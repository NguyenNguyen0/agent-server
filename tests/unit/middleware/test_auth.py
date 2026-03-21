from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.middleware.auth import get_current_user


@dataclass
class MockUser:
    id: str
    email: str

    def model_dump(self) -> dict[str, str]:
        return {"id": self.id, "email": self.email}


@dataclass
class MockAuthResult:
    user: MockUser | None


@pytest.mark.asyncio
async def test_get_current_user_returns_user_dict_when_token_valid() -> None:
    db = AsyncMock()
    db.auth.get_user = AsyncMock(
        return_value=MockAuthResult(user=MockUser(id="user-1", email="u@example.com"))
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid")

    result = await get_current_user(credentials=credentials, db=db)

    assert result["id"] == "user-1"


@pytest.mark.asyncio
async def test_get_current_user_raises_401_when_token_invalid() -> None:
    db = AsyncMock()
    db.auth.get_user = AsyncMock(return_value=MockAuthResult(user=None))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid")

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=credentials, db=db)

    assert exc_info.value.status_code == 401
