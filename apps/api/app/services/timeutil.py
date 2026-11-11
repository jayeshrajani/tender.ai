"""Time helpers. Storage is always UTC; display/scheduling is Asia/Kolkata."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Scheduled reanalysis slots (IST) and daily digest hour.
REANALYSIS_HOURS_IST = (0, 8, 16)
DIGEST_HOUR_IST = 9

_DATE_FORMATS = (
    "%d-%b-%Y %I:%M %p",
    "%d-%b-%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y %I:%M %p",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %I:%M %p",
    "%d.%m.%Y %H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%d-%b-%Y",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def ist_to_utc(dt: datetime) -> datetime:
    """Interpret a naive datetime as IST wall-clock time and convert to UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC)


def parse_ist_datetime(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    """Parse portal-style date strings (assumed IST unless an offset is present) to UTC."""
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            return parsed.astimezone(UTC)
        return ist_to_utc(parsed)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%H" not in fmt and "%I" not in fmt and end_of_day:
            parsed = datetime.combine(parsed.date(), time(23, 59))
        return ist_to_utc(parsed)
    return None


def format_ist(dt: datetime | None) -> str:
    if dt is None:
        return "Not stated"
    local = to_ist(dt)
    return local.strftime("%d %b %Y, %I:%M %p IST").lstrip("0")


def today_ist() -> date:
    return utcnow().astimezone(IST).date()


def slot_key(slot_start_utc: datetime) -> str:
    return to_ist(slot_start_utc).strftime("%Y-%m-%dT%H:%M+05:30")


def latest_reanalysis_slot(now: datetime | None = None) -> datetime:
    """Most recent 00:00/08:00/16:00 IST boundary at or before ``now`` (UTC result)."""
    local = to_ist(now or utcnow())
    hour = max(h for h in REANALYSIS_HOURS_IST if h <= local.hour)
    return local.replace(hour=hour, minute=0, second=0, microsecond=0).astimezone(UTC)


def next_reanalysis_slot(now: datetime | None = None) -> datetime:
    local = to_ist(now or utcnow())
    for h in REANALYSIS_HOURS_IST:
        candidate = local.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidate > local:
            return candidate.astimezone(UTC)
    tomorrow = (local + timedelta(days=1)).replace(
        hour=REANALYSIS_HOURS_IST[0], minute=0, second=0, microsecond=0
    )
    return tomorrow.astimezone(UTC)


def latest_digest_slot(now: datetime | None = None) -> datetime | None:
    local = to_ist(now or utcnow())
    slot = local.replace(hour=DIGEST_HOUR_IST, minute=0, second=0, microsecond=0)
    return slot.astimezone(UTC) if slot <= local else None


def next_digest_slot(now: datetime | None = None) -> datetime:
    local = to_ist(now or utcnow())
    slot = local.replace(hour=DIGEST_HOUR_IST, minute=0, second=0, microsecond=0)
    if slot <= local:
        slot += timedelta(days=1)
    return slot.astimezone(UTC)


def in_quiet_hours(now: datetime, start: time | None, end: time | None) -> bool:
    if start is None or end is None or start == end:
        return False
    t = to_ist(now).time()
    if start < end:
        return start <= t < end
    return t >= start or t < end


def quiet_hours_end(now: datetime, end: time) -> datetime:
    local = to_ist(now)
    candidate = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)
