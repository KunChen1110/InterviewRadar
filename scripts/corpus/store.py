import json
from pathlib import Path

from scripts.corpus.extraction import ExtractionCandidate, ExtractionDecision
from scripts.models import RawPost, Question


def save_raw_posts(posts: list[RawPost], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [p.to_dict() for p in posts]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_raw_posts(path) -> list[RawPost]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [RawPost.from_dict(d) for d in data]


def save_questions(questions: list[Question], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [q.to_dict() for q in questions]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_questions(path) -> list[Question]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Question.from_dict(d) for d in data]


def save_extraction_candidates(candidates: list[ExtractionCandidate], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [candidate.to_dict() for candidate in candidates]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_extraction_candidates(path) -> list[ExtractionCandidate]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ExtractionCandidate.from_dict(item) for item in data]


def save_extraction_decisions(decisions: list[ExtractionDecision], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = [decision.to_dict() for decision in decisions]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_extraction_decisions(path) -> list[ExtractionDecision]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ExtractionDecision.from_dict(item) for item in data]
