# 小红书面经采集 — MediaCrawler 设置指引

启用 `interview-radar` skill 的小红书源是**可选**步骤。skill 本身不抓数据;
真正的采集由开源工具 [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 完成,
本文档教你怎么把它和本 skill 串起来。

> 仅供个人、非商业用途。请遵守目标平台的服务条款。

## 推荐:driver 模式(一次设置,之后全自动)

只需要做**两件事**(总共约 5 分钟):

### 1. 装 MediaCrawler 到默认路径

```bash
# 默认路径是 ~/.mediacrawler/。也可以装到任意位置,然后 export MEDIACRAWLER_HOME=<path>
git clone https://github.com/NanmiCoder/MediaCrawler.git ~/.mediacrawler
cd ~/.mediacrawler

# 用 Python 3.11(它 requirements.txt 锁的版本)
python3.11 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/playwright install chromium
```

### 1.5. 关掉默认的 CDP 模式(重要)

MediaCrawler 默认 `ENABLE_CDP_MODE = True`,会尝试连接你**已经开着**的 Chrome(端口 9222),不开就报 "CDP port 9222 is not accessible" 死循环。改成 False 让它用自带的 Playwright Chromium:

```bash
sed -i '' 's/^ENABLE_CDP_MODE = True/ENABLE_CDP_MODE = False/' config/base_config.py
```

(macOS sed 语法;Linux 用 `sed -i 's/.../.../' config/base_config.py`。)

### 2. 扫码登录一次

```bash
cd ~/.mediacrawler
python main.py --platform xhs --lt qrcode --type search --keywords "测试"
```

屏幕上会弹出二维码,用手机小红书 App 扫码登录。**之后登录态会被 MediaCrawler 缓存**,在过期之前都不需要再扫。

之后就别再手动跑 MediaCrawler 了 ——

**skill 会在需要小红书数据时自动调用它**(通过 `XiaohongshuConnector(driver=MediaCrawlerDriver())`),把关键词喂进去 → 拿 JSON → 进管道,全自动。

### 登录态过期了怎么办?

skill 会返回 `status="degraded"` 并提示"登录过期"。重新执行第 2 步扫码即可,代码不用动。

---

## 备用:手动模式(不想让 skill 自动跑 MediaCrawler)

如果你想自己控制爬虫节奏,或者觉得让 skill shell out 跑外部工具不放心:

```bash
# 自己跑 MediaCrawler
cd ~/.mediacrawler
python main.py --platform xhs --lt qrcode --type search --keywords "AI 应用开发 面经"

# 用本 skill 的适配器归一化
cd ~/.claude/skills/interview-radar
.venv/bin/python -m scripts.scrape.normalize_xhs \
    ~/.mediacrawler/data/xhs/json/search_contents_*.json \
    -o corpus_cache/xhs_export.json
```

然后让 skill 用 `XiaohongshuConnector(export_path="corpus_cache/xhs_export.json")`,不传 driver。

---

## 排错

| 现象 | 可能原因 |
|---|---|
| `MediaCrawlerNotInstalledError` | 没装在 `~/.mediacrawler/`,且没设 `$MEDIACRAWLER_HOME` |
| `MediaCrawlerScrapeError: login expired` | 登录态过期,**重扫码**(第 2 步) |
| `MediaCrawlerScrapeError: ... schema may have changed` | MediaCrawler 升级了 CLI 或输出路径,改 `scripts/scrape/mediacrawler_driver.py` 里的假设 |
| 适配器(`normalize_xhs.py`)报错 | MediaCrawler 升级了 JSON schema,改 `scripts/scrape/normalize_xhs.py` 里的字段假设 |
