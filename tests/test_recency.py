from datetime import date

from scripts.models import RawPost
from scripts.corpus.recency import classify_recency, filter_recent


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


def test_unparseable_date_is_dropped():
    ref = date(2026, 5, 28)
    posts = [_post("not-a-date")]
    kept = filter_recent(posts, window_days=730, today=ref)
    assert kept == []


def test_boundary_exactly_window_is_kept():
    ref = date(2026, 5, 28)
    posts = [_post("2024-05-29")]  # 729 days before ref → kept
    kept = filter_recent(posts, window_days=730, today=ref)
    assert len(kept) == 1


def test_classify_recency_distinguishes_unknown_invalid_and_stale():
    ref = date(2026, 5, 28)

    assert classify_recency(None, today=ref) == "undated"
    assert classify_recency("not-a-date", today=ref) == "invalid"
    assert classify_recency("2023-01-01", today=ref) == "stale"
    assert classify_recency("2026-01-01", today=ref) == "recent"


def test_future_date_is_dropped_beyond_timezone_tolerance():
    ref = date(2026, 5, 28)
    posts = [_post("2026-05-29"), _post("2026-05-30")]

    kept = filter_recent(posts, today=ref)

    assert [post.posted_at for post in kept] == ["2026-05-29"]
    assert classify_recency("2026-05-30", today=ref) == "future"


def test_can_exclude_undated_supplemental_posts():
    ref = date(2026, 5, 28)
    posts = [_post(None), _post("2026-01-01")]

    kept = filter_recent(posts, today=ref, keep_undated=False)

    assert [post.posted_at for post in kept] == ["2026-01-01"]
