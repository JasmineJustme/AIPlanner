from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.router import api_router
from app.config import settings
from app.database import engine
from app.models.base import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Audit Coworker backend...")

    # Enable WAL mode for SQLite to handle concurrency better
    if "sqlite" in settings.DATABASE_URL:
        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;")) # Optional: for performance
            logger.info("SQLite WAL mode enabled.")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
