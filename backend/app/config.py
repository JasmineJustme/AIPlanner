from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./audit_coworker.db"
    ENCRYPTION_KEY: str = "your-32-byte-key-here"
    LOG_LEVEL: str = "INFO"
    SSL_VERIFY: bool = True

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
