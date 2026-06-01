---
name: interview-intelligence
description: 面试准备 / interview prep。当用户上传简历(PDF/图片)并给出一个模糊的目标岗位方向(例如"AI 应用开发""市场实习")时使用。广撒网检索真实面经(主力源:牛客;补充源:GitHub),只保留近两年内容,去重并按频次+时效排序,结合用户简历生成带项目追问的个性化备考包。
---

# 面试情报 Skill(Interview Intelligence）

把「简历 + 模糊岗位」变成一份**基于真实面经内容**的个性化备考包。你(agent)负责推理判断;`scripts/` 下的 Python 脚本负责确定性的脏活。两者通过 `corpus_cache/` 里的 JSON 文件交互。

## 输入
- 简历:PDF、图片或文本文件路径。
- 模糊岗位:一个方向,例如"AI 应用开发"(**不是**具体的 JD)。

## 工具(用包内 venv 运行:`.venv/bin/python`)
- `scripts/resume_extract.py` → `extract_resume(path) -> ResumeExtraction{text, needs_vision, asset_path}`
- `scripts/connectors/github.py` → `GithubConnector(repo_raw_urls).search(queries) -> SearchResult`
- `scripts/connectors/nowcoder.py` → `NowCoderConnector(post_urls).search(queries) -> SearchResult`
- `scripts/connectors/xiaohongshu.py` → `XiaohongshuConnector(export_path).search(queries) -> SearchResult`
- `scripts/scrape/normalize_xhs.py` → `normalize(notes) -> list[dict]`(CLI:`python -m scripts.scrape.normalize_xhs <in.json> -o <out.json>`),把 MediaCrawler 原生输出归一化为 `XiaohongshuConnector` 的输入。
- `scripts/ocr/extract.py` → `extract_text_from_image(path, engine=None, min_confidence=0.6) -> OcrResult{text, confidence, needs_vision}`
- `scripts/corpus/store.py` → `save_raw_posts / load_raw_posts / save_questions / load_questions`
- `scripts/corpus/recency.py` → `filter_recent(posts, window_days=730, today=None) -> list[RawPost]`
- `scripts/corpus/dedupe_rank.py` → `dedupe_and_rank(questions) -> list[Question]`
- 数据模型在 `scripts/models.py`;结构说明见 `assets/schema.md`。

## 工作流

0. **准备(仅当启用小红书源)。** 让用户先按 `docs/setup_mediacrawler.md` 跑一遍 MediaCrawler 采集 + 适配器归一化,产出 `corpus_cache/xhs_export.json`(适配器在 `scripts/scrape/normalize_xhs.py`,把 MediaCrawler 的原生输出转成 `XiaohongshuConnector` 能吃的格式)。文本/牛客/GitHub 源不需要这一步。

1. **简历理解。** 调用 `extract_resume`。若 `needs_vision` 为真,就用你自己的视觉能力直接读这张图片/PDF。产出结构化摘要:技能、项目(每个项目用到的技术)、关键术语。

2. **种子查询生成。** 用你**自己的领域知识**,从「岗位方向 + 简历」推导出种子查询。这是领域无关的:无论什么领域(市场、量化、后端、设计……)你本来就知道相关的岗位别名和底层技能/话题,当场生成即可。**不要依赖任何预设词表。** 种子来自两处:(a) 岗位方向隐含的相关岗位别名;(b) 从简历里抽出的具体技能/项目/关键词。优先用底层技能/话题词,而不是岗位名——它们更稳定、召回更好。

3. **迭代检索。** 源的优先级:**牛客 + 小红书(主力,带时间戳)> GitHub(补充,常过时)**。

   **3a. URL 发现(每轮先做)。** 用你的搜索能力(WebSearch 或等价工具)对当前的种子查询跑一遍,收集候选 URL。按域名分桶:
   - `nowcoder.com/discuss/<post_id>` → 进 `NowCoderConnector(post_urls=...)`
   - `xiaohongshu.com/explore/<note_id>` → **不能直抓**,记下笔记 ID,告诉用户按 `docs/setup_mediacrawler.md` 跑 MediaCrawler 把这批笔记抓回来再走 `XiaohongshuConnector`
   - `github.com/<owner>/<repo>/blob/<branch>/<path>` 或 `raw.githubusercontent.com/...` → 转 raw URL → 进 `GithubConnector(repo_raw_urls=...)`
   - **其他公开正文页**(知乎 article、CSDN 文章、个人博客、woshipm/uisdc 等):用 WebFetch 拉回正文,自己手工构造 `RawPost(source="webfetch:<domain>", post_type="text", raw_text=<正文>, posted_at=<页面可见日期或 None>)`,和 connector 结果一起 `save_raw_posts`

   显式排除:聚合/listing 页(只接 article 页);403/需登录的页面(不浪费 fetch 配额,记下来当作知识缺口告诉用户)。

   **3b. 调 connectors + 收割。** 把分好桶的 URL 喂给对应 connector,结果用 `save_raw_posts` 落盘。读取结果,**收割真实出现的岗位名 / 标签 / 高频术语**,用收割到的词跑下一轮 3a,直到不再冒出新词。若某 connector 返回 `status="degraded"`(例如牛客需要 cookie、小红书需要先跑 MediaCrawler、或消息含 `selector` 表示 HTML 漂移),把它需要的东西告诉用户;主力源降级会显著影响时效性,必须明确提示用户,不要默默用 GitHub 凑数。

   **GitHub 调用必带 `relevance_hints`(不要传 `None` 或 `[]`)。** GitHub 仓库里夹带大量算法/八股,不过滤会严重污染语料。`GithubConnector(repo_raw_urls=..., relevance_hints=<当前一轮的术语/岗位别名>)`。**冷启动**(第一轮还没有收割结果)时,直接把步骤 2 的种子查询当 hints 传进去——任何时候都要传非空 list。命中规则:子串、大小写不敏感,只要正文里出现任一 hint 就保留。

   **Human-in-the-loop:** 在最后一轮之前,把你从真实数据里发现的方向/术语展示给用户,让他增删/纠偏。

4. **内容级相关性判定。** 通过**读帖子内容**对照用户岗位 + 简历来判断每条是否相关——**不是**靠帖子的岗位名是否匹配某张预设表。

5. **题目抽取。** 文本类 RawPost 直接读。**图片类 RawPost(小红书,`post_type="image"`)**:对每个 `asset_paths` 里的图片调用 `extract_text_from_image(path, engine)`;若返回 `needs_vision=True`(没接 OCR 引擎或置信度低),就用你自己的视觉能力直接读这张图。把读到的题目转成标准化的 `Question`,图片来源的设 `modality_origin="ocr"` 或 `"vision"`。用 `save_questions` 落盘。

5b. **时效过滤。** 在抽取出题目之前,先用 `filter_recent(raw_posts)` 把超过约两年的帖子丢掉(默认窗口 730 天;`posted_at` 为 None 的无日期帖子保留)。时效性是硬需求——过时的面经没有价值。

6. **去重 & 排序。** 跑 `dedupe_and_rank(load_questions(...))` 并保存排序结果。排序同时考虑**频次和时效**(近期题加权更高),这就是高频题集。

7. **项目锚定推理。** 对每道高频题,检查它能否挂到简历里的某个项目/技能上。能挂上就构造 `FollowUpChain`(种子题 → 个性化追问,`is_grounded=true`)。每个追问都**必须**能追溯到(简历某项目/技能)+(某条真实爬到的题);追溯不上就设 `is_grounded=false`,当普通八股题保留。**不要凭空编追问。**

8. **备考包。** 写一份 Markdown 备考包:岗位分析、gap 分析、高频八股题(附来源链接)、个性化项目追问链、参考思路。保存到 `corpus_cache/prep_package.md` 并展示给用户。

## 约束
- **所有面向用户的产出一律用中文**(备考包、题目、追问、分析)——面经源是中文。
- 当前源:牛客 + 小红书(主力,带时间戳)+ GitHub(补充)。
- 小红书走 MediaCrawler 采集导出(用户预先离线跑一次,流程见 `docs/setup_mediacrawler.md`),OCR 采用混合策略(粗 OCR + 视觉回退);MediaCrawler 仅供个人、非商业用途。
- 时效性是硬需求:只保留近两年的面经,排序向近期加权。
- 后续版本用到的第三方爬虫(如 MediaCrawler)仅供个人、非商业用途。
- **可追溯优先于流畅度**:绝不编造无法追溯到真实数据的题目或追问。
- 若 connector 返回 `degraded` 且消息含 `selector`,说明源站点 HTML 改了选择器;到对应 `scripts/connectors/<name>.py` 顶部注释看当前假设,核对真实 HTML 后更新选择器并补 fixture。
