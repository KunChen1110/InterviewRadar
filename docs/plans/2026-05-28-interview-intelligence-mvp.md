# Interview Intelligence Skill — MVP Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable Claude Code Agent Skill that, given a resume (PDF/image) and a fuzzy role, retrieves interview questions from GitHub interview repos, dedupes/ranks them, and lets the agent produce a personalized prep package with project-anchored follow-ups.

**Architecture:** Deterministic dirty work (fetch, parse, persist, dedupe/rank, resume text extraction) lives in tested Python scripts. Judgment/reasoning (resume understanding, iterative vocabulary harvesting, content-relevance, project anchoring, prep authoring) is performed by the agent following `SKILL.md`. Python tools and the agent communicate through normalized JSON files in `corpus_cache/`.

**Tech Stack:** Python 3.11, pytest, pypdf, requests. (Embeddings/semantic dedupe and the 牛客/小红书 connectors + OCR are deferred to Plans 2 and 3.)

**Scope note:** This plan is the MVP slice. 牛客 connector (Plan 2) and 小红书 + hybrid OCR (Plan 3) are out of scope here. The connector interface in Task 4 is designed so those drop in later without changing callers.

---

### Task 1: Project scaffold

**Files:**
- Create: `interview-intelligence/requirements.txt`
- Create: `interview-intelligence/pytest.ini`
- Create: `interview-intelligence/scripts/__init__.py`
- Create: `interview-intelligence/scripts/connectors/__init__.py`
- Create: `interview-intelligence/scripts/corpus/__init__.py`
- Create: `interview-intelligence/tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
pypdf==4.3.1
requests==2.32.3
pytest==8.3.2
```

- [ ] **Step 2: Create pytest.ini**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 3: Create empty package markers**

Create each `__init__.py` listed above as an empty file.

- [ ] **Step 4: Install deps**

Run: `cd interview-intelligence && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
Expected: installs without error.

- [ ] **Step 5: Commit**

```bash
git add interview-intelligence/requirements.txt interview-intelligence/pytest.ini interview-intelligence/scripts interview-intelligence/tests
git commit -m "chore: scaffold interview-intelligence skill package"
```

---

### Task 2: Data models

**Files:**
- Create: `interview-intelligence/scripts/models.py`
- Test: `interview-intelligence/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.models import RawPost, Question, FollowUpChain


def test_rawpost_roundtrips_through_dict():
    post = RawPost(
        source="github",
        url="https://example.com/p1",
        post_type="text",
        raw_text="What is MCP?",
        asset_paths=[],
        comments=["see docs"],
    )
    assert RawPost.from_dict(post.to_dict()) == post


def test_question_roundtrips_through_dict():
    q = Question(
        text="What is MCP?",
        source_refs=["https://example.com/p1"],
        freq=2,
        role_tags=["agent"],
        topic="protocols",
        modality_origin="text",
    )
    assert Question.from_dict(q.to_dict()) == q


def test_followupchain_roundtrips_through_dict():
    chain = FollowUpChain(
        seed_question="What is MCP?",
        resume_anchor="skill-driven project",
        followups=["How does your skill engine work?"],
        is_grounded=True,
    )
    assert FollowUpChain.from_dict(chain.to_dict()) == chain
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_models.py -v`
Expected: FAIL with "No module named 'scripts.models'".

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass, field, asdict


@dataclass
class RawPost:
    source: str
    url: str
    post_type: str  # text | image | mixed
    raw_text: str
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_models.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add interview-intelligence/scripts/models.py interview-intelligence/tests/test_models.py
git commit -m "feat: add RawPost/Question/FollowUpChain data models"
```

---

### Task 3: Corpus store (JSON persistence)

**Files:**
- Create: `interview-intelligence/scripts/corpus/store.py`
- Test: `interview-intelligence/tests/test_store.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.models import RawPost, Question
from scripts.corpus.store import (
    save_raw_posts, load_raw_posts, save_questions, load_questions,
)


def test_raw_posts_save_and_load(tmp_path):
    posts = [RawPost("github", "u1", "text", "Q1"), RawPost("github", "u2", "text", "Q2")]
    path = tmp_path / "raw.json"
    save_raw_posts(posts, path)
    assert load_raw_posts(path) == posts


def test_questions_save_and_load(tmp_path):
    qs = [Question("Q1", ["u1"]), Question("Q2", ["u2"], freq=3)]
    path = tmp_path / "q.json"
    save_questions(qs, path)
    assert load_questions(path) == qs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_store.py -v`
Expected: FAIL with "No module named 'scripts.corpus.store'".

- [ ] **Step 3: Write minimal implementation**

```python
import json
from pathlib import Path

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_store.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add interview-intelligence/scripts/corpus/store.py interview-intelligence/tests/test_store.py
git commit -m "feat: add JSON corpus store for raw posts and questions"
```

---

### Task 4: Connector interface

**Files:**
- Create: `interview-intelligence/scripts/connectors/base.py`
- Test: `interview-intelligence/tests/test_base_connector.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.models import RawPost
from scripts.connectors.base import Connector, SearchResult


def test_searchresult_holds_status_and_posts():
    posts = [RawPost("github", "u1", "text", "Q1")]
    r = SearchResult(posts=posts, status="ok", message="")
    assert r.posts == posts
    assert r.status == "ok"


def test_searchresult_degraded_factory_has_no_posts():
    r = SearchResult.degraded("nowcoder", "needs cookie")
    assert r.posts == []
    assert r.status == "degraded"
    assert "cookie" in r.message


def test_connector_is_abstract():
    class Dummy(Connector):
        name = "dummy"

        def search(self, queries):
            return SearchResult(posts=[], status="ok", message="")

    assert Dummy().search(["x"]).status == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_base_connector.py -v`
Expected: FAIL with "No module named 'scripts.connectors.base'".

- [ ] **Step 3: Write minimal implementation**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from scripts.models import RawPost


@dataclass
class SearchResult:
    posts: list[RawPost] = field(default_factory=list)
    status: str = "ok"  # ok | degraded | error
    message: str = ""

    @classmethod
    def degraded(cls, source: str, message: str) -> "SearchResult":
        return cls(posts=[], status="degraded", message=f"[{source}] {message}")


class Connector(ABC):
    name: str = "base"

    @abstractmethod
    def search(self, queries: list[str]) -> SearchResult:
        """Run queries against the source and return normalized RawPosts."""
        raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_base_connector.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add interview-intelligence/scripts/connectors/base.py interview-intelligence/tests/test_base_connector.py
git commit -m "feat: add Connector interface and SearchResult with degrade factory"
```

---

### Task 5: GitHub connector — markdown parsing

**Files:**
- Create: `interview-intelligence/scripts/connectors/github.py`
- Test: `interview-intelligence/tests/test_github_connector.py`

The parser splits an interview-repo markdown file into candidate question posts. It treats markdown headings (`#`..`######`) and list bullets (`-`, `*`, or `1.`) that end in a question mark OR contain interview-question keywords as separate `RawPost`s. Network fetch is a thin wrapper tested separately by monkeypatching.

- [ ] **Step 1: Write the failing test**

```python
from scripts.connectors.github import extract_posts_from_markdown, GithubConnector


SAMPLE_MD = """# Agent 面经
## 一面
- 说明 MCP 和 Skill 的区别
- 什么是 RAG？
随便一句不是题目的话。
### 项目相关
1. 介绍一下你的 agent 项目架构
"""


def test_extract_picks_question_like_lines():
    posts = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo")
    texts = [p.raw_text for p in posts]
    assert "说明 MCP 和 Skill 的区别" in texts
    assert "什么是 RAG？" in texts
    assert "介绍一下你的 agent 项目架构" in texts
    assert "随便一句不是题目的话。" not in texts


def test_extract_sets_source_and_url():
    posts = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo")
    assert all(p.source == "github" for p in posts)
    assert all(p.url == "https://example.com/repo" for p in posts)
    assert all(p.post_type == "text" for p in posts)


def test_connector_search_uses_injected_fetcher():
    conn = GithubConnector(
        repo_raw_urls=["https://example.com/repo"],
        fetcher=lambda url: SAMPLE_MD,
    )
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert any("RAG" in p.raw_text for p in result.posts)


def test_connector_degrades_on_fetch_error():
    def boom(url):
        raise RuntimeError("network down")

    conn = GithubConnector(repo_raw_urls=["https://example.com/repo"], fetcher=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_github_connector.py -v`
Expected: FAIL with "No module named 'scripts.connectors.github'".

- [ ] **Step 3: Write minimal implementation**

```python
import re
from collections.abc import Callable

import requests

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost

_KEYWORDS = ("介绍", "说明", "区别", "原理", "什么是", "如何", "为什么", "解释")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET = re.compile(r"^(?:[-*]|\d+\.)\s+(.*)$")


def _is_question_like(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t.endswith("?") or t.endswith("？"):
        return True
    return any(k in t for k in _KEYWORDS)


def extract_posts_from_markdown(md_text: str, url: str) -> list[RawPost]:
    posts: list[RawPost] = []
    for line in md_text.splitlines():
        m = _HEADING.match(line) or _BULLET.match(line)
        candidate = m.group(1).strip() if m else line.strip()
        if _is_question_like(candidate):
            posts.append(RawPost(source="github", url=url, post_type="text", raw_text=candidate))
    return posts


def _default_fetcher(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


class GithubConnector(Connector):
    name = "github"

    def __init__(self, repo_raw_urls: list[str], fetcher: Callable[[str], str] | None = None):
        self.repo_raw_urls = repo_raw_urls
        self.fetcher = fetcher or _default_fetcher

    def search(self, queries: list[str]) -> SearchResult:
        posts: list[RawPost] = []
        try:
            for url in self.repo_raw_urls:
                posts.extend(extract_posts_from_markdown(self.fetcher(url), url))
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(self.name, f"fetch failed: {exc}")
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")
```

Note: `queries` is accepted for interface symmetry; GitHub repos are pulled whole and filtered downstream by the agent's content-relevance step (the repo URLs themselves are the targeting).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_github_connector.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add interview-intelligence/scripts/connectors/github.py interview-intelligence/tests/test_github_connector.py
git commit -m "feat: add GitHub interview-repo connector with degrade-on-error"
```

---

### Task 6: Dedupe & rank

**Files:**
- Create: `interview-intelligence/scripts/corpus/dedupe_rank.py`
- Test: `interview-intelligence/tests/test_dedupe_rank.py`

MVP dedupe is normalized-text based (lowercase, strip punctuation/whitespace). Embedding-based semantic dedupe is deferred — `normalize` is the single seam where it would be swapped in later. Duplicates merge: `freq` sums, `source_refs`/`role_tags` union (order-preserving). Output is sorted by `freq` descending, ties broken by first-seen order.

- [ ] **Step 1: Write the failing test**

```python
from scripts.models import Question
from scripts.corpus.dedupe_rank import normalize, dedupe_and_rank


def test_normalize_strips_case_punctuation_whitespace():
    assert normalize("  What is  MCP??  ") == normalize("what is mcp")


def test_dedupe_merges_and_sums_freq():
    qs = [
        Question("What is MCP?", ["u1"], role_tags=["agent"]),
        Question("what is  mcp", ["u2"], role_tags=["llm"]),
        Question("What is RAG?", ["u3"]),
    ]
    out = dedupe_and_rank(qs)
    assert len(out) == 2
    top = out[0]
    assert top.freq == 2
    assert top.source_refs == ["u1", "u2"]
    assert top.role_tags == ["agent", "llm"]


def test_rank_sorts_by_freq_desc():
    qs = [
        Question("rare", ["a"]),
        Question("common", ["b"]),
        Question("common", ["c"]),
    ]
    out = dedupe_and_rank(qs)
    assert out[0].text == "common"
    assert out[0].freq == 2
    assert out[1].text == "rare"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_dedupe_rank.py -v`
Expected: FAIL with "No module named 'scripts.corpus.dedupe_rank'".

- [ ] **Step 3: Write minimal implementation**

```python
import re

from scripts.models import Question

_PUNCT = re.compile(r"[^\w一-鿿]+")


def normalize(text: str) -> str:
    t = text.strip().lower()
    t = _PUNCT.sub(" ", t)
    return " ".join(t.split())


def _union(into: list[str], extra: list[str]) -> None:
    for item in extra:
        if item not in into:
            into.append(item)


def dedupe_and_rank(questions: list[Question]) -> list[Question]:
    merged: dict[str, Question] = {}
    order: list[str] = []
    for q in questions:
        key = normalize(q.text)
        if key not in merged:
            merged[key] = Question(
                text=q.text,
                source_refs=list(q.source_refs),
                freq=q.freq,
                role_tags=list(q.role_tags),
                topic=q.topic,
                modality_origin=q.modality_origin,
            )
            order.append(key)
        else:
            m = merged[key]
            m.freq += q.freq
            _union(m.source_refs, q.source_refs)
            _union(m.role_tags, q.role_tags)
    ranked = sorted(order, key=lambda k: -merged[k].freq)
    return [merged[k] for k in ranked]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_dedupe_rank.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add interview-intelligence/scripts/corpus/dedupe_rank.py interview-intelligence/tests/test_dedupe_rank.py
git commit -m "feat: add normalized-text dedupe and frequency ranking"
```

---

### Task 7: Resume extraction

**Files:**
- Create: `interview-intelligence/scripts/resume_extract.py`
- Test: `interview-intelligence/tests/test_resume_extract.py`
- Test fixture: `interview-intelligence/tests/fixtures/sample_resume.pdf`

PDFs are extracted to text with pypdf. Image resumes (`.png/.jpg/.jpeg/.webp`) cannot be parsed deterministically — return `needs_vision=True` with the asset path so the agent reads the image directly (mirrors the hybrid-OCR fallback policy). A PDF that yields little/no text (scanned image PDF) also sets `needs_vision=True`.

- [ ] **Step 1: Create the PDF fixture**

Run (generates a one-page text PDF without extra deps via pypdf's writer is insufficient, so use reportlab-free approach with a committed fixture):

```bash
cd interview-intelligence && .venv/bin/python -c "
from pypdf import PdfWriter
# pypdf cannot draw text; create fixture via a minimal embedded PDF string instead
import pathlib, base64
# Minimal single-page PDF containing the text 'Skill driven agent project Python RAG'
pdf = b'''%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 74>>stream
BT /F1 12 Tf 20 100 Td (Skill driven agent project Python RAG) Tj ET
endstream endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000052 00000 n 
0000000101 00000 n 
0000000229 00000 n 
0000000353 00000 n 
trailer<</Size 6/Root 1 0 R>>
startxref
422
%%EOF'''
pathlib.Path('tests/fixtures').mkdir(parents=True, exist_ok=True)
pathlib.Path('tests/fixtures/sample_resume.pdf').write_bytes(pdf)
print('wrote fixture')
"
```
Expected: prints `wrote fixture`. Then verify it is readable: `.venv/bin/python -c "from pypdf import PdfReader; print(repr(PdfReader('tests/fixtures/sample_resume.pdf').pages[0].extract_text()))"` — expected output contains `Skill driven agent project Python RAG`. If extraction returns empty, regenerate; do not proceed until the fixture extracts text.

- [ ] **Step 2: Write the failing test**

```python
from pathlib import Path

from scripts.resume_extract import extract_resume, ResumeExtraction

FIXTURE = Path(__file__).parent / "fixtures" / "sample_resume.pdf"


def test_pdf_extraction_returns_text():
    result = extract_resume(FIXTURE)
    assert isinstance(result, ResumeExtraction)
    assert "Skill" in result.text
    assert result.needs_vision is False


def test_image_resume_flags_vision(tmp_path):
    img = tmp_path / "resume.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    result = extract_resume(img)
    assert result.needs_vision is True
    assert result.asset_path == str(img)
    assert result.text == ""


def test_empty_pdf_flags_vision(tmp_path):
    blank = tmp_path / "blank.pdf"
    blank.write_bytes((FIXTURE.read_bytes().replace(b"Skill driven agent project Python RAG", b" ")))
    result = extract_resume(blank)
    assert result.needs_vision is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_resume_extract.py -v`
Expected: FAIL with "No module named 'scripts.resume_extract'".

- [ ] **Step 4: Write minimal implementation**

```python
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_MIN_TEXT_CHARS = 10


@dataclass
class ResumeExtraction:
    text: str
    needs_vision: bool
    asset_path: str


def extract_resume(path) -> ResumeExtraction:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in _IMAGE_EXTS:
        return ResumeExtraction(text="", needs_vision=True, asset_path=str(p))
    if ext == ".pdf":
        reader = PdfReader(str(p))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if len(text) < _MIN_TEXT_CHARS:
            return ResumeExtraction(text="", needs_vision=True, asset_path=str(p))
        return ResumeExtraction(text=text, needs_vision=False, asset_path=str(p))
    # Plain text / markdown resumes
    text = p.read_text(encoding="utf-8", errors="ignore").strip()
    needs_vision = len(text) < _MIN_TEXT_CHARS
    return ResumeExtraction(text=text, needs_vision=needs_vision, asset_path=str(p))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_resume_extract.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add interview-intelligence/scripts/resume_extract.py interview-intelligence/tests/test_resume_extract.py interview-intelligence/tests/fixtures/sample_resume.pdf
git commit -m "feat: add resume extraction with vision fallback for images/scanned PDFs"
```

---

### Task 8: Full test run + reference docs

**Files:**
- Create: `interview-intelligence/assets/schema.md`
- Create: `interview-intelligence/references/role_taxonomy.md`

- [ ] **Step 1: Run the whole suite green**

Run: `cd interview-intelligence && .venv/bin/pytest -v`
Expected: all tests from Tasks 2–7 pass (15 tests).

- [ ] **Step 2: Write assets/schema.md**

```markdown
# Data Structures

- **RawPost** `{ source, url, post_type(text|image|mixed), raw_text, asset_paths[], comments[] }`
  One scraped unit (a question-like line, post, or image). Produced by connectors.
- **Question** `{ text, source_refs[], freq, role_tags[], topic, modality_origin(text|ocr|vision) }`
  A normalized interview question. Produced by the agent's extraction step from RawPosts,
  then merged/ranked by `corpus/dedupe_rank.py`.
- **FollowUpChain** `{ seed_question, resume_anchor, followups[], is_grounded }`
  A personalized follow-up chain. Produced by the agent's project-anchoring step.
  `is_grounded=false` means it degraded to a plain 八股 question (no resume anchor found).

Persistence: normalized JSON under `corpus_cache/` via `corpus/store.py`.
```

- [ ] **Step 3: Write references/role_taxonomy.md**

```markdown
# Role Taxonomy (seed only)

A *starting* alias list for AI-application roles. This is a SEED for the agent's first-pass
queries, NOT the source of truth. The real role vocabulary is discovered iteratively by
harvesting actual role names/tags from first-pass scrape results (see SKILL.md step 3).

- AI 应用开发 / AI 应用工程师
- AI 创新应用 / AI 产品研发
- Agent 开发 / 智能体应用
- AI 研究开发 / LLM 应用开发
- 大模型应用 / 生成式 AI 工程师

Common underlying skill/topic seeds (more stable than role names):
agent, RAG, MCP, prompt engineering, LLM 应用, 向量检索, function calling, 微调, 评测.
```

- [ ] **Step 4: Commit**

```bash
git add interview-intelligence/assets/schema.md interview-intelligence/references/role_taxonomy.md
git commit -m "docs: add data-structure schema and role-taxonomy seed reference"
```

---

### Task 9: SKILL.md orchestration

**Files:**
- Create: `interview-intelligence/SKILL.md`

This is the agent-facing orchestration contract. No code/tests — it is authored prose that wires the Python tools into the 8-step workflow, GitHub-only for the MVP.

- [ ] **Step 1: Write SKILL.md**

````markdown
---
name: interview-intelligence
description: Use when a user wants to prepare for interviews by uploading a resume (PDF/image) and naming a fuzzy target role (e.g. "AI 应用开发"). Broad-net retrieves real interview questions from GitHub interview repos, dedupes/ranks them, and produces a personalized prep package with project-anchored follow-ups. V1 source is GitHub only.
---

# Interview Intelligence Skill

Turn a resume + a fuzzy role into a personalized interview prep package grounded in real
interview-experience (面经) content. You (the agent) do the reasoning; Python scripts under
`scripts/` do the deterministic work. Communicate through JSON in `corpus_cache/`.

## Inputs
- Resume: a PDF, image, or text file path.
- Fuzzy role: a direction like "AI 应用开发" (NOT a specific JD).

## Tools (run with the package venv: `.venv/bin/python`)
- `scripts/resume_extract.py` → `extract_resume(path) -> ResumeExtraction{text, needs_vision, asset_path}`
- `scripts/connectors/github.py` → `GithubConnector(repo_raw_urls).search(queries) -> SearchResult`
- `scripts/corpus/store.py` → `save_raw_posts/load_raw_posts/save_questions/load_questions`
- `scripts/corpus/dedupe_rank.py` → `dedupe_and_rank(questions) -> list[Question]`
- Data models in `scripts/models.py`; structures documented in `assets/schema.md`.

## Workflow

1. **Resume understanding.** Call `extract_resume`. If `needs_vision` is true, read the
   image/PDF yourself with your vision capability. Produce a structured summary: skills,
   projects (with the techniques each project used), and notable keywords.

2. **Seed query generation.** From the role direction + the resume's skills/topics, build
   SEED queries from underlying skills/topics (agent, RAG, MCP, LLM 应用, …), NOT a guessed
   role-name list. Use `references/role_taxonomy.md` only as a starting hint.

3. **Iterative retrieval (GitHub, V1).** Pick relevant interview repos and pass their raw
   markdown URLs to `GithubConnector(repo_raw_urls).search(seed_queries)`. Save the returned
   posts with `save_raw_posts`. Read the results and HARVEST the real role names / tags /
   recurring terms that actually appear. Re-run with repos/terms the harvest surfaced. Repeat
   until no new vocabulary emerges. If a connector returns `status="degraded"`, tell the user
   what it needs and continue with what you have — never block the pipeline.
   **Human-in-the-loop:** before the final pass, show the user the directions/terms you
   discovered from real data and let them add/remove/steer.

4. **Content-semantic relevance.** Decide each post's relevance by reading its content against
   the user's role + resume — NOT by whether a role name matched a preset list.

5. **Question extraction.** Convert relevant RawPosts into normalized `Question`s (set
   `modality_origin`). Save with `save_questions`.

6. **Dedupe & rank.** Run `dedupe_and_rank(load_questions(...))` and save the ranked result.
   This is the high-frequency question set.

7. **Project-anchored reasoning.** For each top question, check whether it connects to a
   resume project/skill. If yes, build a `FollowUpChain` (seed → personalized follow-ups,
   `is_grounded=true`). Every follow-up MUST trace to (a resume project/skill) + (a real
   scraped question) — if you cannot ground it, set `is_grounded=false` and keep it as a
   plain 八股 question. Do NOT fabricate follow-ups.

8. **Prep package.** Write a Markdown package: role analysis, gap analysis, high-frequency
   八股 questions (with source links), personalized project follow-up chains, and reference
   approaches. Save it to `corpus_cache/prep_package.md` and show it to the user.

## Constraints
- GitHub is the only source in V1 (牛客/小红书 + OCR come in later plans).
- Third-party scrapers used in later versions (e.g. MediaCrawler) are for personal,
  non-commercial use only.
- Grounding over fluency: never invent follow-ups or questions not traceable to real data.
````

- [ ] **Step 2: Sanity-check the skill loads (front-matter valid)**

Run: `cd interview-intelligence && .venv/bin/python -c "import re,sys; t=open('SKILL.md').read(); assert t.startswith('---'); fm=t.split('---')[1]; assert 'name:' in fm and 'description:' in fm; print('SKILL.md front-matter OK')"`
Expected: prints `SKILL.md front-matter OK`.

- [ ] **Step 3: Commit**

```bash
git add interview-intelligence/SKILL.md
git commit -m "feat: add SKILL.md orchestration for interview-intelligence MVP"
```

---

## Self-Review

**Spec coverage (MVP scope):**
- Resume understanding (image/PDF, vision fallback) → Task 7 + SKILL step 1. ✓
- Seed query generation (skills/topics, not role names) → SKILL step 2 + Task 8 taxonomy. ✓
- Iterative data-driven retrieval + vocabulary harvest + HITL → SKILL step 3. ✓
- Content-semantic relevance → SKILL step 4. ✓
- Connector interface + degrade → Task 4; GitHub connector → Task 5. ✓
- Question extraction + normalized records → SKILL step 5 + Task 2 models. ✓
- Dedupe & rank → Task 6. ✓
- Project-anchored reasoning + grounding validation → SKILL step 7 + FollowUpChain (Task 2). ✓
- Prep package output → SKILL step 8. ✓
- Corpus persistence → Task 3. ✓
- Deferred (correctly out of MVP scope): 牛客 connector (Plan 2), 小红书 + hybrid OCR (Plan 3),
  embedding-based semantic dedupe, ASR sources, interactive mock.

**Placeholder scan:** No TBD/TODO; every code step has complete code; commands have expected output.

**Type consistency:** `RawPost`/`Question`/`FollowUpChain` fields are identical across Tasks 2,
3, 5, 6, and SKILL.md. `SearchResult{posts,status,message}` consistent in Tasks 4 and 5.
`extract_resume`→`ResumeExtraction{text,needs_vision,asset_path}` consistent in Task 7 and SKILL.md.
`dedupe_and_rank` / `normalize` names consistent in Task 6 and SKILL.md.
