import json as _json
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import select, text
from starlette.responses import FileResponse

from app.api.router import api_router
from app.config import settings
from app.database import engine, async_session_factory
from app.models.base import Base


def _resolve_frontend_dist() -> Path | None:
    """Locate the frontend dist folder in bundled or development layout."""
    if getattr(sys, "frozen", False):
        bundle_dir = Path(sys._MEIPASS)
        dist = bundle_dir / "frontend_dist"
        if dist.is_dir():
            return dist
    project_root = Path(__file__).resolve().parent.parent.parent
    dist = project_root / "frontend" / "dist"
    if dist.is_dir():
        return dist
    return None


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

        llm_info = await conn.execute(text("PRAGMA table_info(llm_configs)"))
        llm_columns = {row[1] for row in llm_info.fetchall()}
        if "timeout" not in llm_columns:
            await conn.execute(
                text("ALTER TABLE llm_configs ADD COLUMN timeout INTEGER NOT NULL DEFAULT 180"),
            )
            logger.warning("Applied SQLite compatibility schema update for llm_configs.timeout")


async def _migrate_orchestrations_from_json() -> None:
    """One-time migration: import orchestrations.json into the DB table."""
    from app.models.orchestration import Orchestration

    json_file = Path(__file__).resolve().parents[1] / "data" / "orchestrations.json"
    if not json_file.exists():
        return

    try:
        raw = _json.loads(json_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not read orchestrations.json for migration: {e}")
        return

    if not isinstance(raw, dict) or not raw:
        return

    async with async_session_factory() as session:
        existing = await session.execute(select(Orchestration.id).limit(1))
        if existing.scalar_one_or_none() is not None:
            logger.info("Orchestrations table already has data – skipping JSON migration")
            return

        count = 0
        for orch_id, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("status") == "cancelled":
                continue

            submitted_str = entry.get("submitted_at")
            submitted_at = None
            if submitted_str:
                try:
                    submitted_at = datetime.fromisoformat(str(submitted_str))
                    if submitted_at.tzinfo is not None:
                        submitted_at = submitted_at.replace(tzinfo=None)
                except (ValueError, TypeError):
                    pass

            orch = Orchestration(
                id=orch_id,
                summary=entry.get("summary"),
                status=entry.get("status", "pending_confirm"),
                submitted_at=submitted_at,
                todos_snapshot=entry.get("todos"),
                suggested_agent=entry.get("suggested_agent"),
                suggested_wagent=entry.get("suggested_wagent"),
                plan=entry.get("plan"),
                llm_reason=entry.get("llm_reason"),
                error=entry.get("error"),
                llm_recommended_id=entry.get("llm_recommended_id"),
                llm_recommended_name=entry.get("llm_recommended_name"),
                llm_recommended_type=entry.get("llm_recommended_type"),
                llm_recommended_input_params=entry.get("llm_recommended_input_params"),
            )
            session.add(orch)
            count += 1

        if count:
            await session.commit()
            backup = json_file.with_suffix(".json.migrated")
            json_file.rename(backup)
            logger.info(f"Migrated {count} orchestrations from JSON to DB (backup: {backup.name})")
        else:
            logger.info("No orchestrations to migrate from JSON")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Audit Coworker backend...")

    # Enable WAL mode for SQLite to handle concurrency better
    if "sqlite" in settings.DATABASE_URL:
        async with engine.connect() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
            logger.info("SQLite WAL mode enabled.")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_sqlite_runtime_schema()
    await _migrate_orchestrations_from_json()
    logger.info("Database tables ensured.")

    from app.api.orchestration import recover_stale_analyzing_orchestrations
    await recover_stale_analyzing_orchestrations()

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


_frontend_dist = _resolve_frontend_dist()
if _frontend_dist:
    logger.info(f"Serving frontend from {_frontend_dist}")
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = _frontend_dist / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")
