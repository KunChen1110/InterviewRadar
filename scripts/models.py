from dataclasses import dataclass, field, asdict, fields


@dataclass
class RawPost:
    source: str
    url: str
    post_type: str  # text | image | mixed
    raw_text: str
    posted_at: str | None = None  # ISO YYYY-MM-DD, or None if source has no date
    asset_paths: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    locator_text: str = ""
    content_text: str = ""
    image_ocr_text: str | None = None
    needs_vision_fallback: bool = False
    extraction_quality: str = "text_only"  # text_only | ocr_ok | ocr_low_quality

    def __post_init__(self) -> None:
        if not self.locator_text:
            self.locator_text = self.raw_text
        if not self.content_text:
            self.content_text = self.raw_text

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RawPost":
        data = dict(d)
        raw_text = data.get("raw_text") or data.get("content_text") or data.get("locator_text") or ""
        data.setdefault("raw_text", raw_text)
        data.setdefault("locator_text", raw_text)
        data.setdefault("content_text", raw_text)
        data.setdefault("image_ocr_text", None)
        data.setdefault("needs_vision_fallback", False)
        data.setdefault("extraction_quality", "text_only")
        data.setdefault("asset_paths", [])
        data.setdefault("comments", [])
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class QuestionEvidence:
    source_url: str
    excerpt: str
    posted_at: str | None = None
    modality_origin: str = "text"  # text | ocr | vision

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "QuestionEvidence":
        return cls(**d)


@dataclass
class Question:
    text: str
    source_refs: list[str] = field(default_factory=list)
    freq: int = 1
    latest_posted_at: str | None = None  # most recent posted_at among merged duplicates
    role_tags: list[str] = field(default_factory=list)
    topic: str = ""
    modality_origin: str = "text"  # text | ocr | vision
    canonical_text: str = ""  # short semantic intent used for cross-wording dedupe
    evidence: list[QuestionEvidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        data = dict(d)
        data["evidence"] = [
            item if isinstance(item, QuestionEvidence) else QuestionEvidence.from_dict(item)
            for item in data.get("evidence", [])
        ]
        return cls(**data)


@dataclass
class FollowUpChain:
    seed_question: str
    resume_anchor: str
    followups: list[str] = field(default_factory=list)
    is_grounded: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FollowUpChain":
        return cls(**d)
