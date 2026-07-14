"""Standard time buckets for capacity forwards (spec §3).

Buckets are the standardization that turns seller offers into a
comparable order book. All boundaries are UTC:

  * 8h  — blocks starting 00:00 / 08:00 / 16:00 UTC
  * 24h — calendar days starting 00:00 UTC
  * 168h — calendar weeks starting Monday 00:00 UTC

Pure functions over tz-aware datetimes. Naive datetimes are rejected
(fail-loud): a naive timestamp in the money path is always a bug.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

__all__ = [
    "BucketError",
    "BUCKET_HOURS",
    "DEFAULT_HORIZON_DAYS",
    "is_aligned",
    "validate_bucket_start",
    "next_bucket_start",
    "enumerate_buckets",
    "bucket_end",
]

BUCKET_HOURS = (8, 24, 168)
DEFAULT_HORIZON_DAYS = 28


class BucketError(ValueError):
    """Raised on invalid bucket parameters."""


def _require_utc(dt: datetime, name: str) -> datetime:
    if dt.tzinfo is None:
        raise BucketError(f"{name} must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _require_hours(bucket_hours: int) -> None:
    if bucket_hours not in BUCKET_HOURS:
        raise BucketError(f"bucket_hours must be one of {BUCKET_HOURS}")


def is_aligned(start: datetime, bucket_hours: int) -> bool:
    """True iff ``start`` lies exactly on a standard bucket boundary."""
    _require_hours(bucket_hours)
    start = _require_utc(start, "start")
    if start.minute or start.second or start.microsecond:
        return False
    if bucket_hours == 8:
        return start.hour in (0, 8, 16)
    if bucket_hours == 24:
        return start.hour == 0
    # 168h: Monday 00:00 UTC
    return start.hour == 0 and start.weekday() == 0


def bucket_end(start: datetime, bucket_hours: int) -> datetime:
    _require_hours(bucket_hours)
    start = _require_utc(start, "start")
    return start + timedelta(hours=bucket_hours)


def validate_bucket_start(
    start: datetime,
    bucket_hours: int,
    *,
    now: datetime,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> None:
    """A sellable bucket must be aligned, strictly in the future, and
    start within the horizon. Raises BucketError otherwise.

    'Strictly in the future' means the bucket's *start* is after now —
    capacity in an already-running bucket can't be forward-sold (that's
    spot's job).
    """
    _require_hours(bucket_hours)
    start = _require_utc(start, "start")
    now = _require_utc(now, "now")
    if horizon_days <= 0:
        raise BucketError("horizon_days must be > 0")
    if not is_aligned(start, bucket_hours):
        raise BucketError(
            f"start {start.isoformat()} is not on a {bucket_hours}h boundary"
        )
    if start <= now:
        raise BucketError("bucket_start must be strictly in the future")
    if start > now + timedelta(days=horizon_days):
        raise BucketError(f"bucket_start beyond {horizon_days}-day horizon")


def next_bucket_start(now: datetime, bucket_hours: int) -> datetime:
    """Earliest sellable bucket start strictly after ``now``."""
    _require_hours(bucket_hours)
    now = _require_utc(now, "now")
    base = now.replace(minute=0, second=0, microsecond=0)
    if bucket_hours == 8:
        aligned_hour = (now.hour // 8) * 8
        candidate = base.replace(hour=aligned_hour)
        step = timedelta(hours=8)
    elif bucket_hours == 24:
        candidate = base.replace(hour=0)
        step = timedelta(hours=24)
    else:  # 168
        candidate = base.replace(hour=0) - timedelta(days=now.weekday())
        step = timedelta(days=7)
    while candidate <= now:
        candidate += step
    return candidate


def enumerate_buckets(
    now: datetime,
    bucket_hours: int,
    *,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> list[datetime]:
    """All sellable bucket starts in (now, now + horizon]. Used by the
    forward-curve endpoint to render empty buckets explicitly."""
    _require_hours(bucket_hours)
    now = _require_utc(now, "now")
    if horizon_days <= 0:
        raise BucketError("horizon_days must be > 0")
    end = now + timedelta(days=horizon_days)
    out: list[datetime] = []
    cur = next_bucket_start(now, bucket_hours)
    while cur <= end:
        out.append(cur)
        cur += timedelta(hours=bucket_hours)
    return out
