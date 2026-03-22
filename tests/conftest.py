import os


def _set_required_env() -> None:
    os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
    os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
    os.environ.setdefault("MONGODB_DB_NAME", "agent_server_test")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")


_set_required_env()
