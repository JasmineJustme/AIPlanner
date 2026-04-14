from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger

try:
    from croniter import croniter  # type: ignore
except Exception:  # pragma: no cover
    croniter = None


def normalize_cron_expression(expr: str | None) -> str | None:
    if expr is None:
        return None
    normalized = str(expr).strip()
    return normalized or None


def validate_cron_expression(expr: str | None) -> bool:
    cron = normalize_cron_expression(expr)
    if not cron:
        return False

    if croniter is not None:
        return bool(croniter.is_valid(cron))

    try:
        CronTrigger.from_crontab(cron)
        return True
    except Exception:
        return False


def get_next_run_time(expr: str, base_time: datetime) -> datetime:
    if croniter is not None:
        it = croniter(expr, base_time)
        return it.get_next(datetime)

    trigger = CronTrigger.from_crontab(expr, timezone=timezone.utc)
    aware_base = base_time.replace(tzinfo=timezone.utc) if base_time.tzinfo is None else base_time.astimezone(timezone.utc)
    next_dt = trigger.get_next_fire_time(previous_fire_time=None, now=aware_base)
    if next_dt is None:
        raise ValueError("Cannot calculate next run time from cron expression")
    return next_dt.replace(tzinfo=None)
