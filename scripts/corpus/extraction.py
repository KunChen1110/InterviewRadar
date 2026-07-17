from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from scripts.corpus.dedupe_rank import normalize_source_ref
from scripts.models import RawPost


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
    return _INTERVIEW_PREFIX.sub("", _LIST_PREFIX.sub("", excerpt)).strip()


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
