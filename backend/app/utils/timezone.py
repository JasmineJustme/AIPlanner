from datetime import UTC, datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def utc_now_naive() -> datetime:
    """Return current UTC time without tzinfo for DB storage consistency."""
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def parse_datetime_value(value: datetime | str | None) -> datetime | None:
    """Parse datetime value from datetime/ISO string; returns None on invalid input."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def beijing_to_utc_naive(value: datetime) -> datetime:
    """Convert Beijing time to UTC naive datetime for querying/storing."""
    if value.tzinfo is None:
        aware = value.replace(tzinfo=BEIJING_TZ)
    else:
        aware = value.astimezone(BEIJING_TZ)
    return aware.astimezone(UTC).replace(tzinfo=None, microsecond=0)


def to_utc_naive(value: datetime | str | None) -> datetime | None:
    """Convert input datetime to UTC naive; naive values are treated as Beijing time."""
    parsed = parse_datetime_value(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return beijing_to_utc_naive(parsed)
    return parsed.astimezone(UTC).replace(tzinfo=None, microsecond=0)


def utc_to_beijing_datetime(value: datetime | None) -> datetime | None:
    """Convert UTC datetime (aware/naive) to Asia/Shanghai datetime."""
    if value is None:
        return None
    aware_utc = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware_utc.astimezone(BEIJING_TZ).replace(microsecond=0)


def utc_to_beijing_iso(value: datetime | None) -> str | None:
    converted = utc_to_beijing_datetime(value)
    return converted.isoformat() if converted else None


def utc_to_beijing_iso_from_any(value: datetime | str | None) -> str | None:
    """Convert UTC datetime/string to Beijing ISO format for API output."""
    parsed = parse_datetime_value(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed.astimezone(BEIJING_TZ).replace(microsecond=0).isoformat()


