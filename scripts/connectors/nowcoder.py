"""NowCoder discuss-page connector.

Current selector assumptions (verified 2026-06-01 against real HTML):
- Title:   <div class="content-post-title"><h1>...</h1></div>
- Content: <div class="nc-slate-editor-content"><p>...</p>...</div>
- Date:    "createTime": <epoch_ms> in an embedded JS blob (NOT visible HTML).

If parsing returns empty title AND empty content for every URL, the connector
degrades with a "selector" message — NowCoder almost certainly updated their
schema. Inspect the live HTML and update the three selectors above.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost

_CREATE_TIME = re.compile(r'"createTime"\s*:\s*(\d{10,13})')


def _parse_create_time(html: str) -> str | None:
    m = _CREATE_TIME.search(html)
    if not m:
        return None
    try:
        ts = int(m.group(1))
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except (ValueError, OSError):
        return None


def parse_nowcoder_post(html: str, url: str) -> RawPost:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("div.content-post-title h1")
    title = title_el.get_text(strip=True) if title_el else ""

    content_el = soup.select_one("div.nc-slate-editor-content")
    body = content_el.get_text("\n", strip=True) if content_el else ""

    posted_at = _parse_create_time(html)

    if title and body:
        raw_text = f"{title}\n{body}"
    else:
        raw_text = title or body
    return RawPost(
        source="nowcoder",
        url=url,
        post_type="text",
        raw_text=raw_text,
        posted_at=posted_at,
    )


def _default_fetcher(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


class NowCoderConnector(Connector):
    name = "nowcoder"

    def __init__(self, post_urls: list[str], fetcher: Callable[[str], str] | None = None):
        self.post_urls = post_urls
        self.fetcher = fetcher or _default_fetcher

    def search(self, queries: list[str]) -> SearchResult:
        posts: list[RawPost] = []
        failures: list[tuple[str, Exception]] = []
        for url in self.post_urls:
            try:
                posts.append(parse_nowcoder_post(self.fetcher(url), url))
            except Exception as exc:  # noqa: BLE001 - isolate failures per URL
                failures.append((url, exc))

        empties = [p for p in posts if not p.raw_text]
        good = [p for p in posts if p.raw_text]
        total = len(self.post_urls)

        if failures and not good:
            first_error = failures[0][1]
            return SearchResult.degraded(
                self.name,
                f"{len(failures)}/{total} fetch failed ({first_error});"
                " 牛客需要登录，请提供 cookie 或手动粘贴帖子链接/内容",
            )

        if empties and not good:
            return SearchResult.degraded(
                self.name,
                "解析后的标题和正文都为空,NowCoder HTML 选择器可能已漂移;"
                "请对照 scripts/connectors/nowcoder.py 顶部注释更新 selectors",
            )

        if failures or empties:
            details = []
            if failures:
                details.append(f"{len(failures)}/{total} fetch failed")
            if empties:
                details.append(
                    f"{len(empties)}/{total} 帖正文为空"
                    "(疑似 anti-bot 间歇响应或 selector 漂移)"
                )
            return SearchResult(
                posts=good,
                status="degraded",
                message=(
                    f"[{self.name}] {'; '.join(details)};"
                    f" 仅保留 {len(good)} 帖成功内容,建议检查登录态或稍后重试"
                ),
            )

        return SearchResult(posts=good, status="ok", message=f"{len(good)} posts")
