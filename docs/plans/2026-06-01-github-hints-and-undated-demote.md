# GitHub Hints + Undated Demote 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `GithubConnector` 加 `relevance_hints` 过滤减噪音,把 `posted_at=None` 在排序里降权到 0.2(低于已知 >730 天),并在 SKILL.md 里记录 hints 用法。

**Architecture:** 两个独立的小改:(A) `extract_posts_from_markdown` 和 `GithubConnector` 多一个 `relevance_hints` 可选参数,默认 `None` 表示不过滤,保证向后兼容;(B) `_recency_weight` 把 None/解析失败两条分支的返回值从 `0.5` 改成 `0.2`。两改通过独立任务、独立 commit 落地。

**Tech Stack:** Python 3.11、pytest、`.venv/bin/python`(包内 venv)

仓库根:`/Users/kun/Desktop/Projects/InterviewPrepare`
子包根:`interview-intelligence/`
pytest 工作目录:`interview-intelligence/`(`pytest tests/...`)
Spec:`docs/superpowers/specs/2026-06-01-github-relevance-and-undated-demote-design.md`

---

## File Structure

| 文件 | 改动 |
|---|---|
| `interview-intelligence/scripts/connectors/github.py` | 给 `extract_posts_from_markdown` 和 `GithubConnector` 加 `relevance_hints` 参数 + 过滤逻辑 |
| `interview-intelligence/tests/test_github_connector.py` | 新增 hints 行为测试 |
| `interview-intelligence/scripts/corpus/dedupe_rank.py` | `_recency_weight` 的 `None` 与 `ValueError` 分支返回 `0.2` |
| `interview-intelligence/tests/test_dedupe_rank.py` | 更新现有 `test_none_date_weight_between_fresh_and_stale`,新增 `test_malformed_date_treated_as_undated` |
| `interview-intelligence/SKILL.md` | 步骤 3b 文档:dispatch `GithubConnector` 时传 `relevance_hints=收割到的词` |

---

## Task 1: GithubConnector `relevance_hints` 过滤

**Files:**
- Modify: `interview-intelligence/scripts/connectors/github.py`
- Modify: `interview-intelligence/tests/test_github_connector.py`

---

- [ ] **Step 1: 写失败测试 — hints 过滤**

把下面的测试**追加**到 `interview-intelligence/tests/test_github_connector.py` 末尾:

```python
def test_extract_with_hints_keeps_only_matching():
    posts = extract_posts_from_markdown(
        SAMPLE_MD,
        "https://example.com/repo",
        relevance_hints=["RAG"],
    )
    texts = [p.raw_text for p in posts]
    assert "什么是 RAG？" in texts
    assert "说明 MCP 和 Skill 的区别" not in texts
    assert "介绍一下你的 agent 项目架构" not in texts


def test_extract_with_hints_case_insensitive():
    posts = extract_posts_from_markdown(
        SAMPLE_MD,
        "https://example.com/repo",
        relevance_hints=["mcp"],  # lowercase, candidate has uppercase MCP
    )
    texts = [p.raw_text for p in posts]
    assert any("MCP" in t for t in texts)
    assert all("RAG" not in t for t in texts)


def test_extract_with_empty_hints_does_not_filter():
    posts_none = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo", relevance_hints=None)
    posts_empty = extract_posts_from_markdown(SAMPLE_MD, "https://example.com/repo", relevance_hints=[])
    assert {p.raw_text for p in posts_none} == {p.raw_text for p in posts_empty}
    assert len(posts_empty) >= 3  # all question-like lines


def test_connector_passes_hints_through():
    conn = GithubConnector(
        repo_raw_urls=["https://example.com/repo"],
        fetcher=lambda url: SAMPLE_MD,
        relevance_hints=["agent"],
    )
    result = conn.search([])
    assert result.status == "ok"
    texts = [p.raw_text for p in result.posts]
    assert any("agent" in t.lower() for t in texts)
    assert all("RAG" not in t for t in texts)
```

- [ ] **Step 2: 跑测试验证失败**

```bash
cd /Users/kun/Desktop/Projects/InterviewPrepare/interview-intelligence
.venv/bin/python -m pytest tests/test_github_connector.py -v
```

预期:4 个新测试 FAIL,失败原因 `extract_posts_from_markdown() got an unexpected keyword argument 'relevance_hints'` 和 `GithubConnector.__init__() got an unexpected keyword argument 'relevance_hints'`。已有 4 个测试仍 PASS。

- [ ] **Step 3: 改 github.py — 加 hints 过滤**

把 `interview-intelligence/scripts/connectors/github.py` **完整**替换为:

```python
import re
from collections.abc import Callable, Iterable

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
    if t.endswith("?") or t.endswith("?"):
        return True
    return any(k in t for k in _KEYWORDS)


def _matches_any_hint(text: str, hints: Iterable[str]) -> bool:
    t = text.lower()
    return any(h.lower() in t for h in hints)


def extract_posts_from_markdown(
    md_text: str,
    url: str,
    relevance_hints: list[str] | None = None,
) -> list[RawPost]:
    posts: list[RawPost] = []
    use_hints = bool(relevance_hints)
    for line in md_text.splitlines():
        m = _HEADING.match(line) or _BULLET.match(line)
        candidate = m.group(1).strip() if m else line.strip()
        if not _is_question_like(candidate):
            continue
        if use_hints and not _matches_any_hint(candidate, relevance_hints):
            continue
        posts.append(RawPost(source="github", url=url, post_type="text", raw_text=candidate))
    return posts


def _default_fetcher(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


class GithubConnector(Connector):
    name = "github"

    def __init__(
        self,
        repo_raw_urls: list[str],
        fetcher: Callable[[str], str] | None = None,
        relevance_hints: list[str] | None = None,
    ):
        self.repo_raw_urls = repo_raw_urls
        self.fetcher = fetcher or _default_fetcher
        self.relevance_hints = relevance_hints

    def search(self, queries: list[str]) -> SearchResult:
        posts: list[RawPost] = []
        try:
            for url in self.repo_raw_urls:
                posts.extend(
                    extract_posts_from_markdown(
                        self.fetcher(url),
                        url,
                        relevance_hints=self.relevance_hints,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(self.name, f"fetch failed: {exc}")
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")
```

注意:`_is_question_like` 里的两个问号原文件用的就是英文 `?` + 中文 `?`,这里保持原样。

- [ ] **Step 4: 跑测试验证通过**

```bash
cd /Users/kun/Desktop/Projects/InterviewPrepare/interview-intelligence
.venv/bin/python -m pytest tests/test_github_connector.py -v
```

预期:8 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
cd /Users/kun/Desktop/Projects/InterviewPrepare
git add interview-intelligence/scripts/connectors/github.py interview-intelligence/tests/test_github_connector.py
git commit -m "feat(github): add relevance_hints to filter noise

When relevance_hints is provided, only keep question-like lines that
contain at least one hint (case-insensitive substring). Default None
preserves prior behavior."
```

---

## Task 2: `posted_at=None` 降权到 0.2

**Files:**
- Modify: `interview-intelligence/scripts/corpus/dedupe_rank.py`
- Modify: `interview-intelligence/tests/test_dedupe_rank.py`

---

- [ ] **Step 1: 改测试 — 更新 None 顺序 + 新增解析失败测试**

打开 `interview-intelligence/tests/test_dedupe_rank.py`。

**替换** `test_none_date_weight_between_fresh_and_stale` 整段(原断言 `fresh > undated > stale`)为:

```python
def test_undated_ranks_below_known_stale():
    # New policy: undated (0.2) ranks BELOW known-stale (0.3).
    # freq all 1: fresh(1.0) > stale(0.3) > undated(0.2)
    qs = [
        Question("stale", ["a"], latest_posted_at="2022-01-01"),
        Question("undated", ["b"], latest_posted_at=None),
        Question("fresh", ["c"], latest_posted_at="2026-05-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert [q.text for q in out] == ["fresh", "stale", "undated"]
```

**追加**到文件末尾:

```python
def test_malformed_date_treated_as_undated():
    # Malformed posted_at should weight the same as None (0.2), i.e. rank below known-stale.
    qs = [
        Question("stale", ["a"], latest_posted_at="2022-01-01"),
        Question("garbled", ["b"], latest_posted_at="not-a-date"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert [q.text for q in out] == ["stale", "garbled"]
```

- [ ] **Step 2: 跑测试验证失败**

```bash
cd /Users/kun/Desktop/Projects/InterviewPrepare/interview-intelligence
.venv/bin/python -m pytest tests/test_dedupe_rank.py -v
```

预期:`test_undated_ranks_below_known_stale` FAIL(当前权重 0.5 让 undated 排在 stale 前面),`test_malformed_date_treated_as_undated` FAIL(原因同上)。其余 PASS。

- [ ] **Step 3: 改 dedupe_rank.py — None / ValueError 分支返回 0.2**

修改 `interview-intelligence/scripts/corpus/dedupe_rank.py` 的 `_recency_weight` 函数:

把这段:

```python
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
```

换成:

```python
def _recency_weight(posted_at: str | None, today: date) -> float:
    if not posted_at:
        return 0.2
    try:
        d = datetime.strptime(posted_at, "%Y-%m-%d").date()
    except ValueError:
        return 0.2
    days = (today - d).days
    if days <= 365:
        return 1.0
    if days <= 730:
        return 0.6
    return 0.3
```

- [ ] **Step 4: 跑测试验证通过**

```bash
cd /Users/kun/Desktop/Projects/InterviewPrepare/interview-intelligence
.venv/bin/python -m pytest tests/test_dedupe_rank.py -v
```

预期:全部 PASS(原 5 个 + 改名后的 1 个 + 新增 1 个 = 7 个)。

- [ ] **Step 5: 提交**

```bash
cd /Users/kun/Desktop/Projects/InterviewPrepare
git add interview-intelligence/scripts/corpus/dedupe_rank.py interview-intelligence/tests/test_dedupe_rank.py
git commit -m "feat(dedupe_rank): demote undated/malformed posts to 0.2

Timeliness is a hard requirement; undated posts are empirically often
older than known-stale. New ordering: fresh(<=365d, 1.0) > 730d(0.6)
> stale(>730d, 0.3) > undated/malformed(0.2)."
```

---

## Task 3: SKILL.md 文档同步

**Files:**
- Modify: `interview-intelligence/SKILL.md`(步骤 3b 段)

---

- [ ] **Step 1: 编辑 SKILL.md**

打开 `interview-intelligence/SKILL.md`,找到这一段(在第 44 行附近,步骤 3b 的开头):

```
   **3b. 调 connectors + 收割。** 把分好桶的 URL 喂给对应 connector,结果用 `save_raw_posts` 落盘。读取结果,**收割真实出现的岗位名 / 标签 / 高频术语**,用收割到的词跑下一轮 3a,直到不再冒出新词。若某 connector 返回 `status="degraded"`(例如牛客需要 cookie、小红书需要先跑 MediaCrawler、或消息含 `selector` 表示 HTML 漂移),把它需要的东西告诉用户;主力源降级会显著影响时效性,必须明确提示用户,不要默默用 GitHub 凑数。
```

在这一段**之后**追加一段(空一行,然后):

```
   **GitHub 调用必带 `relevance_hints`。** GitHub 仓库里夹带大量算法/八股,如果不带提示词过滤会污染语料。`GithubConnector(repo_raw_urls=..., relevance_hints=<当前一轮的术语/岗位别名>)`,第一轮没收割到东西时用步骤 2 的种子查询当 hints。命中规则:子串、大小写不敏感,只要正文里出现任一 hint 就保留。
```

- [ ] **Step 2: 验证 SKILL.md 仍可解析**

```bash
cd /Users/kun/Desktop/Projects/InterviewPrepare
.venv/bin/python - <<'EOF'
from pathlib import Path
text = Path("interview-intelligence/SKILL.md").read_text(encoding="utf-8")
# Minimal sanity check: front-matter, key steps present
assert text.startswith("---\nname: interview-intelligence")
assert "**3a. URL 发现" in text
assert "**3b. 调 connectors" in text
assert "relevance_hints" in text
print("ok")
EOF
```

预期输出 `ok`。如果 `.venv` 路径不在仓库根,改成 `interview-intelligence/.venv/bin/python`。

- [ ] **Step 3: 跑全套测试回归**

```bash
cd /Users/kun/Desktop/Projects/InterviewPrepare/interview-intelligence
.venv/bin/python -m pytest tests/ -v
```

预期:所有测试 PASS,无新失败。

- [ ] **Step 4: 提交**

```bash
cd /Users/kun/Desktop/Projects/InterviewPrepare
git add interview-intelligence/SKILL.md
git commit -m "docs: document relevance_hints usage for GithubConnector in step 3b"
```

---

## 完成后

回到 main 提交合并(由控制方在 finishing-a-development-branch 阶段执行):

```bash
git checkout main
git merge --no-ff fix/github-hints-and-undated
```

测试再跑一次确认无回归后,删分支。
