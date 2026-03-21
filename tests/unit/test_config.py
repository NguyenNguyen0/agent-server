import pytest

from app.config import Settings


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-test")
    monkeypatch.setenv("APP_ENV", "test")

    settings = Settings()

    assert settings.groq_api_key == "gsk-test"
    assert settings.supabase_url == "https://project.supabase.co"
    assert settings.supabase_anon_key == "anon-test"
    assert settings.supabase_service_role_key == "service-test"
    assert settings.app_env == "test"
