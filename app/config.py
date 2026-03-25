from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    mongodb_uri: str
    mongodb_db_name: str = "agent_server"

    huggingface_api_key: str = ""
    hf_embedding_model: str = "BAAI/bge-base-en-v1.5"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_name: str = "uploads"

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]
    max_file_size_mb: int = 5
    chunk_size: int = 1000
    chunk_overlap: int = 200


settings = Settings()  # ty:ignore[missing-argument]
