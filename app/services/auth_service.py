from typing import Any

from app.repositories.user_repo import UserRepository


class AuthService:
    """Authentication and JWT utilities."""

    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    async def register_user(
        self,
        email: str,
        password: str,
        full_name: str,
    ) -> dict[str, Any]:
        """Register user through Supabase Auth."""
        return await self._user_repo.register_user(email, password, full_name)

    async def login(self, email: str, password: str) -> str:
        """Authenticate and return JWT access token."""
        return await self._user_repo.login(email, password)

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Fetch user by id."""
        return await self._user_repo.get_user_by_id(user_id)

    async def list_users(self) -> list[dict[str, Any]]:
        """List all users."""
        return await self._user_repo.list_users()

    async def get_current_user_from_token(self, token: str) -> dict[str, Any]:
        """Validate token and return corresponding user."""
        return await self._user_repo.get_current_user_from_token(token)
