from datetime import date, datetime
from typing import Literal

from scripts.models import RawPost

RecencyStatus = Literal["recent", "stale", "undated", "invalid", "future"]


def _parse(posted_at: str | None) -> date | None:
    if not posted_at:
        return None
    try:
        return datetime.strptime(posted_at, "%Y-%m-%d").date()
    except ValueError:
        return None


def classify_recency(
    posted_at: str | None,
    window_days: int = 730,
    today: date | None = None,
    future_tolerance_days: int = 1,
) -> RecencyStatus:
    if window_days < 0:
        raise ValueError("window_days must be non-negative")
    if future_tolerance_days < 0:
        raise ValueError("future_tolerance_days must be non-negative")
    if not posted_at:
        return "undated"

    posted_date = _parse(posted_at)
    if posted_date is None:
        return "invalid"

    age_days = ((today or date.today()) - posted_date).days
    if age_days < -future_tolerance_days:
        return "future"
    if age_days <= window_days:
        return "recent"
    return "stale"


def filter_recent(
    posts: list[RawPost],
    window_days: int = 730,
    today: date | None = None,
    *,
    keep_undated: bool = True,
    future_tolerance_days: int = 1,
) -> list[RawPost]:
    kept: list[RawPost] = []
    for p in posts:
        status = classify_recency(
            p.posted_at,
            window_days=window_days,
            today=today,
            future_tolerance_days=future_tolerance_days,
        )
        if status == "recent" or (status == "undated" and keep_undated):
            kept.append(p)
    return kept
