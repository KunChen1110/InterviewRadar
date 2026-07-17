from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile

from scripts.corpus.extraction import extract_candidates, materialize_questions
from scripts.corpus.quality import prepare_questions
from scripts.corpus.store import (
    load_extraction_decisions,
    load_raw_posts,
    save_extraction_candidates,
    save_extraction_decisions,
    save_questions,
    save_raw_posts,
)
from scripts.models import Question


_ARTIFACT_NAMES = (
    "raw_posts.json",
    "extraction_decisions.json",
    "extraction_candidates.json",
    "materialized_questions.json",
    "ranked_questions.json",
    "rejected_questions.json",
    "diagnostics.json",
)


@dataclass(frozen=True)
class PipelineRunResult:
    output_dir: Path
    manifest: dict[str, object]
    ranked_questions: list[Question]


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _parse_today(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--today must be an ISO calendar date such as 2026-07-17"
        ) from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError(
            "--today must be an ISO calendar date such as 2026-07-17"
        )
    return parsed


def _diagnostics(materialized, prepared) -> dict[str, object]:
    return {
        "materialization": {
            "rejected_decisions": [
                decision.to_dict() for decision in materialized.rejected_decisions
            ],
            "issues": [asdict(issue) for issue in materialized.issues],
        },
        "quality": {
            "issues": [asdict(issue) for issue in prepared.issues],
            "recency_counts": prepared.recency_counts,
        },
    }


def _manifest(
    input_sha256: dict[str, str],
    artifact_paths: dict[str, Path],
    raw_posts: list,
    candidates: list,
    decisions: list,
    materialized,
    prepared,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "input_sha256": input_sha256,
        "artifact_sha256": {
            name: _sha256(path) for name, path in artifact_paths.items()
        },
        "counts": {
            "raw_posts": len(raw_posts),
            "extraction_candidates": len(candidates),
            "extraction_decisions": len(decisions),
            "materialized_questions": len(materialized.questions),
            "ranked_questions": len(prepared.ranked_questions),
            "rejected_questions": len(prepared.rejected_questions),
            "rejected_decisions": len(materialized.rejected_decisions),
            "materialization_issues": len(materialized.issues),
            "quality_issues": len(prepared.issues),
        },
        "recency_counts": prepared.recency_counts,
    }


def _ensure_new_output_directory(output_dir: Path) -> None:
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"output directory already exists: {output_dir}")


def run_pipeline(
    raw_posts_path: Path,
    decisions_path: Path,
    output_dir: Path,
    *,
    today: date | None = None,
) -> PipelineRunResult:
    raw_posts_path = Path(raw_posts_path)
    decisions_path = Path(decisions_path)
    output_dir = Path(output_dir)
    _ensure_new_output_directory(output_dir)

    input_sha256 = {
        "raw_posts": _sha256(raw_posts_path),
        "extraction_decisions": _sha256(decisions_path),
    }
    raw_posts = load_raw_posts(raw_posts_path)
    decisions = load_extraction_decisions(decisions_path)
    candidates = extract_candidates(raw_posts)
    materialized = materialize_questions(candidates, decisions)
    prepared = prepare_questions(raw_posts, materialized.questions, today=today)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent)
    )
    try:
        save_raw_posts(raw_posts, stage_dir / "raw_posts.json")
        save_extraction_decisions(decisions, stage_dir / "extraction_decisions.json")
        save_extraction_candidates(candidates, stage_dir / "extraction_candidates.json")
        save_questions(materialized.questions, stage_dir / "materialized_questions.json")
        save_questions(prepared.ranked_questions, stage_dir / "ranked_questions.json")
        save_questions(prepared.rejected_questions, stage_dir / "rejected_questions.json")
        _write_json(stage_dir / "diagnostics.json", _diagnostics(materialized, prepared))

        artifact_paths = {name: stage_dir / name for name in _ARTIFACT_NAMES}
        manifest = _manifest(
            input_sha256,
            artifact_paths,
            raw_posts,
            candidates,
            decisions,
            materialized,
            prepared,
        )
        _write_json(stage_dir / "manifest.json", manifest)
        _ensure_new_output_directory(output_dir)
        stage_dir.rename(output_dir)
    except BaseException:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise

    return PipelineRunResult(
        output_dir=output_dir,
        manifest=manifest,
        ranked_questions=prepared.ranked_questions,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an auditable offline InterviewRadar corpus run."
    )
    parser.add_argument("--raw-posts", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--today", type=_parse_today)
    return parser


def _main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_pipeline(
        args.raw_posts,
        args.decisions,
        args.output,
        today=args.today,
    )
    print(f"wrote {len(result.ranked_questions)} ranked questions to {result.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

