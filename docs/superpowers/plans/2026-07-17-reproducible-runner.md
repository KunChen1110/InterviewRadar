# Reproducible Corpus Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build an offline deterministic runner that packages evidence-first extraction inputs, intermediate artifacts, diagnostics, and ranked questions into an auditable immutable run directory.

**Architecture:** scripts/corpus/runner.py composes the existing store, extraction, and quality modules without duplicating their domain rules. It writes canonical artifacts to a sibling staging directory, hashes finalized artifacts into a versioned manifest, then publishes a fresh destination directory. All end-to-end tests use local RawPost and ExtractionDecision fixtures only.

**Tech Stack:** Python 3.11+, argparse, dataclasses, datetime, hashlib, json, pathlib, shutil, pytest, GitHub Actions.

---

> **Implementation status:** Complete. The task code blocks below preserve the
> original test-first plan. When they conflict with the post-review corrections,
> they are historical only and must not be used as an implementation reference.

## Post-Review Corrections

The initial staging-and-rename sketch had a destination race and read each
input twice. The implemented runner instead atomically reserves the output
directory with `mkdir()`, removes that owned directory on failure, snapshots
each input once before hashing and parsing, writes the effective `today` value
to `manifest.json`, and reports every extracted candidate lacking a decision as
`missing_decision`. These changes preserve the plan's public artifact contract
while closing integrity gaps found during review.

---

## File Structure

- Create: scripts/corpus/runner.py
  - PipelineRunResult, stable JSON/hash helpers, safe staging, run_pipeline, and CLI.
- Create: tests/test_runner.py
  - Full run package, hash integrity, replay determinism, stale diagnostics, no-overwrite, and date parsing.
- Modify: README.md:273-281
  - Record the real scope of completed Plan 9.
- Modify: SKILL.md:23-27,59-70
  - Make the runner the explicit handoff from decisions to preparation.
- Modify: .github/workflows/tests.yml:25-26
  - Compile scripts in every existing Python matrix entry.
- Create: docs/superpowers/plans/2026-07-17-reproducible-runner.md
  - This plan.

### Task 1: Define runner behavior with failing tests

**Files:**
- Create: tests/test_runner.py
- Reference: scripts/corpus/store.py
- Reference: scripts/corpus/extraction.py
- Reference: scripts/corpus/quality.py

- [ ] **Step 1: Write a complete successful-run contract test**

~~~python
from datetime import date
from hashlib import sha256
import json

from scripts.corpus.extraction import ExtractionDecision, extract_candidates
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
        raw_text="面试官主要问：\\n1. 如何评估 RAG 系统效果？",
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
~~~

- [ ] **Step 2: Run the focused test in red state**

Run:

~~~bash
/Users/kun/Desktop/Projects/InterviewRadar/.venv/bin/python -m pytest tests/test_runner.py::test_run_pipeline_writes_auditable_package -v
~~~

Expected: collection fails because scripts.corpus.runner does not exist.

- [ ] **Step 3: Add deterministic replay, stale-source, safety, and parser tests**

~~~python
import pytest

from scripts.corpus import runner


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
    assert diagnostics["quality"]["issues"][0]["code"] == "source_outside_recency"


def test_existing_destination_is_never_overwritten(tmp_path):
    raw_posts_path, decisions_path = _inputs(tmp_path)
    output_dir = tmp_path / "runs" / "occupied"
    output_dir.mkdir(parents=True)
    sentinel = output_dir / "keep.txt"
    sentinel.write_text("do not replace", encoding="utf-8")

    with pytest.raises(FileExistsError, match="output directory already exists"):
        runner.run_pipeline(raw_posts_path, decisions_path, output_dir, today=TODAY)

    assert sentinel.read_text(encoding="utf-8") == "do not replace"


def test_parse_today_accepts_only_iso_calendar_dates():
    assert runner._parse_today("2026-07-17") == TODAY
    with pytest.raises(Exception):
        runner._parse_today("2026/07/17")
~~~

- [ ] **Step 4: Run all new tests before implementing code**

Run:

~~~bash
/Users/kun/Desktop/Projects/InterviewRadar/.venv/bin/python -m pytest tests/test_runner.py -v
~~~

Expected: collection fails for the missing module. Do not alter extraction or quality
tests to compensate.

### Task 2: Implement the deterministic orchestration module

**Files:**
- Create: scripts/corpus/runner.py
- Test: tests/test_runner.py

- [ ] **Step 1: Add imports, result type, and stable utility functions**

~~~python
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


@dataclass(frozen=True)
class PipelineRunResult:
    output_dir: Path
    manifest: dict[str, object]
    ranked_questions: list


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
~~~

Use only existing typed store writers for RawPost, ExtractionDecision,
ExtractionCandidate, and Question lists. Use dataclasses.asdict for issue
objects and decision.to_dict for rejected reviewer decisions.

- [ ] **Step 2: Add canonical diagnostics and manifest builders**

~~~python
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
    input_sha256,
    artifact_paths,
    raw_posts,
    candidates,
    decisions,
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
~~~

Write the seven non-manifest artifacts in fixed filename order, calculate their
actual byte hashes, then write manifest.json. Do not hash manifest.json itself;
that would make the manifest self-referential. Do not include input paths,
absolute paths, timestamps, or random values in generated JSON.

- [ ] **Step 3: Add run_pipeline with staging and no-overwrite protection**

> **Superseded during review:** This staging-and-rename sketch has a
> check-then-rename race. The final implementation atomically reserves
> `output_dir` with `mkdir()`, writes artifacts there, and removes that owned
> directory on failure. See the Post-Review Corrections section and
> `scripts/corpus/runner.py` for the authoritative behavior.

~~~python
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
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f"output directory already exists: {output_dir}")

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

        artifact_names = (
            "raw_posts.json",
            "extraction_decisions.json",
            "extraction_candidates.json",
            "materialized_questions.json",
            "ranked_questions.json",
            "rejected_questions.json",
            "diagnostics.json",
        )
        manifest = _manifest(
            input_sha256,
            {name: stage_dir / name for name in artifact_names},
            raw_posts,
            candidates,
            decisions,
            materialized,
            prepared,
        )
        _write_json(stage_dir / "manifest.json", manifest)
        stage_dir.rename(output_dir)
    except BaseException:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise

    return PipelineRunResult(output_dir, manifest, prepared.ranked_questions)
~~~

This function must call extract_candidates, materialize_questions, and
prepare_questions once. It must not import connectors, browser code, LLM code,
resume code, or preparation prose code. A failed run removes only its staging
directory; it never modifies an existing destination.

- [ ] **Step 4: Add the module CLI**

~~~python
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
~~~

- [ ] **Step 5: Run focused and regression checks**

Run:

~~~bash
/Users/kun/Desktop/Projects/InterviewRadar/.venv/bin/python -m pytest tests/test_runner.py -v
/Users/kun/Desktop/Projects/InterviewRadar/.venv/bin/python -m pytest tests/ -q
~~~

Expected: runner tests and the existing suite pass. If an assertion fails,
identify the mismatch in the package contract rather than weakening evidence or
recency checks.

- [ ] **Step 6: Commit implementation and tests**

~~~bash
git add scripts/corpus/runner.py tests/test_runner.py
git commit -m "feat: add reproducible corpus runner"
~~~

### Task 3: Document the handoff and add CI compilation

**Files:**
- Modify: README.md:273-281
- Modify: SKILL.md:23-27,59-70
- Modify: .github/workflows/tests.yml:25-26
- Test: tests/test_runner.py

- [ ] **Step 1: Update the Plan 9 roadmap item**

Replace it with:

~~~markdown
- [x] **Plan 9:可复放语料 runner + CI**:输入已归一化的 raw_posts.json 和显式 extraction_decisions.json,一次生成带 SHA-256 manifest 的独立运行包（候选、落题、排序题、拒绝项和诊断）。它不隐藏浏览器采集、Agent 判断或最终备考文案，正式包只消费 ranked_questions.json。
~~~

Keep Plan 10 and Golden Set evaluation unchecked. Do not claim resume-to-web
automation.

- [ ] **Step 2: Add the runner to SKILL.md and define the command boundary**

Add this module map entry:

~~~markdown
- scripts/corpus/runner.py → run_pipeline(raw_posts_path, decisions_path, output_dir, today=None) -> PipelineRunResult（离线、可复放地生成输入副本、候选、落题、排序题、拒绝项、诊断和 SHA-256 manifest）
~~~

After the decision and quality sections add:

~~~text
python -m scripts.corpus.runner \
  --raw-posts corpus_cache/raw_posts.json \
  --decisions corpus_cache/extraction_decisions.json \
  --output corpus_cache/runs/<本次标识> \
  --today YYYY-MM-DD
~~~

State that output must be a new directory, diagnostics.json must be inspected
for invalid decisions, failed grounding, and stale sources, and downstream
preparation may consume only output/ranked_questions.json. The runner must not
be represented as search, crawler, resume, reviewer, or final-writing
automation.

- [ ] **Step 3: Add compileall to the existing CI matrix**

Change the final workflow steps to:

~~~yaml
      - name: Compile scripts
        run: python -m compileall -q scripts

      - name: Run tests
        run: python -m pytest tests/ -v
~~~

Do not add network-backed tests or a separate workflow.

- [ ] **Step 4: Verify final behavior and patch quality**

Run:

~~~bash
/Users/kun/Desktop/Projects/InterviewRadar/.venv/bin/python -m compileall -q scripts
/Users/kun/Desktop/Projects/InterviewRadar/.venv/bin/python -m pytest tests/ -q
git diff --check
~~~

Expected: compilation exits zero, every test passes, and no whitespace errors
are reported.

- [ ] **Step 5: Commit docs, CI, and plan**

~~~bash
git add README.md SKILL.md .github/workflows/tests.yml docs/superpowers/plans/2026-07-17-reproducible-runner.md
git commit -m "docs: document reproducible corpus runs"
~~~

### Task 4: Review, integrate, and publish

**Files:**
- Review: scripts/corpus/runner.py
- Review: tests/test_runner.py
- Review: README.md
- Review: SKILL.md
- Review: .github/workflows/tests.yml

- [ ] **Step 1: Review package invariants against the design spec**

Confirm all of the following before integration:

~~~text
- No browser, connector, LLM, resume, or preparation-prose import exists in runner.py.
- The runner delegates extraction, materialization, and quality filtering to existing modules.
- ranked_questions.json is the only downstream question artifact.
- Input and artifact digests are calculated from actual file bytes.
- manifest.json has no timestamp, absolute path, random value, or self-hash.
- Existing output paths are rejected and never removed.
- Staging output is removed after processing or write failures.
~~~

- [ ] **Step 2: Request a code review**

Request review focused on data-integrity regressions, path safety, deterministic
serialization, error cleanup, and diagnostic completeness. Turn each confirmed
finding into a targeted regression test before changing implementation.

- [ ] **Step 3: Run final branch verification**

Run:

~~~bash
/Users/kun/Desktop/Projects/InterviewRadar/.venv/bin/python -m compileall -q scripts
/Users/kun/Desktop/Projects/InterviewRadar/.venv/bin/python -m pytest tests/ -q
git status --short
git log --oneline main..HEAD
~~~

Expected: compilation and tests pass; the branch contains only focused plan,
implementation, and documentation changes.

- [ ] **Step 4: Merge and push after successful final verification**

~~~bash
git switch main
git merge --no-ff codex/reproducible-runner -m "feat: add reproducible corpus runner"
git push origin main
~~~

Remove the isolated worktree only after the remote push completes. Preserve any
unrelated root-worktree files.
