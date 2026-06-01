# Interview Intelligence — 小红书 Connector + Hybrid OCR Implementation Plan (Plan 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 小红书 image source — a connector that turns a MediaCrawler JSON export into dated image-RawPosts, plus a hybrid OCR module that coarse-reads images and falls back to the agent's vision when confidence is low.

**Architecture:** Builds on V1 + Plan 2 at `interview-intelligence/`. Adds `connectors/xiaohongshu.py` (parses a MediaCrawler export — offline, no live login) producing `RawPost(post_type="image", asset_paths=[...], posted_at=...)`, and `ocr/extract.py` with an **injectable OCR engine** and a **vision fallback** (mirrors the established degrade/vision-fallback pattern in `resume_extract.py`). Reasoning stays in `SKILL.md`.

**Tech Stack:** Python 3.11, pytest. No new pip dependency. (A real OCR engine such as PaddleOCR/Tesseract is injectable but intentionally NOT wired here.)

**Scope note (intentional deferrals, same discipline as Plan 2's 牛客):**
- No live MediaCrawler login/scraping is implemented. The connector ingests an already-produced MediaCrawler JSON export; when the export is missing/unreadable it degrades cleanly.
- No OCR engine binary is bundled. `extract_text_from_image` takes an injectable `engine`; with no engine, or when the engine's confidence is below threshold, it flags `needs_vision=True` so the agent reads the image with its own vision. Wiring PaddleOCR/Tesseract is a documented future config step.
- Image downloading (turning remote `asset_paths` URLs into local files) is out of scope; `asset_paths` hold the export's image references as-is.

**Prerequisite:** Plan 2 merged to `main`. Existing: `scripts/models.py` (`RawPost` with `posted_at`, `post_type`, `asset_paths`), `scripts/connectors/base.py` (`Connector`, `SearchResult.degraded`), `scripts/connectors/{github,nowcoder}.py` (established connector pattern), `scripts/resume_extract.py` (established vision-fallback pattern). Work on a branch off `main`.

---

### Task 1: Hybrid OCR module

**Files:**
- Create: `interview-intelligence/scripts/ocr/__init__.py` (empty)
- Create: `interview-intelligence/scripts/ocr/extract.py`
- Test: `interview-intelligence/tests/test_ocr_extract.py`

`extract_text_from_image(path, engine=None, min_confidence=0.6)` returns `OcrResult{text, confidence, needs_vision}`. An `engine` is any callable `(path: str) -> tuple[str, float]` returning `(text, confidence)`. Policy: no engine → `needs_vision=True`, `text=""`, `confidence=0.0`. Engine present → call it; if `confidence >= min_confidence` AND text is non-empty → `needs_vision=False`; otherwise `needs_vision=True` (keep whatever text the engine returned as a hint). This is the hybrid: coarse OCR when confident, agent-vision fallback otherwise.

- [ ] **Step 1: Create the package marker**

Create `interview-intelligence/scripts/ocr/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test** `tests/test_ocr_extract.py`

```python
from scripts.ocr.extract import extract_text_from_image, OcrResult


def test_no_engine_flags_vision():
    result = extract_text_from_image("img.png")
    assert isinstance(result, OcrResult)
    assert result.needs_vision is True
    assert result.text == ""
    assert result.confidence == 0.0


def test_confident_engine_returns_text():
    engine = lambda path: ("什么是 RAG？", 0.95)
    result = extract_text_from_image("img.png", engine=engine)
    assert result.needs_vision is False
    assert result.text == "什么是 RAG？"
    assert result.confidence == 0.95


def test_low_confidence_flags_vision_but_keeps_hint():
    engine = lambda path: ("blurry guess", 0.30)
    result = extract_text_from_image("img.png", engine=engine, min_confidence=0.6)
    assert result.needs_vision is True
    assert result.text == "blurry guess"


def test_empty_text_flags_vision_even_if_confident():
    engine = lambda path: ("", 0.99)
    result = extract_text_from_image("img.png", engine=engine)
    assert result.needs_vision is True
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_ocr_extract.py -v`
Expected: FAIL — "No module named 'scripts.ocr.extract'".

- [ ] **Step 4: Implement** `scripts/ocr/extract.py`

```python
from collections.abc import Callable
from dataclasses import dataclass

OcrEngine = Callable[[str], tuple[str, float]]


@dataclass
class OcrResult:
    text: str
    confidence: float
    needs_vision: bool


def extract_text_from_image(
    path: str, engine: OcrEngine | None = None, min_confidence: float = 0.6
) -> OcrResult:
    if engine is None:
        return OcrResult(text="", confidence=0.0, needs_vision=True)
    text, confidence = engine(path)
    needs_vision = confidence < min_confidence or not text.strip()
    return OcrResult(text=text, confidence=confidence, needs_vision=needs_vision)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_ocr_extract.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/ocr/__init__.py scripts/ocr/extract.py tests/test_ocr_extract.py
git commit -m "feat: add hybrid OCR module (injectable engine + vision fallback)"
```

---

### Task 2: 小红书 connector — MediaCrawler export parsing

**Files:**
- Create: `interview-intelligence/scripts/connectors/xiaohongshu.py`
- Test: `interview-intelligence/tests/test_xiaohongshu_connector.py`
- Test fixture: `interview-intelligence/tests/fixtures/xhs_mediacrawler_export.json`

Parses a MediaCrawler 小红书 JSON export (a list of note objects) into `RawPost`s. Field mapping per note: `note_url`→`url`; `title`+`desc`→`raw_text` (joined, stripped); `image_list` (list of image URLs)→`asset_paths`; `time` (epoch milliseconds)→`posted_at` (ISO `YYYY-MM-DD`, UTC); `post_type="image"`; `source="xiaohongshu"`. Missing/zero `time`→`posted_at=None`. The connector reads the export via an injectable `loader` (defaults to reading the file); it degrades when the loader fails (export missing → MediaCrawler hasn't been run / needs login).

- [ ] **Step 1: Create the fixture** `tests/fixtures/xhs_mediacrawler_export.json`

```json
[
  {
    "note_id": "n1",
    "note_url": "https://www.xiaohongshu.com/explore/n1",
    "title": "字节 AI 应用开发 面经",
    "desc": "一面问了 MCP 和 Skill 的区别，还有 agent 项目细节。",
    "time": 1758326400000,
    "image_list": [
      "https://sns-img.xhs.cn/n1_a.jpg",
      "https://sns-img.xhs.cn/n1_b.jpg"
    ]
  },
  {
    "note_id": "n2",
    "note_url": "https://www.xiaohongshu.com/explore/n2",
    "title": "无日期帖",
    "desc": "RAG 检索优化怎么答。",
    "time": 0,
    "image_list": ["https://sns-img.xhs.cn/n2_a.jpg"]
  }
]
```

Note: `time` `1758326400000` ms = `2025-09-20T00:00:00Z` → `posted_at` `"2025-09-20"`.

- [ ] **Step 2: Write the failing test** `tests/test_xiaohongshu_connector.py`

```python
from pathlib import Path

from scripts.connectors.base import SearchResult
from scripts.connectors.xiaohongshu import (
    parse_mediacrawler_export,
    XiaohongshuConnector,
)

FIXTURE = Path(__file__).parent / "fixtures" / "xhs_mediacrawler_export.json"
SAMPLE_JSON = FIXTURE.read_text(encoding="utf-8")


def test_parse_maps_notes_to_image_rawposts():
    posts = parse_mediacrawler_export(SAMPLE_JSON)
    assert len(posts) == 2
    first = posts[0]
    assert first.source == "xiaohongshu"
    assert first.url == "https://www.xiaohongshu.com/explore/n1"
    assert first.post_type == "image"
    assert first.posted_at == "2025-09-20"
    assert first.asset_paths == [
        "https://sns-img.xhs.cn/n1_a.jpg",
        "https://sns-img.xhs.cn/n1_b.jpg",
    ]
    assert "MCP 和 Skill 的区别" in first.raw_text
    assert "字节 AI 应用开发 面经" in first.raw_text


def test_parse_zero_time_yields_none_date():
    posts = parse_mediacrawler_export(SAMPLE_JSON)
    assert posts[1].posted_at is None


def test_connector_search_uses_injected_loader():
    conn = XiaohongshuConnector(export_path="whatever.json", loader=lambda p: SAMPLE_JSON)
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert len(result.posts) == 2
    assert result.posts[0].posted_at == "2025-09-20"


def test_connector_degrades_when_loader_fails():
    def boom(path):
        raise FileNotFoundError("no export")

    conn = XiaohongshuConnector(export_path="missing.json", loader=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "mediacrawler" in result.message.lower()
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_xiaohongshu_connector.py -v`
Expected: FAIL — "No module named 'scripts.connectors.xiaohongshu'".

- [ ] **Step 4: Implement** `scripts/connectors/xiaohongshu.py`

```python
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost


def _epoch_ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None
    return dt.date().isoformat()


def parse_mediacrawler_export(json_text: str) -> list[RawPost]:
    notes = json.loads(json_text)
    posts: list[RawPost] = []
    for note in notes:
        title = (note.get("title") or "").strip()
        desc = (note.get("desc") or "").strip()
        raw_text = "\n".join(part for part in (title, desc) if part)
        posts.append(
            RawPost(
                source="xiaohongshu",
                url=note.get("note_url", ""),
                post_type="image",
                raw_text=raw_text,
                posted_at=_epoch_ms_to_iso(note.get("time")),
                asset_paths=list(note.get("image_list") or []),
            )
        )
    return posts


def _default_loader(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


class XiaohongshuConnector(Connector):
    name = "xiaohongshu"

    def __init__(self, export_path: str, loader: Callable[[str], str] | None = None):
        self.export_path = export_path
        self.loader = loader or _default_loader

    def search(self, queries: list[str]) -> SearchResult:
        try:
            posts = parse_mediacrawler_export(self.loader(self.export_path))
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(
                self.name,
                f"无法读取 MediaCrawler 导出 ({exc});请先用 MediaCrawler 登录并采集小红书笔记，导出 JSON 后再试",
            )
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")
```

Note: `queries` is accepted for interface symmetry; the connector ingests the given export file (the user runs MediaCrawler with their own keywords). Do NOT implement live scraping or login here.

- [ ] **Step 5: Run to verify it passes**

Run: `cd interview-intelligence && .venv/bin/pytest tests/test_xiaohongshu_connector.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/connectors/xiaohongshu.py tests/test_xiaohongshu_connector.py tests/fixtures/xhs_mediacrawler_export.json
git commit -m "feat: add 小红书 connector parsing MediaCrawler export to dated image RawPosts"
```

---

### Task 3: Update SKILL.md for 小红书 + OCR

**Files:**
- Modify: `interview-intelligence/SKILL.md`

- [ ] **Step 1: Add tools** — in the `## 工具` section, add these lines (after the `nowcoder.py` line and after the `dedupe_rank.py` line respectively):
```
- `scripts/connectors/xiaohongshu.py` → `XiaohongshuConnector(export_path).search(queries) -> SearchResult`
- `scripts/ocr/extract.py` → `extract_text_from_image(path, engine=None, min_confidence=0.6) -> OcrResult{text, confidence, needs_vision}`
```

- [ ] **Step 2: Update the source-priority sentence in step 3.** Find the line that begins `3. **迭代检索。** 源的优先级:` and replace just that first sentence so it reads:
```
3. **迭代检索。** 源的优先级:**牛客 + 小红书(主力,带时间戳)> GitHub(补充,常过时)**。把发现的牛客帖子 URL 传给 `NowCoderConnector(post_urls).search(...)`;小红书先用 MediaCrawler 采集导出 JSON,再传给 `XiaohongshuConnector(export_path).search(...)`;把 GitHub 仓库 raw URL 传给 `GithubConnector(repo_raw_urls).search(...)`。三者结果都用 `save_raw_posts` 落盘。读取结果,**收割真实出现的岗位名 / 标签 / 高频术语**,再用收割到的词跑下一轮,直到不再冒出新词。若某 connector 返回 `status="degraded"`(例如牛客需要 cookie、小红书需要先跑 MediaCrawler),把它需要的东西告诉用户;主力源降级会显著影响时效性,必须明确提示用户,不要默默用 GitHub 凑数。
```

- [ ] **Step 3: Update step 5 (题目抽取) to cover image posts via OCR.** Replace the step-5 line with:
```
5. **题目抽取。** 文本类 RawPost 直接读。**图片类 RawPost(小红书,`post_type="image"`)**:对每个 `asset_paths` 里的图片调用 `extract_text_from_image(path, engine)`;若返回 `needs_vision=True`(没接 OCR 引擎或置信度低),就用你自己的视觉能力直接读这张图。把读到的题目转成标准化的 `Question`,图片来源的设 `modality_origin="ocr"` 或 `"vision"`。用 `save_questions` 落盘。
```

- [ ] **Step 4: Update the constraints.** Replace the line `- 当前源:牛客(主力)+ GitHub(补充)。小红书 + OCR 在后续 plan。` with:
```
- 当前源:牛客 + 小红书(主力,带时间戳)+ GitHub(补充)。
- 小红书走 MediaCrawler 采集导出,OCR 采用混合策略(粗 OCR + 视觉回退);MediaCrawler 仅供个人、非商业用途。
```

- [ ] **Step 5: Validate front-matter and commit**

Run: `cd interview-intelligence && .venv/bin/python -c "t=open('SKILL.md').read(); assert t.startswith('---'); fm=t.split('---')[1]; assert 'name:' in fm and 'description:' in fm; print('OK')"`
Expected: prints `OK`.
```bash
git add SKILL.md
git commit -m "docs: wire 小红书 connector and hybrid OCR into SKILL.md workflow"
```

---

### Task 4: Full suite + schema doc update

**Files:**
- Modify: `interview-intelligence/assets/schema.md`

- [ ] **Step 1: Run the whole suite green**

Run: `cd interview-intelligence && .venv/bin/pytest -q`
Expected: all pass (Plan 2's 31 + Task1's 4 + Task2's 4 = 39).

- [ ] **Step 2: Add an image-post note to `assets/schema.md`.** Append this paragraph to the end of the file:
```markdown

## Image posts & OCR

Image-based posts (小红书) use `post_type="image"`, carry image references in `asset_paths`, and
usually have empty/short `raw_text` (caption only). Their questions are extracted by
`ocr/extract.py` `extract_text_from_image(path, engine=None)`: a coarse OCR engine when one is
wired and confident, otherwise `needs_vision=True` and the agent reads the image directly. The
resulting `Question.modality_origin` is `"ocr"` or `"vision"` accordingly.
```

- [ ] **Step 3: Commit**

```bash
git add assets/schema.md
git commit -m "docs: document image posts and hybrid OCR in schema"
```

---

## Self-Review

**Spec coverage:**
- 小红书 source (image-based, MediaCrawler adapter) → Task 2 + SKILL step 3 (Task 3). ✓
- Hybrid OCR (coarse OCR + vision fallback) → Task 1 + SKILL step 5 (Task 3). ✓
- `posted_at` carried from 小红书 (epoch ms → ISO) → Task 2; feeds the existing recency filter/ranking from Plan 2. ✓
- MediaCrawler non-commercial constraint recorded → SKILL constraints (Task 3). ✓
- Connector degrade pattern preserved (export missing) → Task 2. ✓
- Schema doc updated for image posts/OCR → Task 4. ✓
- Deferred (correctly out of scope): live MediaCrawler login/scraping; real OCR engine wiring;
  image downloading; ASR sources (抖音/B站); interactive mock — all noted in the scope section.

**Placeholder scan:** No TBD/TODO; every code step has complete code; commands have expected output.

**Type consistency:**
- `RawPost(source, url, post_type, raw_text, posted_at=..., asset_paths=...)` field names match the
  V1/Plan-2 model used in Task 2.
- `OcrResult{text, confidence, needs_vision}` and `extract_text_from_image(path, engine=None,
  min_confidence=0.6)` identical across Task 1, its tests, SKILL tools list, and schema doc.
- `parse_mediacrawler_export(json_text) -> list[RawPost]` and
  `XiaohongshuConnector(export_path, loader=None).search(queries) -> SearchResult` consistent in
  Task 2 and SKILL tools list (Task 3).
- `SearchResult` / `Connector` / `SearchResult.degraded` reused unchanged from V1.
