# Interview Intelligence — 牛客 Connector + Recency Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add timeliness to the skill — extract post dates, filter 面经 to the last ~2 years, rank by frequency-and-recency — and add a 牛客 NowCoder connector (the primary timestamped source) that parses post HTML into dated RawPosts with graceful degradation.

**Architecture:** Builds directly on the V1 package at `interview-intelligence/`. Adds a `posted_at` date to `RawPost` and `latest_posted_at` to `Question`, a new `corpus/recency.py` filter, upgrades `corpus/dedupe_rank.py` to weight recency, and adds `connectors/nowcoder.py` (parses recorded sample HTML offline; live fetch is an injectable, degrade-safe wrapper — no real login-wall scraping implemented here). All reasoning stays in `SKILL.md`.

**Tech Stack:** Python 3.11, pytest, pypdf, requests, **beautifulsoup4** (new — HTML parsing for 牛客 pages).

**Scope note:** This plan does NOT implement real cookie-based 牛客 login/anti-bot scraping (deferred; the connector exposes an injectable fetcher and degrades cleanly when none is wired). 小红书 + hybrid OCR remain in Plan 3. The recency window is fixed at 2 years (730 days).

**Prerequisite:** V1 is merged to `main` (`interview-intelligence/scripts/models.py` has `RawPost`/`Question`; `corpus/dedupe_rank.py` has `normalize`/`dedupe_and_rank`; `connectors/base.py` has `Connector`/`SearchResult`). Work on a branch off `main`.

---

### Task 1: Add `beautifulsoup4` dependency

**Files:**
- Modify: `interview-intelligence/requirements.txt`

- [ ] **Step 1: Append the dependency**

Add this line to `interview-intelligence/requirements.txt` (keep the existing three lines):
```
beautifulsoup4==4.12.3
```
The full file must then read:
```
pypdf==4.3.1
requests==2.32.3
pytest==8.3.2
beautifulsoup4==4.12.3
```

- [ ] **Step 2: Install it**

Run: `cd interview-intelligence && .venv/bin/pip install -r requirements.txt`
Expected: installs `beautifulsoup4` (and `soupsieve`) with no error.

- [ ] **Step 3: Verify import**

Run: `cd interview-intelligence && .venv/bin/python -c "import bs4; print(bs4.__version__)"`
Expected: prints `4.12.3`.

- [ ] **Step 4: Commit**

```bash
git add interview-intelligence/requirements.txt
git commit -m "chore: add beautifulsoup4 for HTML parsing"
```

---

### Task 2: Add `posted_at` to RawPost and `latest_posted_at` to Question

**Files:**
- Modify: `interview-intelligence/scripts/models.py`
- Test: `interview-intelligence/tests/test_models.py` (add cases)

Both new fields are optional (`str | None = None`), so existing positional construction in other tests/code keeps working. Dates are ISO `YYYY-MM-DD` strings or `None`.

- [ ] **Step 1: Add failing tests** (append to `tests/test_models.py`)

```python
def test_rawpost_has_optional_posted_at_defaulting_none():
    post = RawPost("github", "u1", "text", "Q1")
    assert post.posted_at is None
    dated = RawPost("nowcoder", "u2", "text", "Q2", posted_at="2025-09-01")
    assert RawPost.from_dict(dated.to_dict()) == dated
    assert dated.posted_at == "2025-09-01"


def test_question_has_optional_latest_posted_at_defaulting_none():
    q = Question("Q1", ["u1"])
    assert q.latest_posted_at is None
    dated = Question("Q2", ["u2"], latest_posted_at="2025-09-01")
    assert Question.from_dict(dated.to_dict()) == dated
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_models.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'posted_at'` (and same for `latest_posted_at`).

- [ ] **Step 3: Add the fields** in `scripts/models.py`

In `RawPost`, add `posted_at` AFTER `raw_text` and BEFORE the `field(default_factory=list)` lines (a non-default field cannot follow defaulted ones, but `posted_at` has a default so it must sit among the defaulted fields — place it as the first defaulted field):
```python
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
```

In `Question`, add `latest_posted_at` after `freq`:
```python
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
```
Leave `FollowUpChain` unchanged.

- [ ] **Step 4: Run the full suite**

Run: `cd interview-intelligence && .venv/bin/pytest -q`
Expected: all pass (existing 18 + 2 new = 20). The existing `test_dedupe_rank.py` still passes because `Question` field additions have defaults and the merge in `dedupe_rank` (Task 4) is not yet changed — but note `dedupe_and_rank` currently reconstructs `Question` field-by-field WITHOUT `latest_posted_at`; that still works (it defaults to None). Confirm green before moving on.

- [ ] **Step 5: Commit**

```bash
git add scripts/models.py tests/test_models.py
git commit -m "feat: add posted_at to RawPost and latest_posted_at to Question"
```

---

### Task 3: Recency filter

**Files:**
- Create: `interview-intelligence/scripts/corpus/recency.py`
- Test: `interview-intelligence/tests/test_recency.py`

Filters RawPosts to those within `window_days` (default 730 = ~2 years) of a reference date. Policy: posts with `posted_at=None` are KEPT (undated supplementary sources like GitHub must not be silently dropped); only posts with a parseable date OLDER than the window are dropped. Unparseable date strings are treated as None (kept).

- [ ] **Step 1: Write the failing test** `tests/test_recency.py`

```python
from datetime import date

from scripts.models import RawPost
from scripts.corpus.recency import filter_recent


def _post(posted_at):
    return RawPost("nowcoder", "u", "text", "Q", posted_at=posted_at)


def test_keeps_recent_drops_old():
    ref = date(2026, 5, 28)
    posts = [_post("2025-09-01"), _post("2023-01-01")]  # within 2y, older than 2y
    kept = filter_recent(posts, window_days=730, today=ref)
    assert [p.posted_at for p in kept] == ["2025-09-01"]


def test_none_dates_are_kept():
    ref = date(2026, 5, 28)
    posts = [_post(None), _post("2010-01-01")]
    kept = filter_recent(posts, window_days=730, today=ref)
    assert [p.posted_at for p in kept] == [None]


def test_unparseable_date_is_kept():
    ref = date(2026, 5, 28)
    posts = [_post("not-a-date")]
    kept = filter_recent(posts, window_days=730, today=ref)
    assert len(kept) == 1


def test_boundary_exactly_window_is_kept():
    ref = date(2026, 5, 28)
    posts = [_post("2024-05-29")]  # 729 days before ref → kept
    kept = filter_recent(posts, window_days=730, today=ref)
    assert len(kept) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_recency.py -v`
Expected: FAIL — "No module named 'scripts.corpus.recency'".

- [ ] **Step 3: Implement** `scripts/corpus/recency.py`

```python
from datetime import date, datetime

from scripts.models import RawPost


def _parse(posted_at: str | None) -> date | None:
    if not posted_at:
        return None
    try:
        return datetime.strptime(posted_at, "%Y-%m-%d").date()
    except ValueError:
        return None


def filter_recent(
    posts: list[RawPost], window_days: int = 730, today: date | None = None
) -> list[RawPost]:
    ref = today or date.today()
    kept: list[RawPost] = []
    for p in posts:
        d = _parse(p.posted_at)
        if d is None:
            kept.append(p)  # undated/unparseable → keep
            continue
        if (ref - d).days <= window_days:
            kept.append(p)
    return kept
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_recency.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/corpus/recency.py tests/test_recency.py
git commit -m "feat: add recency filter (keep posts within ~2 years; keep undated)"
```

---

### Task 4: Upgrade dedupe/rank to carry and weight recency

**Files:**
- Modify: `interview-intelligence/scripts/corpus/dedupe_rank.py`
- Test: `interview-intelligence/tests/test_dedupe_rank.py` (add cases; keep existing)

On merge, the surviving `Question` keeps the MAX (most recent) `latest_posted_at` among duplicates (preferring any real date over None). Ranking score = `freq * recency_weight(latest_posted_at, today)`, where weight is: ≤365 days → 1.0; ≤730 days → 0.6; older → 0.3; None → 0.5 (undated content ranks below recently-dated content but above stale-dated content). Sort by score desc; ties broken by first-seen order (stable sort).

- [ ] **Step 1: Add failing tests** (append to `tests/test_dedupe_rank.py`)

```python
from datetime import date


def test_merge_keeps_most_recent_date():
    qs = [
        Question("What is MCP?", ["u1"], latest_posted_at="2024-01-01"),
        Question("what is  mcp", ["u2"], latest_posted_at="2025-06-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert len(out) == 1
    assert out[0].latest_posted_at == "2025-06-01"
    assert out[0].freq == 2


def test_recency_weight_can_outrank_lower_freq_when_close():
    # old item freq=2 → score 2*0.3=0.6 ; fresh item freq=1 → score 1*1.0=1.0
    qs = [
        Question("old hot", ["a"], freq=2, latest_posted_at="2023-01-01"),
        Question("fresh", ["b"], freq=1, latest_posted_at="2026-04-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert out[0].text == "fresh"


def test_none_date_weight_between_fresh_and_stale():
    # freq all 1: fresh(1.0) > undated(0.5) > stale(0.3)
    qs = [
        Question("stale", ["a"], latest_posted_at="2022-01-01"),
        Question("undated", ["b"], latest_posted_at=None),
        Question("fresh", ["c"], latest_posted_at="2026-05-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert [q.text for q in out] == ["fresh", "undated", "stale"]
```

NOTE: the existing tests in this file call `dedupe_and_rank(qs)` with no `today`. Keep them working by giving `today` a default of `None` (meaning `date.today()`). The existing `test_dedupe_merges_and_sums_freq` and `test_rank_sorts_by_freq_desc` use no dates (all None → equal weight 0.5), so freq alone decides order and they still pass.

- [ ] **Step 2: Run to verify new tests fail**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_dedupe_rank.py -v`
Expected: the 3 new tests FAIL (`dedupe_and_rank() got an unexpected keyword argument 'today'`); existing 3 still pass.

- [ ] **Step 3: Rewrite** `scripts/corpus/dedupe_rank.py`

```python
import re
from datetime import date, datetime

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


def _max_date(a: str | None, b: str | None) -> str | None:
    # Returns the more recent ISO date string; any real date beats None.
    candidates = [d for d in (a, b) if d]
    return max(candidates) if candidates else None


def _recency_weight(posted_at: str | None, today: date) -> float:
    if not posted_at:
        return 0.5
    try:
        d = datetime.strptime(posted_at, "%Y-%m-%d").date()
    except ValueError:
        return 0.5
    days = (today - d).days
    if days <= 365:
        return 1.0
    if days <= 730:
        return 0.6
    return 0.3


def dedupe_and_rank(questions: list[Question], today: date | None = None) -> list[Question]:
    """Merge questions with the same normalized text and rank by frequency and recency.

    Contract: callers pass one Question per occurrence with freq=1; this sums
    incoming freq, so passing pre-aggregated freqs will skew ranking. Score is
    freq * recency_weight(latest_posted_at); ties keep first-seen order.
    """
    ref = today or date.today()
    merged: dict[str, Question] = {}
    order: list[str] = []
    for q in questions:
        key = normalize(q.text)
        if key not in merged:
            merged[key] = Question(
                text=q.text,
                source_refs=list(q.source_refs),
                freq=q.freq,
                latest_posted_at=q.latest_posted_at,
                role_tags=list(q.role_tags),
                topic=q.topic,
                modality_origin=q.modality_origin,
            )
            order.append(key)
        else:
            m = merged[key]
            m.freq += q.freq
            m.latest_posted_at = _max_date(m.latest_posted_at, q.latest_posted_at)
            _union(m.source_refs, q.source_refs)
            _union(m.role_tags, q.role_tags)

    def score(k: str) -> float:
        q = merged[k]
        return q.freq * _recency_weight(q.latest_posted_at, ref)

    ranked = sorted(order, key=lambda k: -score(k))
    return [merged[k] for k in ranked]
```

- [ ] **Step 4: Run the file then full suite**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_dedupe_rank.py -v` — expected 6 passed.
Run: `cd interview-intelligence && .venv/bin/pytest -q` — expected all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/corpus/dedupe_rank.py tests/test_dedupe_rank.py
git commit -m "feat: weight ranking by recency and carry latest_posted_at through merge"
```

---

### Task 5: 牛客 connector — HTML parsing + date extraction

**Files:**
- Create: `interview-intelligence/scripts/connectors/nowcoder.py`
- Test: `interview-intelligence/tests/test_nowcoder_connector.py`
- Test fixture: `interview-intelligence/tests/fixtures/nowcoder_sample.html`

Parses a 牛客 discussion/面经 post HTML page into one RawPost: title + body text become `raw_text`, the post date becomes `posted_at` (ISO). The fixture mimics 牛客's structure: a title element, a date element, and body paragraphs. Live fetching is an injectable `fetcher` (defaults to a `requests`-based one); when no fetcher succeeds the connector degrades. NowCoder needs login for many pages, so the default fetcher will often fail — that is expected and handled by degradation; real cookie-based login is OUT of scope for this task.

- [ ] **Step 1: Create the HTML fixture** `tests/fixtures/nowcoder_sample.html`

```html
<!DOCTYPE html>
<html>
<head><title>字节 AI 应用开发 一面面经</title></head>
<body>
  <div class="post-title">字节 AI 应用开发 一面面经</div>
  <span class="post-date">2025-09-15</span>
  <div class="post-content">
    <p>问了 MCP 和 Skill 的区别。</p>
    <p>介绍一下你做过的 agent 项目架构。</p>
    <p>RAG 的检索召回怎么优化？</p>
  </div>
</body>
</html>
```

- [ ] **Step 2: Write the failing test** `tests/test_nowcoder_connector.py`

```python
from pathlib import Path

from scripts.connectors.base import SearchResult
from scripts.connectors.nowcoder import parse_nowcoder_post, NowCoderConnector

FIXTURE = Path(__file__).parent / "fixtures" / "nowcoder_sample.html"
SAMPLE_HTML = FIXTURE.read_text(encoding="utf-8")


def test_parse_extracts_text_and_date():
    post = parse_nowcoder_post(SAMPLE_HTML, "https://nowcoder.com/p/1")
    assert post.source == "nowcoder"
    assert post.url == "https://nowcoder.com/p/1"
    assert post.posted_at == "2025-09-15"
    assert "MCP 和 Skill 的区别" in post.raw_text
    assert "agent 项目架构" in post.raw_text
    assert "字节 AI 应用开发 一面面经" in post.raw_text


def test_connector_search_uses_injected_fetcher():
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/1"],
        fetcher=lambda url: SAMPLE_HTML,
    )
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert len(result.posts) == 1
    assert result.posts[0].posted_at == "2025-09-15"


def test_connector_degrades_on_fetch_error():
    def boom(url):
        raise RuntimeError("login wall")

    conn = NowCoderConnector(post_urls=["https://nowcoder.com/p/1"], fetcher=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "cookie" in result.message.lower()


def test_parse_missing_date_yields_none():
    html = "<div class='post-title'>T</div><div class='post-content'><p>body text here</p></div>"
    post = parse_nowcoder_post(html, "https://nowcoder.com/p/2")
    assert post.posted_at is None
    assert "body text here" in post.raw_text
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_nowcoder_connector.py -v`
Expected: FAIL — "No module named 'scripts.connectors.nowcoder'".

- [ ] **Step 4: Implement** `scripts/connectors/nowcoder.py`

```python
import re
from collections.abc import Callable

import requests
from bs4 import BeautifulSoup

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_nowcoder_post(html: str, url: str) -> RawPost:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one(".post-title")
    title = title_el.get_text(strip=True) if title_el else ""

    date_el = soup.select_one(".post-date")
    posted_at = None
    if date_el:
        m = _ISO_DATE.search(date_el.get_text(strip=True))
        if m:
            posted_at = m.group(0)

    content_el = soup.select_one(".post-content")
    if content_el:
        paras = [p.get_text(strip=True) for p in content_el.find_all("p")]
        body = "\n".join(p for p in paras if p)
    else:
        body = ""

    raw_text = (title + "\n" + body).strip() if title else body.strip()
    return RawPost(
        source="nowcoder",
        url=url,
        post_type="text",
        raw_text=raw_text,
        posted_at=posted_at,
    )


def _default_fetcher(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


class NowCoderConnector(Connector):
    name = "nowcoder"

    def __init__(self, post_urls: list[str], fetcher: Callable[[str], str] | None = None):
        self.post_urls = post_urls
        self.fetcher = fetcher or _default_fetcher

    def search(self, queries: list[str]) -> SearchResult:
        posts: list[RawPost] = []
        try:
            for url in self.post_urls:
                posts.append(parse_nowcoder_post(self.fetcher(url), url))
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(
                self.name,
                f"fetch failed ({exc}); 牛客需要登录，请提供 cookie 或手动粘贴帖子链接/内容",
            )
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")
```

Note: `queries` is accepted for interface symmetry; the connector fetches the given `post_urls` (the agent supplies URLs it discovered). Do NOT implement search-by-keyword crawling or login here.

- [ ] **Step 5: Run to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_nowcoder_connector.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/connectors/nowcoder.py tests/test_nowcoder_connector.py tests/fixtures/nowcoder_sample.html
git commit -m "feat: add 牛客 connector parsing post HTML to dated RawPost with degrade"
```

---

### Task 6: Update SKILL.md for recency + 牛客

**Files:**
- Modify: `interview-intelligence/SKILL.md`

- [ ] **Step 1: Update the tools list**

In the `## 工具` section, add these two lines (after the `github.py` line and after the `dedupe_rank.py` line respectively):
```
- `scripts/connectors/nowcoder.py` → `NowCoderConnector(post_urls).search(queries) -> SearchResult`
- `scripts/corpus/recency.py` → `filter_recent(posts, window_days=730, today=None) -> list[RawPost]`
```

- [ ] **Step 2: Replace workflow step 3 source guidance**

Find step `3. **迭代检索(V1 用 GitHub)。**` and replace its first sentence so it reads (keep the rest of the step — harvest loop, degrade, HITL — intact):
```
3. **迭代检索。** 源的优先级:**牛客(主力,带时间戳)> GitHub(补充,常过时)**。把发现的牛客帖子 URL 传给 `NowCoderConnector(post_urls).search(...)`,把 GitHub 仓库 raw URL 传给 `GithubConnector(repo_raw_urls).search(...)`。两者结果都用 `save_raw_posts` 落盘。读取结果，**收割真实出现的岗位名 / 标签 / 高频术语**，再用收割到的词跑下一轮，直到不再冒出新词。若某 connector 返回 `status="degraded"`（例如牛客需要 cookie），把它需要的东西告诉用户；牛客降级会显著影响时效性，必须明确提示用户，不要默默用 GitHub 凑数。
```

- [ ] **Step 3: Insert a recency-filter step**

Immediately AFTER step `5.` (题目抽取) and BEFORE step `6.` (去重 & 排序), insert:
```
5b. **时效过滤。** 在抽取出题目之前，先用 `filter_recent(raw_posts)` 把超过约两年的帖子丢掉（默认窗口 730 天；`posted_at` 为 None 的无日期帖子保留）。时效性是硬需求——过时的面经没有价值。
```

- [ ] **Step 4: Update step 6 ranking wording and the constraints**

Change step `6.` text to mention recency:
```
6. **去重 & 排序。** 跑 `dedupe_and_rank(load_questions(...))` 并保存排序结果。排序同时考虑**频次和时效**（近期题加权更高），这就是高频题集。
```
In the `## 约束` section, replace the line `- V1 只有 GitHub 一个源(牛客/小红书 + OCR 在后续 plan)。` with:
```
- 当前源:牛客(主力)+ GitHub(补充)。小红书 + OCR 在后续 plan。
- 时效性是硬需求:只保留近两年的面经,排序向近期加权。
```

- [ ] **Step 5: Validate front-matter and commit**

Run: `cd interview-intelligence && .venv/bin/python -c "t=open('SKILL.md').read(); assert t.startswith('---'); fm=t.split('---')[1]; assert 'name:' in fm and 'description:' in fm; print('OK')"`
Expected: prints `OK`.
```bash
git add SKILL.md
git commit -m "docs: wire 牛客 connector and recency filtering into SKILL.md workflow"
```

---

### Task 7: Full suite + schema doc update

**Files:**
- Modify: `interview-intelligence/assets/schema.md`

- [ ] **Step 1: Run the whole suite green**

Run: `cd interview-intelligence && .venv/bin/pytest -q`
Expected: all tests pass (V1's 18 + Task2's 2 + Task3's 4 + Task4's 3 + Task5's 4 = 31).

- [ ] **Step 2: Update `assets/schema.md`**

Replace the `RawPost` and `Question` bullet lines with:
```markdown
- **RawPost** `{ source, url, post_type(text|image|mixed), raw_text, posted_at(ISO date|null), asset_paths[], comments[] }`
  One scraped unit. `posted_at` is the source post date (ISO `YYYY-MM-DD`) or null for undated
  sources. Produced by connectors. Filtered to the recency window by `corpus/recency.py`.
- **Question** `{ text, source_refs[], freq, latest_posted_at(ISO date|null), role_tags[], topic, modality_origin(text|ocr|vision) }`
  A normalized interview question. `latest_posted_at` is the most recent date among merged
  duplicates. Produced by the agent's extraction step, then merged/ranked (by frequency AND
  recency) by `corpus/dedupe_rank.py`.
```

- [ ] **Step 3: Commit**

```bash
git add assets/schema.md
git commit -m "docs: document posted_at/latest_posted_at and recency in schema"
```

---

## Self-Review

**Spec coverage:**
- Recency as first-class (filter + weighted ranking) → Tasks 3, 4 + SKILL steps 5b/6. ✓
- `posted_at` on RawPost / `latest_posted_at` on Question → Task 2. ✓
- 牛客 primary connector with date extraction + degrade → Task 5. ✓
- GitHub demoted to supplementary; degrade surfaced not silently tolerated → SKILL step 3 (Task 6). ✓
- Rejected stale offline corpus → not built (correct); spec §6 records the rejection. ✓
- Schema doc updated → Task 7. ✓
- Deferred (correctly out of scope): real 牛客 cookie/login scraping; 小红书 + hybrid OCR (Plan 3);
  ASR sources; interactive mock.

**Placeholder scan:** No TBD/TODO; every code step has complete code; commands have expected output.

**Type consistency:**
- `RawPost(... posted_at=...)` and `Question(... latest_posted_at=...)` field names identical across
  Tasks 2, 3, 4, 5 and the schema doc.
- `filter_recent(posts, window_days=730, today=None)` signature identical in Task 3 and SKILL/Task 6.
- `dedupe_and_rank(questions, today=None)` signature identical in Task 4, its tests, and SKILL step 6.
- `NowCoderConnector(post_urls, fetcher=None).search(queries) -> SearchResult` and
  `parse_nowcoder_post(html, url) -> RawPost` consistent in Task 5 and SKILL tools list (Task 6).
- `SearchResult` / `Connector` reused from V1 unchanged.
