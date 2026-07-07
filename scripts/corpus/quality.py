from collections import Counter
from dataclasses import dataclass, replace
from datetime import date

from scripts.corpus.dedupe_rank import dedupe_and_rank, normalize_source_ref
from scripts.corpus.recency import classify_recency
from scripts.models import Question, QuestionEvidence, RawPost


@dataclass(frozen=True)
class GroundingIssue:
    code: str
    question_text: str
    source_url: str = ""


@dataclass
class QuestionPreparationResult:
    ranked_questions: list[Question]
    rejected_questions: list[Question]
    issues: list[GroundingIssue]
    recency_counts: dict[str, int]


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _latest_date(evidence: list[QuestionEvidence]) -> str | None:
    dates = [item.posted_at for item in evidence if item.posted_at]
    return max(dates) if dates else None


def prepare_questions(
    raw_posts: list[RawPost],
    questions: list[Question],
    *,
    today: date | None = None,
    window_days: int = 730,
    keep_undated: bool = True,
    require_evidence: bool = True,
) -> QuestionPreparationResult:
    statuses = [
        classify_recency(post.posted_at, window_days=window_days, today=today)
        for post in raw_posts
    ]
    recency_counts = dict(Counter(statuses))

    all_posts: dict[str, list[RawPost]] = {}
    kept_posts: dict[str, list[RawPost]] = {}
    for post, status in zip(raw_posts, statuses, strict=True):
        key = normalize_source_ref(post.url)
        if not key:
            continue
        all_posts.setdefault(key, []).append(post)
        if status == "recent" or (status == "undated" and keep_undated):
            kept_posts.setdefault(key, []).append(post)

    accepted: list[Question] = []
    rejected: list[Question] = []
    issues: list[GroundingIssue] = []

    for question in questions:
        if not question.evidence:
            if require_evidence:
                rejected.append(question)
                issues.append(GroundingIssue("missing_evidence", question.text))
                continue

            legacy_posts = [
                post
                for source in question.source_refs
                for post in kept_posts.get(normalize_source_ref(source), [])
            ]
            if not legacy_posts:
                rejected.append(question)
                known_source = any(
                    normalize_source_ref(source) in all_posts
                    for source in question.source_refs
                )
                code = "source_outside_recency" if known_source else "source_missing"
                issues.append(GroundingIssue(code, question.text))
                continue
            legacy_dates = [post.posted_at for post in legacy_posts if post.posted_at]
            accepted.append(
                replace(
                    question,
                    source_refs=_unique([post.url for post in legacy_posts]),
                    latest_posted_at=max(legacy_dates) if legacy_dates else None,
                )
            )
            issues.append(GroundingIssue("legacy_unverified", question.text))
            continue

        valid_evidence: list[QuestionEvidence] = []
        for evidence in question.evidence:
            key = normalize_source_ref(evidence.source_url)
            if not key or key not in all_posts:
                issues.append(
                    GroundingIssue("source_missing", question.text, evidence.source_url)
                )
                continue
            if key not in kept_posts:
                issues.append(
                    GroundingIssue(
                        "source_outside_recency",
                        question.text,
                        evidence.source_url,
                    )
                )
                continue

            excerpt = _normalized_text(evidence.excerpt)
            if not excerpt:
                issues.append(
                    GroundingIssue("empty_excerpt", question.text, evidence.source_url)
                )
                continue

            matched_post = next(
                (
                    post
                    for post in kept_posts[key]
                    if excerpt in _normalized_text(post.content_text or post.raw_text)
                ),
                None,
            )
            if matched_post is None:
                issues.append(
                    GroundingIssue(
                        "excerpt_not_found",
                        question.text,
                        evidence.source_url,
                    )
                )
                continue

            valid_evidence.append(
                QuestionEvidence(
                    source_url=matched_post.url,
                    excerpt=evidence.excerpt.strip(),
                    posted_at=matched_post.posted_at,
                    modality_origin=evidence.modality_origin,
                )
            )

        if not valid_evidence:
            rejected.append(question)
            continue

        accepted.append(
            replace(
                question,
                source_refs=_unique([item.source_url for item in valid_evidence]),
                latest_posted_at=_latest_date(valid_evidence),
                evidence=valid_evidence,
            )
        )

    return QuestionPreparationResult(
        ranked_questions=dedupe_and_rank(accepted, today=today),
        rejected_questions=rejected,
        issues=issues,
        recency_counts=recency_counts,
    )
