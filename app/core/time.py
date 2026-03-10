from datetime import datetime, timedelta, timezone

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist() -> datetime:
    """Get current time in IST"""
    return datetime.now(IST)

def utc_to_ist(dt: datetime) -> datetime:
    """Convert UTC datetime to IST"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)

def ist_to_utc(dt: datetime) -> datetime:
    """Convert IST datetime to UTC"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc)

def format_ist(dt: datetime, include_tz: bool = True) -> str:
    """Format datetime in IST"""
    # Convert to IST if the datetime is in UTC (check by offset, not identity)
    if dt.tzinfo is not None and dt.utcoffset() == timedelta(0):
        ist_dt = utc_to_ist(dt)
    else:
        ist_dt = dt
    fmt = "%Y-%m-%d %H:%M:%S"
    if include_tz:
        return ist_dt.strftime(fmt) + " IST"
    return ist_dt.strftime(fmt)
