# Evidence-First Question Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable source-candidate-to-grounded-question pipeline that makes semantic decisions auditable and prevents agent-written evidence or display text from entering the ranked corpus.

**Architecture:** `scripts/corpus/extraction.py` owns small serializable candidate and decision records, deterministic candidate segmentation, and fail-closed materialization. The agent writes only acceptance, canonical intent, topic, and role tags. Materialization derives both `Question.text` and `QuestionEvidence` from the immutable candidate, then the existing `prepare_questions()` gate handles recency and ranking.

**Tech Stack:** Python 3.11+, dataclasses, JSON, pytest; no network or LLM-provider dependency.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `scripts/corpus/extraction.py` | Candidate/decision schemas, deterministic extraction, safe materialization. |
| `scripts/corpus/store.py` | JSON persistence for the two new schemas. |
| `tests/test_question_extraction.py` | Candidate, materialization, and pipeline contracts. |
| `tests/test_store.py` | Candidate and decision JSON round trips. |
| `SKILL.md` | Agent workflow and decision JSON contract. |
| `README.md` | Project structure and Plan 8 status. |
| `assets/schema.md` | Public data-schema documentation. |

### Task 1: Extract Immutable Question Candidates

**Files:**
- Create: `scripts/corpus/extraction.py`
- Create: `tests/test_question_extraction.py`

- [x] **Step 1: Write the failing candidate-extraction tests**

```python
from scripts.corpus.extraction import extract_candidates
from scripts.models import RawPost


def _post(text: str, post_type: str = "text", **kwargs) -> RawPost:
    return RawPost(
        source="nowcoder",
        url="https://example.com/post-1",
        post_type=post_type,
        raw_text=text,
        posted_at="2026-06-01",
        **kwargs,
    )


def test_extract_candidates_keeps_source_lines_and_removes_only_display_prefixes():
    post = _post(
        "面试官主要问：\n"
        "1. 介绍一下你做的 RAG 项目\n"
        "2. RAG 系统如何评估效果？\n"
        "最后聊了薪资和入职时间。"
    )

    candidates = extract_candidates([post])

    assert [item.excerpt for item in candidates] == [
        "1. 介绍一下你做的 RAG 项目",
        "2. RAG 系统如何评估效果？",
    ]
    assert [item.display_text for item in candidates] == [
        "介绍一下你做的 RAG 项目",
        "RAG 系统如何评估效果？",
    ]
    assert [item.source_url for item in candidates] == [post.url, post.url]
    assert [item.posted_at for item in candidates] == ["2026-06-01", "2026-06-01"]


def test_extract_candidates_skips_plain_narrative_and_is_stable():
    post = _post("今天准备了一下午资料，最后聊了薪资和入职时间。")
    question = _post("你如何评估招聘渠道？")

    assert extract_candidates([post]) == []
    first = extract_candidates([question])
    second = extract_candidates([question])
    assert [item.candidate_id for item in first] == [item.candidate_id for item in second]


def test_extract_candidates_derives_modality_from_raw_post_content():
    text = _post("你如何评估招聘渠道？")
    ocr = _post(
        "1. 介绍一下 RAG 项目",
        post_type="image",
        image_ocr_text="1. 介绍一下 RAG 项目",
        content_text="1. 介绍一下 RAG 项目",
    )
    vision = _post(
        "1. 介绍一下 Agent 项目",
        post_type="image",
        needs_vision_fallback=True,
    )

    assert [item.modality_origin for item in extract_candidates([text, ocr, vision])] == [
        "text",
        "ocr",
        "vision",
    ]
```

- [x] **Step 2: Run the candidate tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/test_question_extraction.py -q`

Expected: FAIL during collection because `scripts.corpus.extraction` does not exist.

- [x] **Step 3: Implement candidate schemas and extraction**

Create `scripts/corpus/extraction.py` with the following contracts. The hash input
must use the normalized URL, the original source-line ordinal, and the exact
trimmed excerpt so IDs are repeatable and do not depend on runtime state.

```python
from __future__ import annotations

from dataclasses import dataclass, field
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
    if _QUESTION_PUNCTUATION.search(line):
        return True
    if context_remaining and _LIST_PREFIX.match(line):
        return True
    return bool(context_remaining and _QUESTION_START.match(line))


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
```

- [x] **Step 4: Run the candidate tests to verify they pass**

Run: `../../.venv/bin/python -m pytest tests/test_question_extraction.py -q`

Expected: `3 passed`.

- [x] **Step 5: Commit the extraction foundation**

```bash
git add scripts/corpus/extraction.py tests/test_question_extraction.py
git commit -m "feat: extract immutable question candidates"
```

### Task 2: Materialize Questions From Constrained Decisions

**Files:**
- Modify: `scripts/corpus/extraction.py`
- Modify: `tests/test_question_extraction.py`

- [x] **Step 1: Add failing materialization tests**

Append these tests to `tests/test_question_extraction.py`:

```python
from scripts.corpus.extraction import (
    ExtractionCandidate,
    ExtractionDecision,
    extract_candidates,
    materialize_questions,
)


def test_materialize_uses_candidate_text_and_immutable_evidence():
    post = _post("面试官主要问：\n1. 如何评估招聘渠道？")
    candidate = extract_candidates([post])[0]
    decision = ExtractionDecision(
        candidate_id=candidate.candidate_id,
        accepted=True,
        canonical_text="评估招聘渠道",
        topic="招聘",
        role_tags=["市场实习"],
    )

    result = materialize_questions([candidate], [decision])

    assert result.issues == []
    assert result.rejected_decisions == []
    assert len(result.questions) == 1
    question = result.questions[0]
    assert question.text == "如何评估招聘渠道？"
    assert question.canonical_text == "评估招聘渠道"
    assert question.evidence[0].excerpt == "1. 如何评估招聘渠道？"
    assert question.evidence[0].source_url == post.url
    assert question.evidence[0].modality_origin == "text"


def test_materialize_rejects_invalid_or_ambiguous_decisions_without_raising():
    candidate = ExtractionCandidate(
        candidate_id="candidate_1",
        source_url="https://example.com/post-1",
        excerpt="如何评估招聘渠道？",
        display_text="如何评估招聘渠道？",
    )
    invalid = [
        ExtractionDecision("missing", True, canonical_text="未知"),
        ExtractionDecision("candidate_1", True, canonical_text=""),
        ExtractionDecision("candidate_1", True, canonical_text="评估招聘渠道"),
    ]

    result = materialize_questions([candidate], invalid)

    assert result.questions == []
    assert [issue.code for issue in result.issues] == [
        "unknown_candidate",
        "missing_canonical_text",
        "duplicate_decision",
    ]
    assert result.rejected_decisions == invalid


def test_materialize_rejects_duplicate_candidates_without_raising():
    candidate = ExtractionCandidate(
        candidate_id="candidate_1",
        source_url="https://example.com/post-1",
        excerpt="如何评估招聘渠道？",
        display_text="如何评估招聘渠道？",
    )
    decision = ExtractionDecision("candidate_1", True, canonical_text="评估招聘渠道")

    result = materialize_questions([candidate, candidate], [decision])

    assert result.questions == []
    assert [issue.code for issue in result.issues] == [
        "duplicate_candidate_id",
        "unknown_candidate",
    ]


def test_materialize_rejects_bad_role_tags():
    candidate = ExtractionCandidate(
        candidate_id="candidate_1",
        source_url="https://example.com/post-1",
        excerpt="如何评估招聘渠道？",
        display_text="如何评估招聘渠道？",
    )
    decision = ExtractionDecision(
        "candidate_1", True, canonical_text="评估招聘渠道", role_tags=["市场", ""]
    )

    result = materialize_questions([candidate], [decision])

    assert result.questions == []
    assert [issue.code for issue in result.issues] == ["invalid_role_tags"]
```

- [x] **Step 2: Run the materialization tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/test_question_extraction.py -q`

Expected: FAIL because `ExtractionDecision` and `materialize_questions` are not defined.

- [x] **Step 3: Implement decision schemas, diagnostics, and materialization**

Append the following definitions to `scripts/corpus/extraction.py`. `rejected_decisions`
must retain the original decision instances in input order so callers can write a
complete diagnostics artifact.

```python
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
    duplicate_ids = {
        candidate.candidate_id
        for candidate in candidates
        if sum(item.candidate_id == candidate.candidate_id for item in candidates) > 1
    }
    issues = [ExtractionIssue("duplicate_candidate_id", candidate_id) for candidate_id in sorted(duplicate_ids)]
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
        if not candidate.source_url.strip() or not candidate.excerpt.strip() or not candidate.display_text.strip():
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
    return ExtractionMaterializationResult(questions, rejected, issues)
```

Add these imports at the top of `scripts/corpus/extraction.py`:

```python
from scripts.models import Question, QuestionEvidence, RawPost
```

- [x] **Step 4: Run the materialization tests to verify they pass**

Run: `../../.venv/bin/python -m pytest tests/test_question_extraction.py -q`

Expected: `7 passed`.

- [x] **Step 5: Commit materialization**

```bash
git add scripts/corpus/extraction.py tests/test_question_extraction.py
git commit -m "feat: materialize questions from constrained decisions"
```

### Task 3: Persist Candidate and Decision Artifacts

**Files:**
- Modify: `scripts/corpus/store.py`
- Modify: `tests/test_store.py`
- Modify: `assets/schema.md`

- [x] **Step 1: Write failing persistence tests**

Append to `tests/test_store.py`:

```python
from scripts.corpus.extraction import ExtractionCandidate, ExtractionDecision
from scripts.corpus.store import (
    load_extraction_candidates,
    load_extraction_decisions,
    save_extraction_candidates,
    save_extraction_decisions,
)


def test_extraction_artifacts_save_and_load(tmp_path):
    candidates = [
        ExtractionCandidate(
            "candidate_1", "u1", "1. 如何评估招聘渠道？", "如何评估招聘渠道？"
        )
    ]
    decisions = [ExtractionDecision("candidate_1", True, "评估招聘渠道", role_tags=["市场"])]

    candidate_path = tmp_path / "candidates.json"
    decision_path = tmp_path / "decisions.json"
    save_extraction_candidates(candidates, candidate_path)
    save_extraction_decisions(decisions, decision_path)

    assert load_extraction_candidates(candidate_path) == candidates
    assert load_extraction_decisions(decision_path) == decisions
```

- [x] **Step 2: Run the persistence test to verify it fails**

Run: `../../.venv/bin/python -m pytest tests/test_store.py -q`

Expected: FAIL during collection because the new store helpers do not exist.

- [x] **Step 3: Add store helpers**

Add imports and helpers to `scripts/corpus/store.py`:

```python
from scripts.corpus.extraction import ExtractionCandidate, ExtractionDecision


def save_extraction_candidates(candidates: list[ExtractionCandidate], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps([item.to_dict() for item in candidates], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_extraction_candidates(path) -> list[ExtractionCandidate]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ExtractionCandidate.from_dict(item) for item in data]


def save_extraction_decisions(decisions: list[ExtractionDecision], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps([item.to_dict() for item in decisions], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_extraction_decisions(path) -> list[ExtractionDecision]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [ExtractionDecision.from_dict(item) for item in data]
```

Add the following two entries before `QuestionEvidence` in `assets/schema.md`:

```markdown
- **ExtractionCandidate** `{ candidate_id, source_url, excerpt, display_text, posted_at, modality_origin }`
  An immutable plausible question span. `excerpt` is the verbatim source proof;
  `display_text` is a deterministic source-derived label with only list/framing
  prefixes removed. It is not yet a validated question.
- **ExtractionDecision** `{ candidate_id, accepted, canonical_text, topic, role_tags[] }`
  The agent's constrained semantic decision for one candidate. It cannot provide
  question wording, URLs, dates, or evidence excerpts.
```

- [x] **Step 4: Run persistence tests to verify they pass**

Run: `../../.venv/bin/python -m pytest tests/test_store.py -q`

Expected: `3 passed`.

- [x] **Step 5: Commit persistence and schema**

```bash
git add scripts/corpus/store.py tests/test_store.py assets/schema.md
git commit -m "feat: persist extraction review artifacts"
```

### Task 4: Integrate the Grounding Gate and Agent Workflow

**Files:**
- Modify: `tests/test_question_extraction.py`
- Modify: `SKILL.md`
- Modify: `README.md`

- [x] **Step 1: Add an end-to-end extraction test**

Append to `tests/test_question_extraction.py`:

```python
from datetime import date

from scripts.corpus.quality import prepare_questions


def test_extraction_pipeline_requires_raw_post_evidence_before_ranking():
    post = _post("面试官主要问：\n1. 如何评估招聘渠道？")
    candidate = extract_candidates([post])[0]
    decision = ExtractionDecision(candidate.candidate_id, True, "评估招聘渠道")

    materialized = materialize_questions([candidate], [decision])
    prepared = prepare_questions([post], materialized.questions, today=date(2026, 7, 7))

    assert materialized.questions[0].text == "如何评估招聘渠道？"
    assert materialized.questions[0].evidence[0].excerpt == "1. 如何评估招聘渠道？"
    assert prepared.rejected_questions == []
    assert [question.canonical_text for question in prepared.ranked_questions] == ["评估招聘渠道"]
```

- [x] **Step 2: Run the pipeline test to verify it passes through the existing grounding gate**

Run: `../../.venv/bin/python -m pytest tests/test_question_extraction.py::test_extraction_pipeline_requires_raw_post_evidence_before_ranking -q`

Expected: PASS because Task 2 already creates immutable source refs and evidence.

- [x] **Step 3: Document the exact workflow after confirming the materialized records**

Task 2 must already set `source_refs`, `latest_posted_at`, and immutable
`QuestionEvidence`; this integration task does not relax or modify
`prepare_questions()`.

Replace the current Question-construction portion of step 5 in `SKILL.md` with
this workflow:

```markdown
5. **候选抽题与语义决策。** 先对所有 `RawPost` 调用
   `extract_candidates(raw_posts)`,并用 `save_extraction_candidates` 写入
   `corpus_cache/extraction_candidates.json`。候选只是原文片段,不是题目。
   读取候选后,结合目标岗位和简历,对每个候选写一条
   `ExtractionDecision(candidate_id, accepted, canonical_text, topic, role_tags)`。
   `accepted=true` 只用于真实、相关且语义明确的面试问题;不要提供题面、URL、日期或
   原文证据,这些字段由 Python 固定。用 `save_extraction_decisions` 写入
   `corpus_cache/extraction_decisions.json`。

5a. **题目落盘。** 调用 `materialize_questions(candidates, decisions)`。
   只将其 `questions` 用 `save_questions` 写入 `corpus_cache/questions.json`;
   `rejected_decisions` 和 `issues` 必须进入备考包的“数据缺口”。最终题面来自候选的
   `display_text`,原文证据来自候选的 `excerpt`,不得手工替换。
```

Keep the existing `prepare_questions(raw_posts, questions)` step immediately
after this new section, renumbering it from `5b` to `5b` only if needed for
readability. Update the tool list to name `scripts/corpus/extraction.py` and the
four persistence functions.

In `README.md`, add `extraction.py` below `quality.py` in the corpus tree and
replace the Plan 8 roadmap line with:

```markdown
- [x] **Plan 8:证据优先自动抽题**:`extract_candidates()` 先生成不可变原文候选,
  agent 只提交是否保留、语义归一和岗位标签;`materialize_questions()` 从候选构造题面和
  evidence,再进入 `prepare_questions()`。每轮候选与决策都会落盘,方便核查和复跑。
```

- [x] **Step 4: Run the focused pipeline tests to verify they pass**

Run: `../../.venv/bin/python -m pytest tests/test_question_extraction.py -q`

Expected: `8 passed`.

- [x] **Step 5: Commit workflow integration**

```bash
git add scripts/corpus/extraction.py tests/test_question_extraction.py SKILL.md README.md
git commit -m "feat: document evidence-first extraction workflow"
```

### Task 5: Full Regression and Documentation Verification

**Files:**
- Verify: `scripts/`, `tests/`, `README.md`, `SKILL.md`, `assets/schema.md`

- [x] **Step 1: Run the full suite**

Run: `../../.venv/bin/python -m pytest tests/ -q`

Expected: all existing 115 tests plus the new extraction and persistence tests pass.

- [x] **Step 2: Compile production scripts**

Run: `../../.venv/bin/python -m compileall -q scripts`

Expected: exit code `0` with no output.

- [x] **Step 3: Check diff hygiene and public claims**

Run:

```bash
git diff main...HEAD --check
rg -n "extract_candidates|materialize_questions|ExtractionDecision|证据优先自动抽题" README.md SKILL.md assets/schema.md scripts tests
```

Expected: no whitespace errors, and every public workflow reference points to a
real function or schema.

- [x] **Step 4: No additional documentation correction was required after verification**

```bash
git add README.md SKILL.md assets/schema.md
git commit -m "docs: clarify evidence-first extraction artifacts"
```

Skip this commit if verification found no documentation correction.
