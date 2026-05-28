from datetime import date

from scripts.models import RawPost
from scripts.corpus.recency import filter_recent


def _post(posted_at):
    return RawPost("nowcoder", "u", "text", "Q", posted_at=posted_at)


def test_keeps_recent_drops_old():
    ref = date(2026, 5, 28)
    posts = [_post("2025-09-01"), _post("2023-01-01")]  # within 2y, older than 2y
    kept = filter_recent(posts, window_days=730, today=ref)
    assert [p.posted_at for p in kept] == ["2025-09-01"]


def test_none_dates_are_kept():
    ref = date(2026, 5, 28)
    posts = [_post(None), _post("2010-01-01")]
    kept = filter_recent(posts, window_days=730, today=ref)
    assert [p.posted_at for p in kept] == [None]


def test_unparseable_date_is_kept():
    ref = date(2026, 5, 28)
    posts = [_post("not-a-date")]
    kept = filter_recent(posts, window_days=730, today=ref)
    assert len(kept) == 1


def test_boundary_exactly_window_is_kept():
    ref = date(2026, 5, 28)
    posts = [_post("2024-05-29")]  # 729 days before ref → kept
    kept = filter_recent(posts, window_days=730, today=ref)
    assert len(kept) == 1
