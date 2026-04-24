import json as _json
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import inspect, select, text
from starlette.responses import FileResponse

from app.api.router import api_router
from app.config import settings
from app.database import engine, async_session_factory
from app.models.base import Base
from app.models.user import User
from app.security import hash_password


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


async def _ensure_runtime_schema_updates() -> None:
    def _apply(sync_conn):
        inspector = inspect(sync_conn)

        todo_columns = {col["name"] for col in inspector.get_columns("todos")}
        todo_additions = [
            ("owner_id", "ALTER TABLE todos ADD COLUMN owner_id VARCHAR(36) NULL"),
            ("original_owner_id", "ALTER TABLE todos ADD COLUMN original_owner_id VARCHAR(36) NULL"),
            ("target_user_id", "ALTER TABLE todos ADD COLUMN target_user_id VARCHAR(36) NULL"),
            ("task_flow_type", "ALTER TABLE todos ADD COLUMN task_flow_type VARCHAR(30) NOT NULL DEFAULT 'user_execution'"),
            ("last_flow_state", "ALTER TABLE todos ADD COLUMN last_flow_state VARCHAR(20) NULL"),
            ("last_flow_type", "ALTER TABLE todos ADD COLUMN last_flow_type VARCHAR(40) NULL"),
        ]
        for name, sql in todo_additions:
            if name not in todo_columns:
                sync_conn.execute(text(sql))

        message_columns = {col["name"] for col in inspector.get_columns("messages")}
        message_additions = [
            ("related_request_id", "ALTER TABLE messages ADD COLUMN related_request_id VARCHAR(36) NULL"),
            ("recipient_user_id", "ALTER TABLE messages ADD COLUMN recipient_user_id VARCHAR(36) NULL"),
            ("sender_user_id", "ALTER TABLE messages ADD COLUMN sender_user_id VARCHAR(36) NULL"),
        ]
        for name, sql in message_additions:
            if name not in message_columns:
                sync_conn.execute(text(sql))

    async with engine.begin() as conn:
        await conn.run_sync(_apply)


async def _bootstrap_admin_user() -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == settings.BOOTSTRAP_ADMIN_EMAIL))
        admin = result.scalar_one_or_none()
        if admin:
            return

        admin = User(
            username=settings.BOOTSTRAP_ADMIN_USERNAME,
            email=settings.BOOTSTRAP_ADMIN_EMAIL,
            full_name="System Administrator",
            password_hash=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
            role="admin",
            is_active=True,
            is_superuser=True,
        )
        session.add(admin)
        await session.commit()
        logger.warning("Bootstrap admin user created. Please change default password immediately.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Audit Coworker backend...")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_runtime_schema_updates()
    await _migrate_orchestrations_from_json()
    await _bootstrap_admin_user()
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
