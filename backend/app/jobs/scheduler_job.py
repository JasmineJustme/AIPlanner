from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import select

from app.models.settings import SystemSetting

scheduler = AsyncIOScheduler()
_auto_discover_running = False


def _unwrap_setting_value(raw: object, default: object = None) -> object:
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value")
    return raw if raw is not None else default


async def _get_system_setting(db, key: str, default: object = None) -> object:
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()
    if not setting:
        return default
    return _unwrap_setting_value(setting.value, default)


async def _set_system_setting(db, key: str, value: object) -> None:
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = result.scalar_one_or_none()
    wrapped = value if isinstance(value, dict) else {"value": value}
    if setting:
        setting.value = wrapped
    else:
        db.add(SystemSetting(key=key, value=wrapped))


async def scheduler_tick() -> None:
    """Called every minute by APScheduler"""
    from app.database import async_session_factory
    from app.engine.scheduler import scheduler_engine

    async with async_session_factory() as db:
        try:
            await scheduler_engine.run_tick(db)
            await db.commit()
        except Exception as e:
            logger.error(f"Scheduler tick error: {e}")
            await db.rollback()


async def sync_tick() -> None:
    """Called periodically for datasource sync"""
    from app.database import async_session_factory
    from app.services.datasource_sync import sync_all_datasources

    async with async_session_factory() as db:
        try:
            await sync_all_datasources(db)
            await db.commit()
        except Exception as e:
            logger.error(f"Sync tick error: {e}")
            await db.rollback()


async def auto_discover_tick() -> None:
    """Called every minute; runs smart todo discovery according to system settings."""
    global _auto_discover_running
    if _auto_discover_running:
        logger.warning("Auto discover tick skipped because previous run is still in progress")
        return

    from app.database import async_session_factory
    from app.engine.todo_discovery import todo_discovery_engine

    async with async_session_factory() as db:
        try:
            enabled = bool(await _get_system_setting(db, "auto_smart_discovery_enabled", False))
            if not enabled:
                return

            interval_raw = await _get_system_setting(db, "auto_smart_discovery_interval_minutes", 15)
            try:
                interval_minutes = int(interval_raw)
            except (TypeError, ValueError):
                interval_minutes = 15
            interval_minutes = max(1, min(interval_minutes, 60))

            now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
            last_run_raw = await _get_system_setting(db, "auto_smart_discovery_last_run_at", None)
            last_run_at = None
            if isinstance(last_run_raw, str) and last_run_raw.strip():
                try:
                    last_run_at = datetime.fromisoformat(last_run_raw.strip().replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    last_run_at = None

            if last_run_at and (now - last_run_at) < timedelta(minutes=interval_minutes):
                return

            _auto_discover_running = True
            result = await todo_discovery_engine.smart_discover(db)
            await _set_system_setting(db, "auto_smart_discovery_last_run_at", now.isoformat())
            await db.commit()
            logger.info(
                "Auto smart discover completed: created={}, dedup={}, synced_datasource_count={}",
                result.get("created_count", 0),
                result.get("dedup_count", 0),
                result.get("synced_datasource_count", 0),
            )
        except Exception as e:
            logger.error(f"Auto discover tick error: {e}")
            await db.rollback()
        finally:
            _auto_discover_running = False


async def deadline_reminder_tick() -> None:
    """Called every minute; executes overdue todo reminder scanner by settings."""
    from app.database import async_session_factory
    from app.engine.deadline_reminder import scan_and_send_deadline_reminders

    async with async_session_factory() as db:
        try:
            enabled = bool(await _get_system_setting(db, "deadline_reminder_enabled", True))
            if not enabled:
                return
            result = await scan_and_send_deadline_reminders(db)
            await db.commit()
            logger.info(
                "Deadline reminder tick completed: scanned={}, sent={}, skipped={}",
                result.get("scanned", 0),
                result.get("sent", 0),
                result.get("skipped", 0),
            )
        except Exception as e:
            logger.error(f"Deadline reminder tick error: {e}")
            await db.rollback()


def start_scheduler() -> None:
    scheduler.add_job(scheduler_tick, "interval", minutes=1, id="scheduler_tick")
    scheduler.add_job(sync_tick, "interval", hours=1, id="sync_tick")
    scheduler.add_job(auto_discover_tick, "interval", minutes=1, id="auto_discover_tick")
    scheduler.add_job(deadline_reminder_tick, "interval", minutes=1, id="deadline_reminder_tick")
    scheduler.start()
    logger.info("APScheduler started")


def stop_scheduler() -> None:
    scheduler.shutdown()
    logger.info("APScheduler stopped")
