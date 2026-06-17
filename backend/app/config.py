"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/check_yg.db"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # File storage
    UPLOAD_DIR: str = "data/uploads"
    OUTPUT_DIR: str = "data/outputs"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # LLM
    LLM_API_ENDPOINT: str = "http://localhost:11434/v1"
    LLM_API_KEY: str = "ollama"
    LLM_MODEL_NAME: str = "qwen2.5:7b"
    LLM_TIMEOUT: int = 60

    # MinerU PDF parser
    MINERU_MODE: str = "local"
    MINERU_URL: str = "http://localhost:8000"
    MINERU_PUBLIC_URL: str = "https://mineru.net/api/v1/agent"
    MINERU_PUBLIC_API_KEY: str = ""
    MINERU_TIMEOUT: int = 300


settings = Settings()
