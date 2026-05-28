from datetime import date, datetime

from scripts.models import RawPost


def _parse(posted_at: str | None) -> date | None:
    if not posted_at:
        return None
    try:
        return datetime.strptime(posted_at, "%Y-%m-%d").date()
    except ValueError:
        return None


def filter_recent(
    posts: list[RawPost], window_days: int = 730, today: date | None = None
) -> list[RawPost]:
    ref = today or date.today()
    kept: list[RawPost] = []
    for p in posts:
        d = _parse(p.posted_at)
        if d is None:
            kept.append(p)  # undated/unparseable → keep
            continue
        if (ref - d).days <= window_days:
            kept.append(p)
    return kept
