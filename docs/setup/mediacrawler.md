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
