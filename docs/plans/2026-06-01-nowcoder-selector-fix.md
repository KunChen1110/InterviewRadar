# Interview Intelligence — NowCoder 选择器修复 + 空内容守卫 (Plan 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the silent-ok bug surfaced by the 2026-06-01 end-to-end smoke run: `NowCoderConnector` parsed live HTML with stale selectors, produced empty `RawPost`s, and reported `status=ok`. Update selectors to real schema, add `createTime` epoch-ms date extraction, and harden the connector with an **empty-content guard** so future selector drift fails loud instead of silent.

**Architecture:** One file (`scripts/connectors/nowcoder.py`) + one fixture replacement + test rewrite. No new dependencies. The empty-content guard is the durable part: even if NowCoder shifts schema *again*, the user sees a degrade with an actionable message instead of a corrupted corpus.

**Tech Stack:** Python 3.11, BeautifulSoup, pytest.

**Findings being addressed (附录 B of `corpus_cache/prep_package.md`):**
- Real HTML uses `div.content-post-title h1` (not `.post-title`) and `div.nc-slate-editor-content` (not `.post-content`).
- Real date lives in a JSON blob field `"createTime":<epoch_ms>` — not in any visible `.post-date`.
- The old fixture mirrored the old (wrong) selectors, so tests passed while the connector was broken in production.

**Prerequisite:** Plans 1-4 merged. Work on a branch off `main`.

---

### Task 1: Replace fixture with real-shape HTML

**Files:**
- Modify: `interview-intelligence/tests/fixtures/nowcoder_sample.html`

Replace the fixture with HTML that mirrors real NowCoder discuss-page structure: a `div.content-post-title > h1`, a `div.nc-slate-editor-content` with `<p>` paragraphs, and a `"createTime":<epoch_ms>` substring embedded somewhere in the page (where Vue's data blob would put it). Pick `createTime=1758326400000` (2025-09-20 UTC) to keep the existing test date expectations consistent.

- [ ] **Step 1: Overwrite** `interview-intelligence/tests/fixtures/nowcoder_sample.html` with:

```html
<!DOCTYPE html>
<html>
<head><title>字节 AI 应用开发 一面面经_牛客网</title></head>
<body>
  <section class="post-content-box">
    <div class="content-post-title"><h1>字节 AI 应用开发 一面面经</h1></div>
    <div class="user-job-name">
      <span class="time-text">09-20 12:00</span>
      <span class="job-text">长安大学 产品经理</span>
    </div>
    <div class="nc-slate-editor-content">
      <p>问了 MCP 和 Skill 的区别。</p>
      <p>介绍一下你做过的 agent 项目架构。</p>
      <p>RAG 的检索召回怎么优化？</p>
    </div>
  </section>
  <script>window.__INITIAL_STATE__ = {"post":{"createTime":1758326400000,"title":"字节 AI 应用开发 一面面经"}};</script>
</body>
</html>
```

- [ ] **Step 2: Commit the fixture replacement on its own** (lets the next step's test failures be unambiguous):

```bash
cd interview-intelligence && git add tests/fixtures/nowcoder_sample.html && git commit -m "test: replace nowcoder fixture with real-shape HTML (createTime + new selectors)"
```

---

### Task 2: Watch existing tests break (red phase)

- [ ] **Step 1: Run the existing nowcoder test against the new fixture**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_nowcoder_connector.py -v`
Expected: at least `test_parse_extracts_text_and_date` and `test_connector_search_uses_injected_fetcher` FAIL — title/content not extracted, `posted_at` not parsed, because the connector still uses old selectors. This confirms the bug.

(No commit. This is the documentation that the fix is needed.)

---

### Task 3: Rewrite tests for the new behavior

**Files:**
- Modify: `interview-intelligence/tests/test_nowcoder_connector.py`

Rewrite the test file with:
1. The original "parse extracts text + date" test, now expecting `posted_at == "2025-09-20"` from `createTime` (already aligns).
2. The connector-with-fetcher test, expecting `posted_at == "2025-09-20"`.
3. The `degraded-on-fetch-error` test (cookie message). Unchanged.
4. A new `test_parse_missing_date_yields_none` test against minimal HTML with the new selectors but no `createTime`.
5. **New** `test_connector_degrades_when_parsed_content_is_empty` — feed HTML that has none of the expected selectors; assert `status=="degraded"` with a message containing `"selector"`.
6. **New** `test_parse_handles_only_title_or_only_content` — guard against "title found, content missing" or vice versa: still counts as a real post (don't degrade), but log the partial. (Test asserts the post comes back with partial content and `status=="ok"`; we degrade only when BOTH are empty for that post.)

- [ ] **Step 1: Overwrite** `interview-intelligence/tests/test_nowcoder_connector.py`:

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
    assert post.posted_at == "2025-09-20"
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
    assert result.posts[0].posted_at == "2025-09-20"


def test_connector_degrades_on_fetch_error():
    def boom(url):
        raise RuntimeError("login wall")

    conn = NowCoderConnector(post_urls=["https://nowcoder.com/p/1"], fetcher=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "cookie" in result.message.lower()


def test_parse_missing_date_yields_none():
    html = (
        "<div class='content-post-title'><h1>T</h1></div>"
        "<div class='nc-slate-editor-content'><p>body text here</p></div>"
    )
    post = parse_nowcoder_post(html, "https://nowcoder.com/p/2")
    assert post.posted_at is None
    assert "body text here" in post.raw_text
    assert post.raw_text.startswith("T")


def test_connector_degrades_when_parsed_content_is_empty():
    # HTML with none of the expected selectors — simulates future schema drift.
    drift_html = "<html><body><div class='something-else'>nothing useful</div></body></html>"
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/1"], fetcher=lambda url: drift_html
    )
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "selector" in result.message.lower()


def test_parse_handles_only_title_or_only_content():
    # Title only — still a valid post, don't degrade.
    title_only_html = "<div class='content-post-title'><h1>仅标题</h1></div>"
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/3"], fetcher=lambda url: title_only_html
    )
    result = conn.search([])
    assert result.status == "ok"
    assert result.posts[0].raw_text == "仅标题"

    # Content only — still a valid post.
    content_only_html = (
        "<div class='nc-slate-editor-content'><p>正文段落</p></div>"
    )
    conn2 = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/4"], fetcher=lambda url: content_only_html
    )
    result2 = conn2.search([])
    assert result2.status == "ok"
    assert "正文段落" in result2.posts[0].raw_text
```

- [ ] **Step 2: Run to see failures** (the connector is still old):

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_nowcoder_connector.py -v`
Expected: multiple FAILs (parse tests fail because selectors haven't been updated; degrade-on-empty fails because the guard doesn't exist).

(No commit. Next task makes them pass.)

---

### Task 4: Fix the connector

**Files:**
- Modify: `interview-intelligence/scripts/connectors/nowcoder.py`

Changes:
1. New selectors:
   - title → `div.content-post-title h1`
   - content → `div.nc-slate-editor-content` (use `get_text("\n", strip=True)` to keep paragraph breaks)
2. New date extraction: regex `r'"createTime"\s*:\s*(\d{10,13})'` on the raw HTML (not parsed soup, since it lives in a `<script>`). First match wins (it's the post header; subsequent matches are typically comments). Convert ms → ISO date UTC.
3. New empty-content guard in `search()`: after building each post, if `post.raw_text` is empty, treat it as parse failure. If **every** parsed post is empty, return `SearchResult.degraded(name, "解析后的标题和正文都为空,NowCoder HTML 选择器可能已漂移;请对照 scripts/connectors/nowcoder.py 顶部注释更新 selectors")`. (If some posts succeed and some don't, we keep the good ones and report ok — partial degradation handled by caller.)
4. Add a top-of-file docstring summarizing the current selector assumptions, so the next maintainer (or the agent itself) can find the assumptions fast.

- [ ] **Step 1: Replace** `interview-intelligence/scripts/connectors/nowcoder.py`:

```python
"""NowCoder discuss-page connector.

Current selector assumptions (verified 2026-06-01 against real HTML):
- Title:   <div class="content-post-title"><h1>...</h1></div>
- Content: <div class="nc-slate-editor-content"><p>...</p>...</div>
- Date:    "createTime": <epoch_ms> in an embedded JS blob (NOT visible HTML).

If parsing returns empty title AND empty content for every URL, the connector
degrades with a "selector" message — NowCoder almost certainly updated their
schema. Inspect the live HTML and update the three selectors above.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost

_CREATE_TIME = re.compile(r'"createTime"\s*:\s*(\d{10,13})')


def _parse_create_time(html: str) -> str | None:
    m = _CREATE_TIME.search(html)
    if not m:
        return None
    try:
        ts = int(m.group(1))
        # 13 digits = ms, 10 digits = s
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (ValueError, OSError):
        return None


def parse_nowcoder_post(html: str, url: str) -> RawPost:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("div.content-post-title h1")
    title = title_el.get_text(strip=True) if title_el else ""

    content_el = soup.select_one("div.nc-slate-editor-content")
    body = content_el.get_text("\n", strip=True) if content_el else ""

    posted_at = _parse_create_time(html)

    if title and body:
        raw_text = f"{title}\n{body}"
    else:
        raw_text = title or body
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

        if posts and all(not p.raw_text for p in posts):
            return SearchResult.degraded(
                self.name,
                "解析后的标题和正文都为空,NowCoder HTML 选择器可能已漂移;"
                "请对照 scripts/connectors/nowcoder.py 顶部注释更新 selectors",
            )

        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")
```

- [ ] **Step 2: Run nowcoder tests**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_nowcoder_connector.py -v`
Expected: 6 passed.

- [ ] **Step 3: Run full suite to confirm no regression**

Run: `cd interview-intelligence && .venv/bin/pytest -q`
Expected: 48 (previous) + 2 new tests = **50 passed**. (Task 3 added 2 tests beyond the original 4.)

- [ ] **Step 4: Commit**

```bash
cd interview-intelligence && git add scripts/connectors/nowcoder.py tests/test_nowcoder_connector.py && git commit -m "fix: nowcoder selectors (content-post-title/nc-slate-editor-content/createTime) + empty-content guard"
```

---

### Task 5: SKILL.md note (1 line) + Plan 5 finding back-link

**Files:**
- Modify: `interview-intelligence/SKILL.md`

Add one bullet to the constraints section about the empty-content guard, so future agents (and the user) know what a "selector" degrade means.

- [ ] **Step 1: Append to the `## 约束` list**, after the existing "可追溯优先" bullet:

```
- 若 connector 返回 `degraded` 且消息含 `selector`,说明源站点 HTML 改了选择器;到对应 `scripts/connectors/<name>.py` 顶部注释看当前假设,核对真实 HTML 后更新选择器并补 fixture。
```

- [ ] **Step 2: Validate front-matter + commit**

```bash
cd interview-intelligence && .venv/bin/python -c "t=open('SKILL.md').read(); assert t.startswith('---') and 'name:' in t.split('---')[1] and 'description:' in t.split('---')[1]; print('OK')"
```
Expected: prints `OK`.

```bash
git add SKILL.md && git commit -m "docs: explain the 'selector' degrade signal in SKILL.md constraints"
```

---

## Self-Review

**Spec coverage** (the spec is the smoke-test finding #1):
- Real-shape fixture replacing the self-affirming one → Task 1. ✓
- Selectors updated to real schema → Task 4. ✓
- `createTime` epoch-ms date extraction (which the old connector didn't even try) → Task 4. ✓
- **Durable empty-content guard** (silent ok → loud degrade on future drift) → Task 4 (`if posts and all(not p.raw_text for p in posts)`). ✓
- Tests rewritten to assert real selectors + new guard + partial-content behavior → Task 3. ✓
- SKILL.md tells future agent what "selector" in a degrade message means → Task 5. ✓
- Deferred correctly: anti-scrape/cookie automation, multi-page pagination, comment scraping.

**Placeholder scan:** No TBD/TODO. Every code step has full code. Commands have expected output.

**Type consistency:**
- `parse_nowcoder_post(html, url) -> RawPost` signature unchanged across tests and connector.
- `SearchResult.degraded(name, message)` invocation matches its existing definition.
- `RawPost(source, url, post_type, raw_text, posted_at)` fields all present and match Plan 1/2.
- `_parse_create_time` is private; only used by `parse_nowcoder_post`.

**Risk note:** Real NowCoder pages can have multiple `"createTime"` matches (comments). Taking the **first** match is the right heuristic (the post's header appears before any comment in source order). If a future regression shows wrong dates, the fix is to anchor the regex to the post container — but that's premature now.
