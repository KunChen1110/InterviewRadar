# Interview Intelligence — MediaCrawler Adapter + Setup Doc (Plan 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a file-level adapter that turns MediaCrawler's native 小红书 notes JSON into the schema Plan 3's `XiaohongshuConnector` already eats, plus a user-facing setup doc and a tiny SKILL.md tie-in.

**Architecture:** Pure file IO. No network. No subprocess. No MediaCrawler dependency. New module `scripts/scrape/normalize_xhs.py` (function + `__main__` CLI). Tested with hand-written fixtures, and an end-to-end fixture test that feeds adapter output into Plan 3's `parse_mediacrawler_export`. Setup doc lives at `docs/setup_mediacrawler.md`.

**Tech Stack:** Python 3.11, pytest. No new pip dependency.

**Scope discipline (carried from Plans 2/3):** Do not vendor MediaCrawler. Do not implement login/cookies/scheduling. Do not download images. Do not change 牛客/GitHub/OCR modules.

**Prerequisite:** Plans 1/2/3 merged to `main`. Existing: `interview-intelligence/scripts/connectors/xiaohongshu.py` with `parse_mediacrawler_export(json_text)`; `RawPost` model. Work on a branch off `main`.

---

### Task 1: Normalize adapter — pure function

**Files:**
- Create: `interview-intelligence/scripts/scrape/__init__.py` (empty)
- Create: `interview-intelligence/scripts/scrape/normalize_xhs.py`
- Test: `interview-intelligence/tests/test_normalize_xhs.py`
- Test fixture: `interview-intelligence/tests/fixtures/mc_xhs_raw.json`

Pure function `normalize(notes: list[dict]) -> list[dict]`. Field map per the spec §4:

- `note_url` missing → synthesize `https://www.xiaohongshu.com/explore/<note_id>`
- both `note_id` and `note_url` missing → SKIP that note (do not raise)
- `image_list`: string → `split(",")` strip empties; list → keep as-is; missing → `[]`
- `time`: int → keep; missing / non-int → `0`
- `title`/`desc` missing → `""`
- Drop all other MediaCrawler keys (`liked_count`, `comments`, `tag_list`, `type`, …)
- Preserve input order

Output dict shape (exactly the keys `XiaohongshuConnector.parse_mediacrawler_export` reads):

```python
{
    "note_id": "...",  # carried through (Plan 3 doesn't require it but harmless)
    "note_url": "...",
    "title": "...",
    "desc": "...",
    "time": 1758326400000,
    "image_list": ["url1", "url2"],
}
```

- [ ] **Step 1: Create the package marker**

Create `interview-intelligence/scripts/scrape/__init__.py` as an empty file.

- [ ] **Step 2: Create the fixture** `interview-intelligence/tests/fixtures/mc_xhs_raw.json`

```json
[
  {
    "note_id": "n1",
    "type": "normal",
    "title": "字节 AI 应用开发 面经",
    "desc": "一面问了 MCP 和 Skill 的区别。",
    "time": 1758326400000,
    "note_url": "https://www.xiaohongshu.com/explore/n1",
    "image_list": ["https://sns-img.xhs.cn/n1_a.jpg", "https://sns-img.xhs.cn/n1_b.jpg"],
    "tag_list": "面经,实习",
    "liked_count": "1.2万",
    "comments": [{"text": "mark"}]
  },
  {
    "note_id": "n2",
    "title": "RAG 八股",
    "desc": "讲讲检索优化。",
    "time": 0,
    "image_list": "https://sns-img.xhs.cn/n2_a.jpg,https://sns-img.xhs.cn/n2_b.jpg,"
  },
  {
    "note_id": "n3",
    "title": "无 URL 但有 id",
    "desc": "",
    "time": 1700000000000,
    "image_list": []
  },
  {
    "title": "无 id 无 url,应被跳过",
    "desc": "garbage",
    "time": 1700000000000,
    "image_list": []
  },
  {
    "note_id": "n5",
    "time": "not-a-number",
    "image_list": null
  }
]
```

- [ ] **Step 3: Write the failing test** `interview-intelligence/tests/test_normalize_xhs.py`

```python
import json
from pathlib import Path

from scripts.scrape.normalize_xhs import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "mc_xhs_raw.json"


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_skips_notes_with_no_id_and_no_url():
    out = normalize(_load())
    # input has 5 notes, one of which has neither note_id nor note_url
    assert len(out) == 4
    assert "garbage" not in {n["desc"] for n in out}


def test_passes_through_normal_note():
    out = normalize(_load())
    first = out[0]
    assert first["note_id"] == "n1"
    assert first["note_url"] == "https://www.xiaohongshu.com/explore/n1"
    assert first["title"] == "字节 AI 应用开发 面经"
    assert first["desc"].startswith("一面")
    assert first["time"] == 1758326400000
    assert first["image_list"] == [
        "https://sns-img.xhs.cn/n1_a.jpg",
        "https://sns-img.xhs.cn/n1_b.jpg",
    ]


def test_splits_comma_image_list_and_strips_empties():
    out = normalize(_load())
    n2 = next(n for n in out if n["note_id"] == "n2")
    assert n2["image_list"] == [
        "https://sns-img.xhs.cn/n2_a.jpg",
        "https://sns-img.xhs.cn/n2_b.jpg",
    ]


def test_synthesizes_url_from_note_id_when_url_missing():
    out = normalize(_load())
    n3 = next(n for n in out if n["note_id"] == "n3")
    assert n3["note_url"] == "https://www.xiaohongshu.com/explore/n3"


def test_drops_unknown_keys():
    out = normalize(_load())
    first = out[0]
    assert "liked_count" not in first
    assert "comments" not in first
    assert "tag_list" not in first
    assert "type" not in first


def test_invalid_time_becomes_zero_and_null_image_list_becomes_empty():
    out = normalize(_load())
    n5 = next(n for n in out if n["note_id"] == "n5")
    assert n5["time"] == 0
    assert n5["image_list"] == []
    assert n5["title"] == ""
    assert n5["desc"] == ""


def test_preserves_input_order():
    out = normalize(_load())
    assert [n["note_id"] for n in out] == ["n1", "n2", "n3", "n5"]
```

- [ ] **Step 4: Run to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_normalize_xhs.py -v`
Expected: FAIL — "No module named 'scripts.scrape.normalize_xhs'".

- [ ] **Step 5: Implement** `interview-intelligence/scripts/scrape/normalize_xhs.py`

```python
"""Normalize MediaCrawler's native 小红书 notes export into the schema that
`scripts/connectors/xiaohongshu.py:parse_mediacrawler_export` consumes.

Field assumptions about MediaCrawler's output (based on the public repo,
NanmiCoder/MediaCrawler, 小红书 module). If MediaCrawler changes their schema,
only this file needs to be touched.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_NOTE_URL_TEMPLATE = "https://www.xiaohongshu.com/explore/{note_id}"


def _coerce_image_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _coerce_time(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def normalize(notes: list[dict]) -> list[dict]:
    out: list[dict] = []
    for note in notes:
        note_id = note.get("note_id")
        note_url = note.get("note_url")
        if not note_id and not note_url:
            continue
        if not note_url:
            note_url = _NOTE_URL_TEMPLATE.format(note_id=note_id)
        out.append(
            {
                "note_id": note_id or "",
                "note_url": note_url,
                "title": note.get("title") or "",
                "desc": note.get("desc") or "",
                "time": _coerce_time(note.get("time")),
                "image_list": _coerce_image_list(note.get("image_list")),
            }
        )
    return out


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize MediaCrawler 小红书 notes JSON into XiaohongshuConnector input."
    )
    parser.add_argument("input", help="Path to MediaCrawler notes JSON.")
    parser.add_argument("-o", "--output", required=True, help="Path to write normalized JSON.")
    args = parser.parse_args(argv)

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    normalized = normalize(raw)
    Path(args.output).write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(normalized)} notes to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_normalize_xhs.py -v`
Expected: 7 passed.

- [ ] **Step 7: Commit**

```bash
cd interview-intelligence && git add scripts/scrape/__init__.py scripts/scrape/normalize_xhs.py tests/test_normalize_xhs.py tests/fixtures/mc_xhs_raw.json && git commit -m "feat: add MediaCrawler->小红书 connector normalize adapter"
```

---

### Task 2: CLI smoke test + end-to-end with Plan 3 connector

**Files:**
- Test: `interview-intelligence/tests/test_normalize_xhs_cli.py`

Two integration-flavored tests:

1. CLI: invoke `scripts.scrape.normalize_xhs._main([input, "-o", output])` in-process, assert file is written, JSON shape matches normalized output, and the printed line is correct.
2. End-to-end: feed the normalize output JSON text into Plan 3's `parse_mediacrawler_export` and assert the resulting `RawPost` for `n1` has `source="xiaohongshu"`, `post_type="image"`, `posted_at="2025-09-20"`, `asset_paths` with both URLs.

- [ ] **Step 1: Write the failing test** `interview-intelligence/tests/test_normalize_xhs_cli.py`

```python
import json
from pathlib import Path

from scripts.scrape.normalize_xhs import _main
from scripts.connectors.xiaohongshu import parse_mediacrawler_export

FIXTURE = Path(__file__).parent / "fixtures" / "mc_xhs_raw.json"


def test_cli_writes_normalized_file(tmp_path, capsys):
    out_path = tmp_path / "xhs_export.json"
    rc = _main([str(FIXTURE), "-o", str(out_path)])
    assert rc == 0
    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert isinstance(written, list)
    assert len(written) == 4
    assert written[0]["note_url"] == "https://www.xiaohongshu.com/explore/n1"
    captured = capsys.readouterr()
    assert "wrote 4 notes" in captured.out


def test_end_to_end_with_plan3_connector(tmp_path):
    out_path = tmp_path / "xhs_export.json"
    _main([str(FIXTURE), "-o", str(out_path)])
    posts = parse_mediacrawler_export(out_path.read_text(encoding="utf-8"))
    assert len(posts) == 4
    n1 = posts[0]
    assert n1.source == "xiaohongshu"
    assert n1.post_type == "image"
    assert n1.posted_at == "2025-09-20"
    assert n1.asset_paths == [
        "https://sns-img.xhs.cn/n1_a.jpg",
        "https://sns-img.xhs.cn/n1_b.jpg",
    ]
    # n2 has time=0 in the source, so posted_at should be None
    n2 = next(p for p in posts if "RAG" in p.raw_text)
    assert n2.posted_at is None
```

- [ ] **Step 2: Run the test**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_normalize_xhs_cli.py -v`
Expected: 2 passed.

Note: this is an integration test for the contract between Task 1's adapter and Plan 3's connector. It locks in the end-to-end shape; no separate failing-then-passing TDD cycle needed because both endpoints already exist.

- [ ] **Step 3: Commit**

```bash
cd interview-intelligence && git add tests/test_normalize_xhs_cli.py && git commit -m "test: CLI + end-to-end adapter→XiaohongshuConnector contract"
```

---

### Task 3: Setup doc

**Files:**
- Create: `docs/setup_mediacrawler.md` (at repo root, not inside `interview-intelligence/`)

- [ ] **Step 1: Write** `docs/setup_mediacrawler.md` verbatim:

````markdown
# 小红书面经采集 — MediaCrawler 设置指引

启用 `interview-intelligence` skill 的小红书源是**可选**步骤。skill 本身不抓数据;
真正的采集由开源工具 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 完成,
本文档教你怎么把它产出的 JSON 喂给本 skill。

> 仅供个人、非商业用途。请遵守目标平台的服务条款。

## 1. 前提

- Python 3.11+、Git、一个可登录小红书的微信/手机号
- 一个普通浏览器(扫码登录用)

## 2. 装 MediaCrawler(放在本仓库**外面**)

```bash
cd ~/Code   # 或任意你存放第三方仓库的位置
git clone https://github.com/NanmiCoder/MediaCrawler.git
cd MediaCrawler
# 按它 README 的步骤装依赖(它通常用 uv 或 pip + requirements.txt)
```

> 不要把 MediaCrawler clone 到本仓库里。它有自己的依赖、许可证、更新节奏,
> 解耦更好维护。

## 3. 登录小红书

按 MediaCrawler README 的「登录方式」一节操作(QR 扫码 / Cookie 注入二选一)。
登录态保存在它自己的目录里。

## 4. 用关键词搜面经

在 MediaCrawler 仓库里运行它的搜索命令,目标平台选 `xhs`,关键词建议:

- 你的目标岗位别名(例如「AI 应用开发 面经」「Agent 工程师 面试」「大模型应用 实习」)
- 公司 + 岗位组合(例如「字节 AI 实习 面经」)

具体命令格式以 MediaCrawler 当前版本 README 为准。跑完后输出文件通常在
`MediaCrawler/data/xhs/json/` 之类的位置,文件名形如 `search_contents_2026-xx-xx.json`。

## 5. 归一化

回到本仓库:

```bash
cd /path/to/InterviewPrepare/interview-intelligence
.venv/bin/python -m scripts.scrape.normalize_xhs \
    /path/to/MediaCrawler/data/xhs/json/search_contents_*.json \
    -o corpus_cache/xhs_export.json
```

成功会打印 `wrote N notes to corpus_cache/xhs_export.json`。

如果适配器报错,**多半是 MediaCrawler 升级了输出 schema**。
检查 `scripts/scrape/normalize_xhs.py` 顶部的字段假设注释,对照真实 JSON 修字段名,
跑测试 `pytest tests/test_normalize_xhs.py` 验证,再用真实文件重跑。

## 6. 喂给 skill

在 skill 的工作流里,给 `XiaohongshuConnector` 传刚才的输出路径:

```python
XiaohongshuConnector(export_path="corpus_cache/xhs_export.json")
```

剩下的(时效过滤、OCR、去重、项目锚定)skill 会自己处理。

## 7. 复跑

数据陈旧时直接重跑步骤 4–5。Plan 2 的时效过滤会把超过两年的笔记从结果里剔掉,
所以你不用手动清理旧数据。
````

- [ ] **Step 2: Commit**

```bash
git add docs/setup_mediacrawler.md && git commit -m "docs: add MediaCrawler setup guide for 小红书 source"
```

(Note: this commit runs from the repo root, NOT from `interview-intelligence/`.)

---

### Task 4: SKILL.md tie-in

**Files:**
- Modify: `interview-intelligence/SKILL.md`

Add a single "0. 准备" step before step 1, and tweak the constraints to point at the setup doc.

- [ ] **Step 1: Insert step 0** — find the line `## 工作流` and insert a new step block immediately before the existing `1. **简历理解。**` line:

```
0. **准备(仅当启用小红书源)。** 让用户先按 `docs/setup_mediacrawler.md` 跑一遍 MediaCrawler 采集 + 适配器归一化,产出 `corpus_cache/xhs_export.json`(适配器在 `scripts/scrape/normalize_xhs.py`,把 MediaCrawler 的原生输出转成 `XiaohongshuConnector` 能吃的格式)。文本/牛客/GitHub 源不需要这一步。

```

- [ ] **Step 2: Add adapter to the tools list** — under `## 工具`, add this line right after the existing `scripts/connectors/xiaohongshu.py` line:

```
- `scripts/scrape/normalize_xhs.py` → `normalize(notes) -> list[dict]`(CLI:`python -m scripts.scrape.normalize_xhs <in.json> -o <out.json>`),把 MediaCrawler 原生输出归一化为 `XiaohongshuConnector` 的输入。
```

- [ ] **Step 3: Update constraint** — find the existing line
```
- 小红书走 MediaCrawler 采集导出,OCR 采用混合策略(粗 OCR + 视觉回退);MediaCrawler 仅供个人、非商业用途。
```
and replace it with:
```
- 小红书走 MediaCrawler 采集导出(用户预先离线跑一次,流程见 `docs/setup_mediacrawler.md`),OCR 采用混合策略(粗 OCR + 视觉回退);MediaCrawler 仅供个人、非商业用途。
```

- [ ] **Step 4: Validate front-matter**

Run: `cd interview-intelligence && .venv/bin/python -c "t=open('SKILL.md').read(); assert t.startswith('---'); fm=t.split('---')[1]; assert 'name:' in fm and 'description:' in fm; print('OK')"`
Expected: prints `OK`.

- [ ] **Step 5: Commit**

```bash
cd interview-intelligence && git add SKILL.md && git commit -m "docs: wire MediaCrawler adapter pre-step into SKILL.md"
```

---

### Task 5: Full suite green

- [ ] **Step 1: Run the whole suite**

Run: `cd interview-intelligence && .venv/bin/pytest -q`
Expected: 39 (Plan 3) + 7 (Task 1) + 2 (Task 2) = **48 passed**.

- [ ] **Step 2: No commit if no changes.** If the suite is green and nothing is staged, skip. Otherwise investigate the regression.

---

## Self-Review

**Spec coverage:**
- Adapter at `scripts/scrape/normalize_xhs.py` with the field rules from spec §4 → Task 1. ✓
- CLI `python -m scripts.scrape.normalize_xhs <in> -o <out>` → Task 1 (`_main`) + Task 2 (CLI smoke). ✓
- End-to-end contract adapter → Plan 3 connector → Task 2. ✓
- Setup doc `docs/setup_mediacrawler.md` covering install/login/run/normalize/feed → Task 3. ✓
- SKILL.md step 0 + tools list + constraint update → Task 4. ✓
- Fixture covers all branches from spec §7 (normal note, comma-string image list, missing URL synth, missing id+url skipped, time=0, invalid time, null image list, extra keys dropped, order preserved) → Task 1 fixture + tests. ✓
- Deferred correctly: no vendoring, no auto-login, no image download, no validate-export command.

**Placeholder scan:** No TBD/TODO. Every code step has full code. All shell commands have expected output.

**Type consistency:**
- `normalize(notes: list[dict]) -> list[dict]` signature identical across Task 1 implementation, Task 1 tests, Task 2 tests, SKILL.md tools list.
- Output keys (`note_id, note_url, title, desc, time, image_list`) exactly match what Plan 3's `parse_mediacrawler_export` reads — verified by the end-to-end test (Task 2 step 3).
- `_main(argv) -> int` callable from tests (Task 2) and CLI (Task 1 `if __name__`).
- `XiaohongshuConnector(export_path=...)` referenced unchanged in Task 3 doc and Task 4 SKILL.md (matches Plan 3).
