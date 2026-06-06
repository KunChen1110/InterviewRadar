---
name: interview-radar
description: 面试准备 / interview prep。当用户上传简历(PDF/图片)并给出一个模糊的目标岗位方向(例如"AI 应用开发""市场实习")时使用。广撒网检索真实面经(主力源:牛客 + 小红书;补充源:GitHub + 通用正文页),只保留近两年内容,去重并按频次+时效排序,结合用户简历生成带项目追问的个性化备考包。
---

# InterviewRadar · 面试雷达 Skill

把「简历 + 模糊岗位」变成一份**基于真实面经内容**的个性化备考包。你(agent)负责推理判断;`scripts/` 下的 Python 脚本负责确定性的脏活。两者通过 `corpus_cache/` 里的 JSON 文件交互。

## 输入
- 简历:PDF、图片或文本文件路径。
- 模糊岗位:一个方向,例如"AI 应用开发"(**不是**具体的 JD)。

## 工具(用包内 venv 运行:`.venv/bin/python`)
- `scripts/resume_extract.py` → `extract_resume(path) -> ResumeExtraction{text, needs_vision, asset_path}`
- `scripts/connectors/github.py` → `GithubConnector(repo_raw_urls).search(queries) -> SearchResult`
- `scripts/connectors/nowcoder.py` → `NowCoderConnector(post_urls).search(queries) -> SearchResult`
- `scripts/connectors/xiaohongshu.py` → `XiaohongshuConnector(export_path=..., driver=...).search(queries) -> SearchResult`(二选一:`export_path` 读预生成的 JSON;`driver` 自动跑 MediaCrawler;图片会下载/OCR 后作为主正文)
- `scripts/scrape/mediacrawler_driver.py` → `MediaCrawlerDriver(home=None).scrape_xhs(keywords, login_type="qrcode"|"cookie") -> Path`,**驱动模式**——shell out 调本机已装的 MediaCrawler(默认从 `$MEDIACRAWLER_HOME` 或 `~/.mediacrawler/` 找)。推荐 cookie 登录:在 MediaCrawler `config/base_config.py` 里设置 `LOGIN_TYPE = "cookie"` 和 `COOKIES = "web_session=<value>"`。
- `scripts/scrape/normalize_xhs.py` → `normalize(notes) -> list[dict]`(CLI:`python -m scripts.scrape.normalize_xhs <in.json> -o <out.json>`),把 MediaCrawler 原生输出归一化为 `XiaohongshuConnector` 的输入。仅手动模式用得到;driver 模式连接器内部自动调用。
- `scripts/ocr/extract.py` → `extract_text_from_image(path, engine=None, min_confidence=0.6) -> OcrResult{text, confidence, needs_vision}`
- `scripts/ocr/xhs_images.py` → 下载小红书 `image_list`,默认探测 RapidOCR,把分页 OCR 合并进 `RawPost.content_text/raw_text`;低质量时设 `needs_vision_fallback=True`
- `scripts/corpus/store.py` → `save_raw_posts / load_raw_posts / save_questions / load_questions`
- `scripts/corpus/recency.py` → `filter_recent(posts, window_days=730, today=None) -> list[RawPost]`
- `scripts/corpus/dedupe_rank.py` → `dedupe_and_rank(questions) -> list[Question]`
- 数据模型在 `scripts/models.py`;结构说明见 `assets/schema.md`。

## 工作流

0. **准备(仅当启用小红书源)。** 两种模式二选一,见 `docs/setup/mediacrawler.md`:
   - **driver 模式(推荐)**:用户**一次性**装 MediaCrawler 并登录。优先用 cookie 模式:从正常浏览器复制 `web_session`,写入 MediaCrawler `config.COOKIES`,然后用 `XiaohongshuConnector(driver=MediaCrawlerDriver(), login_type="cookie")` 自动跑采集。二维码模式仍可用,但更容易触发风控。
   - **手动模式**:用户每次自己跑 MediaCrawler + `normalize_xhs.py`,把 `corpus_cache/xhs_export.json` 喂给 `XiaohongshuConnector(export_path=...)`。
   文本/牛客/GitHub 源不需要这一步。

1. **简历理解。** 调用 `extract_resume`。若 `needs_vision` 为真,就用你自己的视觉能力直接读这张图片/PDF。产出结构化摘要:技能、项目(每个项目用到的技术)、关键术语。

2. **种子查询生成。** 用你**自己的领域知识**,从「岗位方向 + 简历」推导出种子查询。这是领域无关的:无论什么领域(市场、量化、后端、设计……)你本来就知道相关的岗位别名和底层技能/话题,当场生成即可。**不要依赖任何预设词表。** 种子来自两处:(a) 岗位方向隐含的相关岗位别名;(b) 从简历里抽出的具体技能/项目/关键词。优先用底层技能/话题词,而不是岗位名——它们更稳定、召回更好。

3. **迭代检索。** 源的优先级:**牛客 + 小红书(主力,带时间戳)> GitHub(补充,常过时)**。

   **3a. URL 发现(每轮先做)。** 用你的搜索能力(WebSearch 或等价工具)对当前的种子查询跑一遍,收集候选 URL。按域名分桶:
   - `nowcoder.com/discuss/<post_id>` → 进 `NowCoderConnector(post_urls=...)`
   - `xiaohongshu.com/explore/<note_id>` → **不能直抓**;如果启用了小红书源,把当前的关键词丢给 `XiaohongshuConnector(driver=MediaCrawlerDriver()).search([keywords])`,它会自动 shell out 跑 MediaCrawler。若未启用,记下笔记 ID 让用户按 `docs/setup/mediacrawler.md` 配置
   - `github.com/<owner>/<repo>/blob/<branch>/<path>` 或 `raw.githubusercontent.com/...` → 转 raw URL → 进 `GithubConnector(repo_raw_urls=...)`
   - **其他公开正文页**(知乎 article、CSDN 文章、个人博客、woshipm/uisdc 等):用 WebFetch 拉回正文,自己手工构造 `RawPost(source="webfetch:<domain>", post_type="text", raw_text=<正文>, posted_at=<页面可见日期或 None>)`,和 connector 结果一起 `save_raw_posts`

   显式排除:聚合/listing 页(只接 article 页);403/需登录的页面(不浪费 fetch 配额,记下来当作知识缺口告诉用户)。

   **3b. 调 connectors + 收割。** 把分好桶的 URL 喂给对应 connector,结果用 `save_raw_posts` 落盘。读取结果,**收割真实出现的岗位名 / 标签 / 高频术语**,用收割到的词跑下一轮 3a,直到不再冒出新词。若某 connector 返回 `status="degraded"`(例如牛客需要 cookie、小红书需要先跑 MediaCrawler、或消息含 `selector` 表示 HTML 漂移),把它需要的东西告诉用户;主力源降级会显著影响时效性,必须明确提示用户,不要默默用 GitHub 凑数。

   **GitHub 调用必带 `relevance_hints`(不要传 `None` 或 `[]`)。** GitHub 仓库里夹带大量算法/八股,不过滤会严重污染语料。`GithubConnector(repo_raw_urls=..., relevance_hints=<当前一轮的术语/岗位别名>)`。**冷启动**(第一轮还没有收割结果)时,直接把步骤 2 的种子查询当 hints 传进去——任何时候都要传非空 list。命中规则:子串、大小写不敏感,只要正文里出现任一 hint 就保留。

   **Human-in-the-loop:** 在最后一轮之前,把你从真实数据里发现的方向/术语展示给用户,让他增删/纠偏。

4. **内容级相关性判定。** 通过**读帖子内容**对照用户岗位 + 简历来判断每条是否相关——**不是**靠帖子的岗位名是否匹配某张预设表。

5. **题目抽取。** 文本类 RawPost 直接读。**图片类 RawPost(小红书,`post_type="image"`)**:默认读 `content_text/raw_text`,它优先来自图片 OCR;标题、caption、tags 只在 `locator_text` 里做召回/定位。若 `needs_vision_fallback=True`,用你自己的视觉能力按 `asset_paths` 顺序补读图片。把读到的题目转成标准化的 `Question`,图片来源的设 `modality_origin="ocr"` 或 `"vision"`。用 `save_questions` 落盘。

5b. **时效过滤。** 在抽取出题目之前,先用 `filter_recent(raw_posts)` 把超过约两年的帖子丢掉(默认窗口 730 天;`posted_at` 为 None 的无日期帖子保留)。时效性是硬需求——过时的面经没有价值。

6. **去重 & 排序。** 跑 `dedupe_and_rank(load_questions(...))` 并保存排序结果。排序同时考虑**频次和时效**(近期题加权更高),这就是高频题集。

7. **项目锚定推理。** 对每道高频题,检查它能否挂到简历里的某个项目/技能上。能挂上就构造 `FollowUpChain`(种子题 → 个性化追问,`is_grounded=true`)。每个追问都**必须**能追溯到(简历某项目/技能)+(某条真实爬到的题);追溯不上就设 `is_grounded=false`,当普通八股题保留。**不要凭空编追问。**

8. **备考包。** 严格按下面的固定模板写 Markdown,保存到 `corpus_cache/prep_package.md` 并展示给用户。不要自由发挥改大结构;若某部分数据不足,写清"数据不足/未覆盖",不要编。

## 备考包固定模板

```markdown
# {目标岗位}岗位备考包 — {候选人姓名或"候选人"}

生成日期:{YYYY-MM-DD}
目标岗位:{用户给定岗位 + 从真实数据收割到的岗位别名}

## 1. 你的候选人定位

用 1 段话定义候选人的面试包装方向。格式:

> {一句候选人定位}

简历里最强的三个证据:

1. **{项目/经历 1}**
   - {证据点 1}
   - {证据点 2}
   - {适合回答什么面试问题}

2. **{项目/经历 2}**
   - ...

3. **{项目/经历 3}**
   - ...

## 2. 岗位 Gap 分析

| 维度 | 当前简历表现 | 面试风险 | 准备建议 |
|---|---|---|---|
| {能力维度} | {基于简历的证据} | {真实面经会追问的风险} | {可执行补强建议} |

至少覆盖:技术理解、产品基本功、业务 sense、数据/实验、落地可信度。非 AI 岗位时把维度换成该岗位的核心能力。

## 3. 真实数据来源概况

本次召回:

- {来源 1}:{数量/状态/保存路径}
- {来源 2}:{数量/状态/保存路径}

数据缺口:

- {降级源、OCR/反爬/时间戳缺口等}

## 4. 高频题 Top {N}

### {序号}. {题目}

来源:
- {source title 或 source type}:`{url}`
- ...

回答要点/回答框架:

- {要点 1}
- {要点 2}
- {要点 3}

可挂简历锚点:

> {把这题连接到候选人某个项目/技能的一段话}

如果适合表格解释,可以用小表格;否则用 bullet。每题必须至少有 1 个真实来源。没有来源的题不能进 Top 高频题。

## 5. 个性化项目追问链

### 链 {序号}:{主题} → {简历项目/经历}

种子题:{来自第 4 节的高频题}

追问:

1. {追问 1}
2. {追问 2}
3. {追问 3}
4. {追问 4}
5. {追问 5}

准备重点:

- {如何准备真实例子/图/指标}
- {面试时要强调的产品视角}

每条追问必须同时能追溯到"真实面经题目"和"简历项目/技能";追溯不上就不要写成个性化追问。

## 6. 你的 60-90 秒自我介绍草稿

写 2-3 段中文口语稿。必须包含:

- 背景
- 目标岗位动机
- 2-3 个最强项目证据
- 候选人的差异化定位

## 7. 一周冲刺计划

### Day 1:{主题}

- {行动项}
- {行动项}

...

### Day 7:{主题}

- {行动项}
- {行动项}

## 8. 建议你立刻补强的简历表述

### {项目/经历 1}

补:

> {可直接放进简历/面试话术的改写}

### {项目/经历 2}

补:

> ...

## 9. 来源列表

按来源类型分组列出代表来源:

小红书:
- `{url}` — {一句说明}

牛客/网页/GitHub:
- `{url}` — {一句说明}

## 10. 面试前速查清单

- 60 秒自我介绍
- {3 个最能证明岗位匹配度的项目/经历证据}
- {3 个真实 trade-off / 失败 / 返工案例}
- {5 个目标岗位必会高频题;例如 AI 产品岗可写 RAG、Agent、实验、指标、产品设计,其他岗位按真实面经替换}
- {4 个高质量反问}
- {可以展示的作品、流程图、数据、文档或代码证据}
```

模板约束:
- 全文中文,但技术名词可保留英文。
- 第 4 节的题目必须来自 `Question` 或明确可追溯的 `RawPost.content_text/raw_text`;小红书 caption/tag 只作为 `locator_text` 辅助,不能单独生成题目。
- 高频题优先按 `dedupe_and_rank` 结果排序;人工调整时只能因岗位相关性或简历匹配度调整,并说明依据。
- 来源 URL 必须真实存在于 `source_refs` 或 RawPost.url;不要写"综合资料"这类不可追溯来源。
- 自我介绍和简历表述可以做表达优化,但事实必须来自简历或真实面经。
- 第 10 节必须按用户目标岗位动态生成,不要写死为 AI 产品题;AI 产品只是示例。

## 约束
- **所有面向用户的产出一律用中文**(备考包、题目、追问、分析)——面经源是中文。
- 当前源:牛客 + 小红书(主力,带时间戳)+ GitHub(补充)。
- 小红书走 MediaCrawler 采集导出(用户预先离线跑一次,流程见 `docs/setup/mediacrawler.md`),OCR 采用混合策略(粗 OCR + 视觉回退);MediaCrawler 仅供个人、非商业用途。
- 时效性是硬需求:只保留近两年的面经,排序向近期加权。
- 后续版本用到的第三方爬虫(如 MediaCrawler)仅供个人、非商业用途。
- **可追溯优先于流畅度**:绝不编造无法追溯到真实数据的题目或追问。
- 若 connector 返回 `degraded` 且消息含 `selector`,说明源站点 HTML 改了选择器;到对应 `scripts/connectors/<name>.py` 顶部注释看当前假设,核对真实 HTML 后更新选择器并补 fixture。
