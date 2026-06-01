# MediaCrawler 适配器 + 设置文档 — Design Spec

**Date:** 2026-05-31
**Status:** Approved (brainstorm)
**Predecessors:** `2026-05-28-interview-intelligence-skill-design.md`; Plans 1/2/3 merged.

## 1. Goal

让用户能用开源 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 真实抓取小红书面经,产出能被 Plan 3 的 `XiaohongshuConnector` 直接消费的 JSON。

## 2. Scope

In scope:

- 一个文件级适配器 `scripts/scrape/normalize_xhs.py`,把 MediaCrawler 原生 小红书 输出归一化为 connector 期望的 schema。CLI 可独立运行。
- 一份 `docs/setup_mediacrawler.md` 设置文档:用户怎么 clone MediaCrawler、登录、跑搜索、把输出交给适配器。
- `SKILL.md` 增补一条「可选 0. 准备」步骤,指向设置文档,并说明适配器输出即 connector 输入。
- Fixture-based 单元测试。无网络、无 subprocess。

Out of scope (deliberately):

- Vendor MediaCrawler(不作为 submodule / 不写自动 clone)。
- 自动登录、cookie 管理、调度。
- 图片下载。
- 牛客 / GitHub / OCR 模块改动。
- 真实端到端拉取(这就是 offline 路线的初衷)。

## 3. Architecture

```
┌─────────────────┐    ┌──────────────────────────┐    ┌─────────────────────┐
│ MediaCrawler    │    │ scripts/scrape/          │    │ scripts/connectors/ │
│ (用户自己装并跑)  │ →  │ normalize_xhs.py         │ →  │ xiaohongshu.py      │
│ xhs_notes_*.json│    │ (适配器,纯文件IO)         │    │ (Plan 3, 不动)       │
└─────────────────┘    └──────────────────────────┘    └─────────────────────┘
```

文件级解耦:适配器和 connector 之间只通过磁盘上的 JSON 文件交流。MediaCrawler 改了输出格式只动适配器,connector 一行不用改。

## 4. Adapter contract

**输入:** MediaCrawler 小红书 notes JSON 文件路径(假设字段——会在实现阶段对照真实样本调整):

```jsonc
[
  {
    "note_id": "...",
    "type": "normal" | "video",
    "title": "...",
    "desc": "...",
    "time": 1758326400000,           // epoch ms
    "image_list": "url1,url2"        // MediaCrawler often joins as comma string
       | ["url1", "url2"],           // or list — adapter must accept both
    "tag_list": "面经,实习",          // optional
    "note_url": "...",               // sometimes missing; adapter synthesizes from note_id
    "liked_count": "1.2万",          // out of scope, dropped
    "comments": [ ... ]              // out of scope, dropped
  }
]
```

**输出:** Plan 3 `parse_mediacrawler_export` 已经接受的 schema:

```jsonc
[
  {
    "note_id": "...",
    "note_url": "https://www.xiaohongshu.com/explore/<note_id>",
    "title": "...",
    "desc": "...",
    "time": 1758326400000,
    "image_list": ["url1", "url2"]
  }
]
```

**映射规则:**

- `note_url` 缺失 → 用 `note_id` 合成 `https://www.xiaohongshu.com/explore/<note_id>`;两者都缺 → 跳过该条。
- `image_list` 是字符串 → split `,` 并去空;是列表 → 原样;缺失 → `[]`。
- `time` 解析失败或 `0` → 输出仍写 `0`(下游已经把 `0` 视作 `posted_at=None`)。
- `title` / `desc` 缺失 → 空串。
- 其它 MediaCrawler 字段一律丢弃。
- 顺序保持。

**CLI:**

```
python -m scripts.scrape.normalize_xhs <input.json> -o <output.json>
```

写完打印 `wrote N notes to <output.json>`(N 是输出条数,可能少于输入,因为跳过了无 id 的)。

## 5. Setup doc structure (`docs/setup_mediacrawler.md`)

简短、命令为主、不复述 MediaCrawler 文档:

1. 前提(Python 3.11+、git、浏览器)
2. `git clone https://github.com/NanmiCoder/MediaCrawler.git` 到 skill 仓库**外面**(强调不放进来)
3. 跟 MediaCrawler README 装依赖
4. 登录步骤(指 MediaCrawler 的 QR / cookie 文档,不复述)
5. 跑搜索命令模板(以小红书 + 关键词为例)
6. 找输出文件位置
7. 用适配器归一化:`python -m scripts.scrape.normalize_xhs <mc输出> -o corpus_cache/xhs_export.json`
8. 把 `corpus_cache/xhs_export.json` 喂给 skill / `XiaohongshuConnector(export_path=...)`
9. 提示:**仅供个人非商业用途**;关键词建议(岗位别名)

## 6. SKILL.md change

新增「**0. 准备(仅当启用小红书)**」段落,放在工作流第 1 步之前,指向 `docs/setup_mediacrawler.md`,一句话:「适配器输出 = `XiaohongshuConnector(export_path=...)` 的输入」。其他步骤保持不变。

## 7. Testing strategy

完全 fixture-based,不连网:

- Fixture A:一份手写的伪 MediaCrawler 输出 JSON,覆盖以下情况:
  - 正常 note(有 `note_url`、`image_list` 列表)
  - `image_list` 是逗号字符串
  - 缺 `note_url`、但有 `note_id`(应合成 URL)
  - 缺 `note_id` 和 `note_url`(应跳过)
  - `time=0`、缺 `title`、缺 `desc`(应保留并空串/0)
  - 含 MediaCrawler 多余字段(`liked_count`、`comments`)(应丢弃)
- 单元测试:
  - `normalize(mc_notes) -> list[dict]` 直接断言映射规则
  - CLI 走文件 IO,写出后读回,字段集严格等于预期
- 端到端串通测试:适配器输出文件喂给 Plan 3 的 `parse_mediacrawler_export`,断言 RawPost 字段(尤其 `posted_at`、`asset_paths`)正确。

## 8. Risks / open questions

- **真实 MediaCrawler 字段名是基于公开仓库的推测。** 实现 PR 里实施者必须在 commit 信息或代码注释里列出适配器对每个字段的具体假设;如果用户跑过后发现某字段不对,后续小 PR 改 fixture + 映射即可。这是适配器解耦的全部价值——风险被关在一个文件里。
- MediaCrawler 自己的输出 schema 在跨版本演化时可能再变;我们不做 schema 版本协商,出错就让 normalize 报错,文档里写「如果适配器报错,可能是 MediaCrawler 升级了 schema,提 issue」。

## 9. Deferred for later

- 自动 install / 自动登录 / 抓视频(抖音、B 站走 ASR)
- 图片下载
- `validate_export` 命令(用户提议过,先不做;normalize 已经会在数据怪时报错)
- 牛客也走类似适配器路线(目前牛客直接从 HTML 解析,够用)
