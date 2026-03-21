from unittest.mock import AsyncMock

import pytest

from app.services.auth_service import AuthService


@pytest.mark.asyncio
async def test_register_user_hashes_password_and_creates_user() -> None:
    user_repo = AsyncMock()
    user_repo.register_user.return_value = {
        "id": "u1",
        "email": "u@example.com",
        "full_name": "U",
    }
    service = AuthService(user_repo=user_repo)

    result = await service.register_user("u@example.com", "password123", "U")

    assert result["id"] == "u1"
    user_repo.register_user.assert_awaited_once_with(
        "u@example.com",
        "password123",
        "U",
    )


@pytest.mark.asyncio
async def test_login_returns_access_token_for_valid_credentials() -> None:
    user_repo = AsyncMock()
    user_repo.login.return_value = "jwt-token"
    service = AuthService(user_repo=user_repo)

    token = await service.login("u@example.com", "password123")

    assert isinstance(token, str)
    assert token == "jwt-token"


@pytest.mark.asyncio
async def test_get_current_user_from_token_raises_for_invalid_token() -> None:
    user_repo = AsyncMock()
    user_repo.get_current_user_from_token.side_effect = ValueError("Invalid token")
    service = AuthService(user_repo=user_repo)

    with pytest.raises(ValueError):
        await service.get_current_user_from_token("bad-token")
