from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from threading import Barrier

import pytest

from scripts.corpus.extraction import ExtractionDecision, extract_candidates
from scripts.corpus import runner
from scripts.corpus.runner import run_pipeline
from scripts.corpus.store import (
    load_questions,
    save_extraction_decisions,
    save_raw_posts,
)
from scripts.models import RawPost


TODAY = date(2026, 7, 17)


def _post(*, posted_at: str = "2026-06-01") -> RawPost:
    return RawPost(
        source="fixture",
        url="https://example.com/interview-radar",
        post_type="text",
        raw_text="面试官主要问：\n1. 如何评估 RAG 系统效果？",
        posted_at=posted_at,
    )


def _inputs(tmp_path, *, posted_at: str = "2026-06-01"):
    raw_posts_path = tmp_path / "raw_posts_input.json"
    decisions_path = tmp_path / "decisions_input.json"
    post = _post(posted_at=posted_at)
    candidate = extract_candidates([post])[0]
    save_raw_posts([post], raw_posts_path)
    save_extraction_decisions(
        [
            ExtractionDecision(
                candidate_id=candidate.candidate_id,
                accepted=True,
                canonical_text="评估 RAG 系统效果",
                topic="RAG",
                role_tags=["AI 应用开发"],
            )
        ],
        decisions_path,
    )
    return raw_posts_path, decisions_path


def _sha256(path):
    return sha256(path.read_bytes()).hexdigest()


def test_run_pipeline_writes_auditable_package(tmp_path):
    raw_posts_path, decisions_path = _inputs(tmp_path)
    output_dir = tmp_path / "runs" / "fixture"

    result = run_pipeline(raw_posts_path, decisions_path, output_dir, today=TODAY)

    assert {path.name for path in output_dir.iterdir()} == {
        "raw_posts.json",
        "extraction_decisions.json",
        "extraction_candidates.json",
        "materialized_questions.json",
        "ranked_questions.json",
        "rejected_questions.json",
        "diagnostics.json",
        "manifest.json",
    }
    assert result.output_dir == output_dir
    assert [item.canonical_text for item in result.ranked_questions] == [
        "评估 RAG 系统效果"
    ]

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["run_config"] == {"today": "2026-07-17"}
    assert manifest["input_sha256"] == {
        "raw_posts": _sha256(raw_posts_path),
        "extraction_decisions": _sha256(decisions_path),
    }
    assert manifest["counts"] == {
        "raw_posts": 1,
        "extraction_candidates": 1,
        "extraction_decisions": 1,
        "materialized_questions": 1,
        "ranked_questions": 1,
        "rejected_questions": 0,
        "rejected_decisions": 0,
        "materialization_issues": 0,
        "quality_issues": 0,
    }
    assert manifest["recency_counts"] == {"recent": 1}
    for filename, digest in manifest["artifact_sha256"].items():
        assert digest == _sha256(output_dir / filename)

    assert load_questions(output_dir / "ranked_questions.json") == result.ranked_questions


def test_fixed_inputs_and_today_produce_byte_identical_artifacts(tmp_path):
    raw_posts_path, decisions_path = _inputs(tmp_path)
    first = tmp_path / "runs" / "first"
    second = tmp_path / "runs" / "second"

    runner.run_pipeline(raw_posts_path, decisions_path, first, today=TODAY)
    runner.run_pipeline(raw_posts_path, decisions_path, second, today=TODAY)

    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }


def test_stale_question_is_diagnostic_not_ranked(tmp_path):
    raw_posts_path, decisions_path = _inputs(tmp_path, posted_at="2020-01-01")
    output_dir = tmp_path / "runs" / "stale"

    result = runner.run_pipeline(raw_posts_path, decisions_path, output_dir, today=TODAY)

    diagnostics = json.loads((output_dir / "diagnostics.json").read_text(encoding="utf-8"))
    assert result.ranked_questions == []
    assert len(load_questions(output_dir / "rejected_questions.json")) == 1
    assert diagnostics["quality"]["recency_counts"] == {"stale": 1}
    assert diagnostics["quality"]["issues"] == [
        {
            "code": "source_outside_recency",
            "question_text": "如何评估 RAG 系统效果？",
            "source_url": "https://example.com/interview-radar",
        }
    ]


def test_existing_destination_is_never_overwritten(tmp_path):
    raw_posts_path, decisions_path = _inputs(tmp_path)
    output_dir = tmp_path / "runs" / "occupied"
    output_dir.mkdir(parents=True)
    sentinel = output_dir / "keep.txt"
    sentinel.write_text("do not replace", encoding="utf-8")

    with pytest.raises(FileExistsError, match="output directory already exists"):
        runner.run_pipeline(raw_posts_path, decisions_path, output_dir, today=TODAY)

    assert sentinel.read_text(encoding="utf-8") == "do not replace"


def test_reserving_output_directory_is_atomic(tmp_path):
    output_dir = tmp_path / "runs" / "reserved"

    runner._reserve_output_directory(output_dir)

    assert output_dir.is_dir()
    with pytest.raises(FileExistsError, match="output directory already exists"):
        runner._reserve_output_directory(output_dir)


def test_concurrent_runs_allow_only_one_output_reservation(tmp_path):
    raw_posts_path, decisions_path = _inputs(tmp_path)
    output_dir = tmp_path / "runs" / "contended"
    barrier = Barrier(2)

    def run_once():
        barrier.wait()
        try:
            runner.run_pipeline(raw_posts_path, decisions_path, output_dir, today=TODAY)
        except FileExistsError:
            return "already_exists"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: run_once(), range(2)))

    assert sorted(outcomes) == ["already_exists", "created"]
    assert (output_dir / "manifest.json").is_file()


def test_pipeline_parses_the_same_input_snapshot_that_it_hashes(tmp_path, monkeypatch):
    raw_posts_path, decisions_path = _inputs(tmp_path)
    original_hash = _sha256(raw_posts_path)
    original_read_bytes = Path.read_bytes

    def read_then_replace_source(path):
        snapshot = original_read_bytes(path)
        if path == raw_posts_path:
            save_raw_posts(
                [
                    RawPost(
                        source="fixture",
                        url="https://example.com/replaced",
                        post_type="text",
                        raw_text="面试官主要问：\\n1. 如何设计 Agent 记忆？",
                        posted_at="2026-06-01",
                    )
                ],
                path,
            )
        return snapshot

    monkeypatch.setattr(Path, "read_bytes", read_then_replace_source)
    output_dir = tmp_path / "runs" / "snapshot"

    result = runner.run_pipeline(raw_posts_path, decisions_path, output_dir, today=TODAY)

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["input_sha256"]["raw_posts"] == original_hash
    assert [question.canonical_text for question in result.ranked_questions] == [
        "评估 RAG 系统效果"
    ]


def test_parse_today_accepts_only_iso_calendar_dates():
    assert runner._parse_today("2026-07-17") == TODAY

    with pytest.raises(Exception):
        runner._parse_today("2026/07/17")
