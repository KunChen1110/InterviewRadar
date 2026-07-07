import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from scripts.models import Question

_PUNCT = re.compile(r"[^\w一-鿿]+")
_TRACKING_QUERY_KEYS = {
    "from",
    "ref",
    "source",
    "spm",
    "xsec_source",
    "xsec_token",
}
T = TypeVar("T")


@dataclass(frozen=True)
class QuestionRankScore:
    source_count: int
    occurrence_count: int
    recency_weight: float
    total: float


def normalize(text: str) -> str:
    t = text.strip().lower()
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


def _union(into: list[T], extra: list[T]) -> None:
    for item in extra:
        if item not in into:
            into.append(item)


def _max_date(a: str | None, b: str | None) -> str | None:
    candidates: list[tuple[date, str]] = []
    for value in (a, b):
        if not value:
            continue
        try:
            candidates.append((datetime.strptime(value, "%Y-%m-%d").date(), value))
        except ValueError:
            continue
    return max(candidates)[1] if candidates else None


def _recency_weight(posted_at: str | None, today: date) -> float:
    if not posted_at:
        return 0.2
    try:
        d = datetime.strptime(posted_at, "%Y-%m-%d").date()
    except ValueError:
        return 0.2
    days = (today - d).days
    if days < -1:
        return 0.2
    if days <= 365:
        return 1.0
    if days <= 730:
        return 0.6
    return 0.3


def normalize_source_ref(source_ref: str) -> str:
    value = source_ref.strip()
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return value
    path = parsed.path.rstrip("/") or "/"
    content_query = sorted(
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    )
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            urlencode(content_query),
            "",
        )
    )


def question_rank_score(q: Question, today: date | None = None) -> QuestionRankScore:
    ref = today or date.today()
    source_count = len(
        {normalize_source_ref(source) for source in q.source_refs if source and source.strip()}
    )
    recency_weight = _recency_weight(q.latest_posted_at, ref)
    return QuestionRankScore(
        source_count=source_count,
        occurrence_count=q.freq,
        recency_weight=recency_weight,
        total=source_count * recency_weight,
    )


def dedupe_and_rank(questions: list[Question], today: date | None = None) -> list[Question]:
    """Merge questions by canonical intent and rank by source breadth and recency.

    Contract: callers pass one Question per occurrence with freq=1; this sums
    incoming freq, so passing pre-aggregated freqs will skew the occurrence
    tie-breaker. Independent source URLs determine the primary frequency score;
    occurrence count only breaks ties. Final ties keep first-seen order.
    """
    ref = today or date.today()
    merged: dict[str, Question] = {}
    order: list[str] = []
    for q in questions:
        key = normalize(q.canonical_text or q.text)
        if key not in merged:
            merged[key] = Question(
                text=q.text,
                source_refs=list(q.source_refs),
                freq=q.freq,
                latest_posted_at=q.latest_posted_at,
                role_tags=list(q.role_tags),
                topic=q.topic,
                modality_origin=q.modality_origin,
                canonical_text=q.canonical_text,
                evidence=list(q.evidence),
            )
            order.append(key)
        else:
            m = merged[key]
            m.freq += q.freq
            m.latest_posted_at = _max_date(m.latest_posted_at, q.latest_posted_at)
            _union(m.source_refs, q.source_refs)
            _union(m.role_tags, q.role_tags)
            _union(m.evidence, q.evidence)
            if not m.canonical_text and q.canonical_text:
                m.canonical_text = q.canonical_text

    def score(k: str) -> tuple[float, int]:
        q = merged[k]
        breakdown = question_rank_score(q, today=ref)
        return breakdown.total, breakdown.occurrence_count

    ranked = sorted(order, key=lambda k: tuple(-part for part in score(k)))
    return [merged[k] for k in ranked]
