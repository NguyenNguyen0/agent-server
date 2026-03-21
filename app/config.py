from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_file_size_mb: int = 20
    chunk_size: int = 1000
    chunk_overlap: int = 200


settings = Settings()
