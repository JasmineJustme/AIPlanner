from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import text

from app.api.router import api_router
from app.config import settings
from app.database import engine
from app.models.base import Base


async def _ensure_sqlite_runtime_schema() -> None:
    # Keep old local SQLite files usable even when migrations were not applied.
    if "sqlite" not in settings.DATABASE_URL:
        return

    async with engine.begin() as conn:
        table_info = await conn.execute(text("PRAGMA table_info(todos)"))
        columns = {row[1] for row in table_info.fetchall()}

        alter_sql: list[str] = []
        if "execution_mode" not in columns:
            alter_sql.append("ALTER TABLE todos ADD COLUMN execution_mode VARCHAR(20) NOT NULL DEFAULT 'system'")
        if "completed_at" not in columns:
            alter_sql.append("ALTER TABLE todos ADD COLUMN completed_at DATETIME")
        if "is_recurring" not in columns:
            alter_sql.append("ALTER TABLE todos ADD COLUMN is_recurring BOOLEAN NOT NULL DEFAULT 0")
        if "recurrence_cron" not in columns:
            alter_sql.append("ALTER TABLE todos ADD COLUMN recurrence_cron VARCHAR(100)")
        if "recurrence_count" not in columns:
            alter_sql.append("ALTER TABLE todos ADD COLUMN recurrence_count INTEGER NOT NULL DEFAULT 0")

        for sql in alter_sql:
            await conn.execute(text(sql))

        if alter_sql:
            logger.warning(f"Applied SQLite compatibility schema updates for todos: {len(alter_sql)} column(s)")

        pref_info = await conn.execute(text("PRAGMA table_info(notification_prefs)"))
        pref_columns = {row[1] for row in pref_info.fetchall()}
        if "channel_enabled_map" not in pref_columns:
            await conn.execute(
                text("ALTER TABLE notification_prefs ADD COLUMN channel_enabled_map JSON NOT NULL DEFAULT '{}'"),
            )
            await conn.execute(
                text(
                    """
                    UPDATE notification_prefs
                    SET channel_enabled_map =
                        '{"in_app":' || CASE WHEN in_app_enabled THEN 'true' ELSE 'false' END ||
                        ',"email_workflow":' || CASE WHEN email_enabled THEN 'true' ELSE 'false' END ||
                        ',"wechat_workflow":' || CASE WHEN wechat_enabled THEN 'true' ELSE 'false' END ||
                        '}'
                    WHERE channel_enabled_map IS NULL OR channel_enabled_map = '{}'
                    """
                ),
            )
            logger.warning("Applied SQLite compatibility schema update for notification_prefs.channel_enabled_map")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Audit Coworker backend...")

    # Enable WAL mode for SQLite to handle concurrency better
    if "sqlite" in settings.DATABASE_URL:
        async with engine.connect() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;")) # Optional: for performance
            logger.info("SQLite WAL mode enabled.")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_sqlite_runtime_schema()
    logger.info("Database tables ensured.")

    from app.jobs.scheduler_job import start_scheduler, stop_scheduler
    start_scheduler()

    yield

    stop_scheduler()
    await engine.dispose()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Audit Coworker API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
