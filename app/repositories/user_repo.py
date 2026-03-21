from datetime import datetime
from typing import Any, Protocol

from supabase import AsyncClient
from supabase_auth.errors import AuthApiError


class UserRepository:
    """Repository for Supabase Auth user operations."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def register_user(
        self,
        email: str,
        password: str,
        full_name: str,
    ) -> dict[str, Any]:
        """Register and auto-confirm a user through Supabase Auth admin API."""
        try:
            admin_response = await self._client.auth.admin.create_user(
                {
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"full_name": full_name},
                }
            )
            if admin_response.user is None:
                raise ValueError("Could not register user")
            return self._to_public_user(admin_response.user)
        except AuthApiError as exc:
            # Fallback for environments using anon key or restricted service key.
            if "requires a valid Bearer token" not in str(exc):
                raise ValueError(str(exc)) from exc

            sign_up_response = await self._client.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {"data": {"full_name": full_name}},
                }
            )
            if sign_up_response.user is None:
                raise ValueError("Could not register user")  # noqa: B904
            return self._to_public_user(sign_up_response.user)

    async def login(self, email: str, password: str) -> str:
        """Sign in user and return JWT access token."""
        try:
            response = await self._client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except AuthApiError as exc:
            if "Email not confirmed" in str(exc):
                raise ValueError("Email not confirmed") from exc
            raise ValueError("Invalid credentials") from exc

        if response.session is None:
            raise ValueError("Invalid credentials")
        return str(response.session.access_token)

    async def get_current_user_from_token(self, token: str) -> dict[str, Any]:
        """Validate JWT and return current user."""
        response = await self._client.auth.get_user(token)
        if response is None or response.user is None:
            raise ValueError("Invalid token")
        return self._to_public_user(response.user)

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Fetch one user by id using admin API."""
        response = await self._client.auth.admin.get_user_by_id(user_id)
        if response is None or response.user is None:
            return None
        return self._to_public_user(response.user)

    async def list_users(self) -> list[dict[str, Any]]:
        """List users via Supabase Auth admin API."""
        users = await self._client.auth.admin.list_users(page=1, per_page=1000)
        return [self._to_public_user(user) for user in users]

    def _to_public_user(self, user: "AuthUserLike") -> dict[str, Any]:
        """Normalize Supabase user object to API public shape."""
        user_metadata = user.user_metadata or {}
        return {
            "id": str(user.id),
            "email": str(user.email or ""),
            "full_name": str(user_metadata.get("full_name", "")),
            "is_active": True,
            "created_at": user.created_at,
        }


class AuthUserLike(Protocol):
    """Protocol for Supabase user payload objects."""

    id: str
    email: str | None
    user_metadata: dict[str, Any]
    created_at: datetime
