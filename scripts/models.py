from dataclasses import dataclass, field, asdict


@dataclass
class RawPost:
    source: str
    url: str
    post_type: str  # text | image | mixed
    raw_text: str
    posted_at: str | None = None  # ISO YYYY-MM-DD, or None if source has no date
    asset_paths: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RawPost":
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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        return cls(**d)


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
