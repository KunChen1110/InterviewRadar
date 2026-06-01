<div align="center">

<img src="assets/logo.png" alt="InterviewRadar" width="200"/>

# InterviewRadar · 面试雷达

**基于真实面经,从你的简历自动生成项目锚定的个性化中文面试备考包**

[![tests](https://github.com/KunChen1110/InterviewRadar/actions/workflows/tests.yml/badge.svg)](https://github.com/KunChen1110/InterviewRadar/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](#)
[![Claude Skill](https://img.shields.io/badge/Claude-Skill-purple.svg)](#)

</div>

---

## 它解决什么问题

市面上的"面试题库"几乎都是静态的,而面试官手里的题是动态的、时效的、个性化的。

- 你刷的 1000 道八股题里,**真正会被问到的可能不到 10%**——因为面试官是按你简历来问的,不是按题库目录
- 牛客 / 小红书的真实面经满天飞,但**没人帮你从里面挖出"跟你简历相关、且最近半年高频"的那一小撮**
- LLM 直接生成的面试题听起来像那么回事,但**没法溯源**——你不知道这道题真有人被问过吗

InterviewRadar 是一个 Claude Skill,把"你给的"变成"它给你的":

| 你给的 | 它做的 | 它给你的 |
|---|---|---|
| • 简历(PDF / 图片 / 扫描件)<br>• 一句**模糊**岗位方向<br>&nbsp;&nbsp;&nbsp;&nbsp;(例:"AI 应用开发""市场实习") | • 多源抓取真实面经<br>&nbsp;&nbsp;&nbsp;&nbsp;(牛客 + 小红书 + GitHub + 公开博客)<br>• 近两年时效**硬过滤**<br>• 频次 × 时效加权排序<br>• 把每道高频题尝试**挂到你简历里的项目**上<br>• LLM 推理 + Python 脚本各司其职<br>&nbsp;&nbsp;&nbsp;&nbsp;(领域无关,不依赖预设词表) | • 一份中文 Markdown **备考包**<br>• **可追溯**的、锚定到你项目的<br>&nbsp;&nbsp;&nbsp;&nbsp;**连环追问链**,而不是凭空编<br>• **任意领域**都能跑——不止 AI 岗 |

## 看一眼输出

> 给一份"3 个项目、目标 Agent 应用开发岗"的简历,跑出来长这样(节选):

```markdown
## 2. 简历 ↔ 岗位 Gap 分析

| 维度 | 现状 | 评级 |
|---|---|---|
| Agent Orchestration | P1 已实现多阶段状态机 | ✅ 强 |
| MCP 协议 | 简历未提 | ❌ 弱 |
| Function Calling 工程细节 | 没专门讲 | ⚠️ 中 |
...

## 4. 个性化项目追问链(锚到你的简历)

### 链 4.1 — 高频题 #3 → P1 多阶段状态机

> Q1: "你 P1 项目里设计了 Understanding → Diagnose → ... 这套状态机,
>      具体是怎么拆解出这六个阶段的?"
> Q2: "这套流程对应 ReAct / Plan-and-Execute / Reflexion 里的哪种范式?"
> Q3: "哪个阶段最容易出问题?你是怎么调的?"
```

完整样例:见 [`examples/sample_prep_package.md`](examples/sample_prep_package.md)

## 快速开始

**前置**:已安装 [Claude Code](https://claude.ai/code)(本项目是一个 Claude Skill)。

```bash
git clone https://github.com/KunChen1110/InterviewRadar.git
cd InterviewRadar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

然后**在 Claude Code 里**对它说:

```
用 InterviewRadar 跑一下:
简历 /path/to/your-resume.pdf
方向:AI 应用开发岗
```

Claude 会自动:
1. 读简历(支持文字 PDF + 图片 + 扫描件)
2. 用 WebSearch 发现牛客 / 公开正文页 URL
3. 按域名分桶,调对应 connector 抓取
4. 时效过滤(默认 730 天)+ 频次×时效排序
5. 项目锚定生成追问链
6. 输出中文备考包到 `corpus_cache/prep_package.md`

> 想接小红书源(很多笔记面经)?见 [`docs/setup/mediacrawler.md`](docs/setup/mediacrawler.md)。MediaCrawler 仅供个人非商用。

## 它怎么工作

<div align="center">
  <img src="assets/workflow.png" alt="InterviewRadar workflow" width="900"/>
</div>

<details>
<summary>等价的 Mermaid 流程图(技术细节)</summary>

```mermaid
flowchart TD
    R["简历 PDF / 图片"] --> A
    D["模糊岗位方向"] --> A
    A["Agent (Claude)"] --> S1["Step 1<br/>简历理解<br/>pypdf + 视觉回退"]
    S1 --> S2["Step 2<br/>种子查询<br/>agent 当场推,不依赖预设词表"]
    S2 --> S3a["Step 3a<br/>WebSearch 发现 URL<br/>按域名分桶"]
    S3a --> S3b["Step 3b: dispatch connector"]
    S3b --> C1["NowCoder<br/>(官方 discuss)"]
    S3b --> C2["Xiaohongshu<br/>(via MediaCrawler)"]
    S3b --> C3["GitHub raw<br/>(with hints filter)"]
    S3b --> C4["WebFetch<br/>(知乎 / CSDN / ...)"]
    C1 --> S45["Step 4-5<br/>内容相关性 + 题目抽取<br/>文本 / OCR / 视觉"]
    C2 --> S45
    C3 --> S45
    C4 --> S45
    S45 --> S6["Step 6<br/>时效过滤 730d 硬截断<br/>频次 × 时效排序"]
    S6 --> S7["Step 7<br/>项目锚定推理<br/>高频题 ↔ 简历项目"]
    S7 --> OUT["prep_package.md (中文)"]

    classDef in fill:#fff3cd,stroke:#856404
    classDef stage fill:#d1ecf1,stroke:#0c5460
    classDef src fill:#d4edda,stroke:#155724
    classDef out fill:#f8d7da,stroke:#721c24
    class R,D in
    class S1,S2,S3a,S3b,S45,S6,S7 stage
    class C1,C2,C3,C4 src
    class OUT out
```

</details>

**分工原则**:
- agent(Claude)做**推理判断**:领域知识、种子词生成、URL 分桶、项目锚定
- Python 脚本做**确定性脏活**:HTML 解析、时效过滤、去重排序、降级处理
- 两者通过磁盘 JSON 解耦,可独立调试

## 它的差异化

| | 静态题库(JavaGuide / Xiaolincoding / GitHub repo) | LLM 直接出题 | **InterviewRadar** |
|---|---|---|---|
| 时效 | ❌ 经常陈旧 | ⚠️ 不可控 | ✅ 730d 硬过滤 |
| 个性化 | ❌ 不看你简历 | ⚠️ 听起来像但不溯源 | ✅ 项目锚定 + `is_grounded` 标记 |
| 可追溯 | ✅ 但散落 | ❌ 编的就是编的 | ✅ 每条题 / 追问都带源链接 |
| 跨领域 | ❌ 一仓一岗 | ✅ | ✅(不依赖预设词表) |
| 多源 | ❌ 单一 | ❌ 不爬 | ✅ 牛客 / 小红书 / GitHub / 通用正文页 |

## 项目结构

```
InterviewRadar/
├── SKILL.md                     ← Claude Skill 的入口工作流
├── scripts/
│   ├── resume_extract.py        简历理解(文本/视觉回退)
│   ├── connectors/              source connectors:
│   │   ├── nowcoder.py            ├─ 牛客 (选择器漂移守卫 + anti-bot 半空守卫)
│   │   ├── xiaohongshu.py         ├─ 小红书 (吃 MediaCrawler 导出)
│   │   └── github.py              └─ GitHub (relevance_hints 过滤算法噪音)
│   ├── corpus/
│   │   ├── store.py             RawPost / Question 存取
│   │   ├── recency.py           时效过滤(730d)
│   │   └── dedupe_rank.py       去重 + 频次×时效排序(未标日期降权 0.2)
│   ├── ocr/extract.py           OCR + 视觉回退
│   └── scrape/normalize_xhs.py  MediaCrawler 输出适配器
├── tests/                       58 单测(TDD)
├── docs/
│   ├── specs/                   3 份设计文档
│   ├── plans/                   6 份实施计划
│   └── setup/mediacrawler.md    小红书源接入指引
├── examples/                    跑通的样例输出
└── corpus_cache/                运行时产物(gitignored)
```

## 开发

```bash
# 跑所有测试
.venv/bin/python -m pytest tests/ -v

# 跑某个 connector 的测试
.venv/bin/python -m pytest tests/test_nowcoder_connector.py -v
```

**怎么加新源**:实现 `Connector` ABC(见 `scripts/connectors/base.py`),返回 `SearchResult`。降级时用 `SearchResult.degraded(name, msg)`,绝不抛异常打断管道。

**怎么调整时效窗口 / 排序权重**:见 `scripts/corpus/recency.py` 和 `scripts/corpus/dedupe_rank.py`,纯函数,容易改 + 测试覆盖好。

## Roadmap

- [ ] **Plan 7**:文本 → 题目自动抽取(目前 agent 端读 raw_text 合成,缺一个 `extract_questions()` 函数把 `dedupe_and_rank` 接进真实管道)
- [ ] **Plan 8**:端到端集成测试 + GitHub Actions CI
- [ ] 持久化:跨 session 累积高频术语词典
- [ ] 抖音视频源(若发现高密度文本转录)
- [ ] 评测体系:Golden Set + Trace 回放

## 贡献

欢迎 issue / PR。开发流程一律走 `docs/specs/` → `docs/plans/` → TDD → 二阶段 review。可以翻看 `docs/plans/` 找现成的范本。

## 免责

仅供个人非商用。使用本工具拉取数据的合规性由用户自担。详见 [DISCLAIMER.md](DISCLAIMER.md)。

## License

MIT © 2026 Kun Chen
