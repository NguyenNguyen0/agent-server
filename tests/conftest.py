import os


def _set_required_env() -> None:
    os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")


_set_required_env()
