from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
import re

from scripts.corpus.dedupe_rank import normalize_source_ref
from scripts.models import Question, QuestionEvidence, RawPost


_LIST_PREFIX = re.compile(r"^(?:\d+|[一二三四五六七八九十]+)[.、)）]\s*")
_QUESTION_START = re.compile(
    r"^(?:\d+[.、)）]\s*)?(?:什么是|如何|怎么|为什么|介绍(?:一下)?|解释|谈谈|区别|是否|有没有|能否)"
)
_QUESTION_PUNCTUATION = re.compile(r"[?？]")
_INTERVIEW_CONTEXT = ("面试官", "一面", "二面", "三面", "面经", "被问", "问题", "追问")
_INTERVIEW_PREFIX = re.compile(r"^(?:面试官(?:问(?:了)?|提问)|追问)[:：]\s*")


@dataclass(frozen=True)
class ExtractionCandidate:
    candidate_id: str
    source_url: str
    excerpt: str
    display_text: str
    posted_at: str | None = None
    modality_origin: str = "text"

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "source_url": self.source_url,
            "excerpt": self.excerpt,
            "display_text": self.display_text,
            "posted_at": self.posted_at,
            "modality_origin": self.modality_origin,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractionCandidate":
        return cls(**data)


def _display_text(excerpt: str) -> str:
    display_text = excerpt.strip()
    while True:
        cleaned = _LIST_PREFIX.sub("", _INTERVIEW_PREFIX.sub("", display_text)).strip()
        if cleaned == display_text:
            return cleaned
        display_text = cleaned


def _candidate_id(source_url: str, line_number: int, excerpt: str) -> str:
    payload = "\0".join((normalize_source_ref(source_url), str(line_number), excerpt))
    return "candidate_" + sha256(payload.encode("utf-8")).hexdigest()[:16]


def _modality_origin(post: RawPost, excerpt: str) -> str:
    ocr_text = " ".join((post.image_ocr_text or "").split())
    normalized_excerpt = " ".join(excerpt.split())
    if ocr_text and normalized_excerpt in ocr_text:
        return "ocr"
    if post.needs_vision_fallback:
        return "vision"
    return "text"


def _looks_like_question(line: str, context_remaining: int) -> bool:
    if _QUESTION_PUNCTUATION.search(line) or _QUESTION_START.match(line):
        return True
    return bool(context_remaining and _LIST_PREFIX.match(line))


def extract_candidates(raw_posts: list[RawPost]) -> list[ExtractionCandidate]:
    candidates: list[ExtractionCandidate] = []
    for post in raw_posts:
        body = post.content_text or post.raw_text
        context_remaining = 0
        for line_number, raw_line in enumerate(body.splitlines()):
            excerpt = raw_line.strip()
            if not excerpt:
                context_remaining = 0
                continue
            if _looks_like_question(excerpt, context_remaining):
                candidates.append(
                    ExtractionCandidate(
                        candidate_id=_candidate_id(post.url, line_number, excerpt),
                        source_url=post.url,
                        excerpt=excerpt,
                        display_text=_display_text(excerpt),
                        posted_at=post.posted_at,
                        modality_origin=_modality_origin(post, excerpt),
                    )
                )
            if any(marker in excerpt for marker in _INTERVIEW_CONTEXT):
                context_remaining = 3
            elif context_remaining:
                context_remaining -= 1
    return candidates


@dataclass
class ExtractionDecision:
    candidate_id: str
    accepted: bool
    canonical_text: str = ""
    topic: str = ""
    role_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "accepted": self.accepted,
            "canonical_text": self.canonical_text,
            "topic": self.topic,
            "role_tags": self.role_tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractionDecision":
        return cls(
            candidate_id=data.get("candidate_id", ""),
            accepted=data.get("accepted", False),
            canonical_text=data.get("canonical_text", ""),
            topic=data.get("topic", ""),
            role_tags=data.get("role_tags", []),
        )


@dataclass(frozen=True)
class ExtractionIssue:
    code: str
    candidate_id: str = ""


@dataclass
class ExtractionMaterializationResult:
    questions: list[Question]
    rejected_decisions: list[ExtractionDecision]
    issues: list[ExtractionIssue]


def materialize_questions(
    candidates: list[ExtractionCandidate],
    decisions: list[ExtractionDecision],
) -> ExtractionMaterializationResult:
    candidate_counts = Counter(candidate.candidate_id for candidate in candidates)
    duplicate_ids = {
        candidate_id for candidate_id, count in candidate_counts.items() if count > 1
    }
    issues = [
        ExtractionIssue("duplicate_candidate_id", candidate_id)
        for candidate_id in sorted(duplicate_ids)
    ]
    candidate_map = {
        candidate.candidate_id: candidate
        for candidate in candidates
        if candidate.candidate_id not in duplicate_ids
    }
    questions: list[Question] = []
    rejected: list[ExtractionDecision] = []
    seen_ids: set[str] = set()

    for decision in decisions:
        candidate_id = decision.candidate_id
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            issues.append(ExtractionIssue("invalid_decision_candidate_id"))
            rejected.append(decision)
            continue
        if candidate_id in seen_ids:
            issues.append(ExtractionIssue("duplicate_decision", candidate_id))
            rejected.append(decision)
            continue
        seen_ids.add(candidate_id)
        candidate = candidate_map.get(candidate_id)
        if candidate is None:
            issues.append(ExtractionIssue("unknown_candidate", candidate_id))
            rejected.append(decision)
            continue
        if not isinstance(decision.accepted, bool):
            issues.append(ExtractionIssue("invalid_accepted", candidate_id))
            rejected.append(decision)
            continue
        if not decision.accepted:
            rejected.append(decision)
            continue
        if not isinstance(decision.canonical_text, str) or not decision.canonical_text.strip():
            issues.append(ExtractionIssue("missing_canonical_text", candidate_id))
            rejected.append(decision)
            continue
        if (
            not isinstance(decision.role_tags, list)
            or any(not isinstance(tag, str) or not tag.strip() for tag in decision.role_tags)
        ):
            issues.append(ExtractionIssue("invalid_role_tags", candidate_id))
            rejected.append(decision)
            continue
        if (
            not candidate.source_url.strip()
            or not candidate.excerpt.strip()
            or not candidate.display_text.strip()
        ):
            issues.append(ExtractionIssue("invalid_candidate", candidate_id))
            rejected.append(decision)
            continue

        evidence = QuestionEvidence(
            source_url=candidate.source_url,
            excerpt=candidate.excerpt,
            posted_at=candidate.posted_at,
            modality_origin=candidate.modality_origin,
        )
        questions.append(
            Question(
                text=candidate.display_text,
                source_refs=[candidate.source_url],
                latest_posted_at=candidate.posted_at,
                role_tags=[tag.strip() for tag in decision.role_tags],
                topic=decision.topic.strip() if isinstance(decision.topic, str) else "",
                modality_origin=candidate.modality_origin,
                canonical_text=decision.canonical_text.strip(),
                evidence=[evidence],
            )
        )

    for candidate_id in candidate_map:
        if candidate_id not in seen_ids:
            issues.append(ExtractionIssue("missing_decision", candidate_id))

    return ExtractionMaterializationResult(questions, rejected, issues)
