# 免责声明 / Disclaimer

## 中文

本项目 **InterviewRadar** 是一个面向**个人学习**的开源工具,使用前请阅读以下条款:

### 1. 用途限定
- 本项目仅供个人学习、面试准备、技术研究使用。
- **严禁用于商业用途**,包括但不限于:对外销售、付费咨询、二次开发为收费产品。
- 严禁用于任何违反目标平台服务条款的批量采集行为。

### 2. 数据来源责任
本项目从公开网络资源中拉取面经内容,包括但不限于牛客网、GitHub、技术博客等。

- 拉取的内容版权归原作者所有。
- 本项目仅提供工具能力,不存储任何爬取的原始数据;所有数据存于用户本地 `corpus_cache/` 目录。
- 使用本工具拉取数据的合规性,由**用户自行承担**。建议:
  - 控制请求频次,不要对源站点造成压力
  - 遵守每个平台的 `robots.txt` 和服务条款
  - 不要将拉取的数据二次分发

### 3. 第三方依赖说明
- 本项目通过适配器与 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 集成以支持小红书等平台采集。MediaCrawler 项目同样要求**仅供个人非商业用途**。
- 用户需自行安装并合规使用 MediaCrawler;本项目不直接 vendor 任何爬虫代码。

### 4. AI 生成内容
本项目使用 LLM 处理拉取到的素材,生成的备考包(`prep_package.md`)中:
- 题目来自真实公开面经,但**经过 LLM 加工**,可能存在改写或推理偏差
- 项目追问由 LLM 基于用户简历推理生成,**不保证一定会被实际面试官问到**

### 5. 风险自担
**本工具按"原样"提供,作者不对任何使用后果负责**,包括但不限于:
- 拉取数据时遇到的法律风险
- LLM 生成内容的事实错误
- 备考包的应试效果

如不接受以上条款,请立即停止使用本项目。

---

## English

**InterviewRadar** is an open-source tool intended for **personal study only**.

- **Personal, non-commercial use only.** No reselling, paid consulting, or repackaging into paid products.
- **You are responsible** for the compliance of any data you scrape using this tool. Respect the `robots.txt` and ToS of each source platform.
- Third-party scraping integration (MediaCrawler) is also restricted to personal non-commercial use; install and operate it under its own terms.
- Generated interview prep packages are LLM-processed and may contain inaccuracies. Do not treat them as authoritative.
- Provided **AS-IS** with no warranty. The author is not liable for any consequences of use.

By using this project you accept the terms above.
