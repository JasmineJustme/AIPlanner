from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    ENCRYPTION_KEY: str = "your-32-byte-key-here"
    LOG_LEVEL: str = "INFO"
    SSL_VERIFY: bool = True

    AUTH_TOKEN_SECRET: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 12
    BOOTSTRAP_ADMIN_USERNAME: str = "admin"
    BOOTSTRAP_ADMIN_PASSWORD: str = "Admin@123456"
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@example.com"

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = {
        "env_file": Path(__file__).resolve().parents[1] / ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()
