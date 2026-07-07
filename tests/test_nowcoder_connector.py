from pathlib import Path

from scripts.connectors.base import SearchResult
from scripts.connectors.nowcoder import parse_nowcoder_post, NowCoderConnector

FIXTURE = Path(__file__).parent / "fixtures" / "nowcoder_sample.html"
SAMPLE_HTML = FIXTURE.read_text(encoding="utf-8")


def test_parse_extracts_text_and_date():
    post = parse_nowcoder_post(SAMPLE_HTML, "https://nowcoder.com/p/1")
    assert post.source == "nowcoder"
    assert post.url == "https://nowcoder.com/p/1"
    assert post.posted_at == "2025-09-20"
    assert "MCP 和 Skill 的区别" in post.raw_text
    assert "agent 项目架构" in post.raw_text
    assert "字节 AI 应用开发 一面面经" in post.raw_text


def test_connector_search_uses_injected_fetcher():
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/1"],
        fetcher=lambda url: SAMPLE_HTML,
    )
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert len(result.posts) == 1
    assert result.posts[0].posted_at == "2025-09-20"


def test_connector_degrades_on_fetch_error():
    def boom(url):
        raise RuntimeError("login wall")

    conn = NowCoderConnector(post_urls=["https://nowcoder.com/p/1"], fetcher=boom)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "cookie" in result.message.lower()


def test_connector_keeps_successful_posts_when_later_fetch_fails():
    def fetch(url):
        if url.endswith("/2"):
            raise RuntimeError("login wall")
        return SAMPLE_HTML

    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/1", "https://nowcoder.com/p/2"],
        fetcher=fetch,
    )

    result = conn.search(["agent"])

    assert result.status == "degraded"
    assert len(result.posts) == 1
    assert result.posts[0].url.endswith("/1")
    assert "1/2" in result.message


def test_parse_missing_date_yields_none():
    html = (
        "<div class='content-post-title'><h1>T</h1></div>"
        "<div class='nc-slate-editor-content'><p>body text here</p></div>"
    )
    post = parse_nowcoder_post(html, "https://nowcoder.com/p/2")
    assert post.posted_at is None
    assert "body text here" in post.raw_text
    assert post.raw_text.startswith("T")


def test_connector_degrades_when_parsed_content_is_empty():
    drift_html = "<html><body><div class='something-else'>nothing useful</div></body></html>"
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/1"], fetcher=lambda url: drift_html
    )
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "selector" in result.message.lower()


def test_connector_degrades_when_majority_bodies_empty_keeps_good_posts():
    # Real-world case: NowCoder serves anti-bot pages where createTime stays in the
    # JS blob but the editor content div is missing. Most posts come back empty;
    # we should flag this loud (status=degraded) but keep whatever did parse.
    good_html = (
        "<div class='content-post-title'><h1>真实标题</h1></div>"
        "<div class='nc-slate-editor-content'><p>真实正文</p></div>"
        "<script>{\"createTime\":1758326400000}</script>"
    )
    empty_html = "<script>{\"createTime\":1758326400000}</script>"  # createTime survives, body gone

    def fetch(url):
        return good_html if url.endswith("/1") else empty_html

    conn = NowCoderConnector(
        post_urls=[f"https://nowcoder.com/p/{i}" for i in range(1, 5)],  # 1 good + 3 empty
        fetcher=fetch,
    )
    result = conn.search([])
    assert result.status == "degraded"
    assert "anti-bot" in result.message.lower() or "重试" in result.message
    assert len(result.posts) == 1
    assert "真实正文" in result.posts[0].raw_text


def test_connector_degrades_and_drops_empty_posts_even_when_minority():
    # Empty posts are not useful downstream, even when most URLs parsed correctly.
    good_html = (
        "<div class='content-post-title'><h1>T</h1></div>"
        "<div class='nc-slate-editor-content'><p>body</p></div>"
        "<script>{\"createTime\":1758326400000}</script>"
    )
    empty_html = "<script>{\"createTime\":1758326400000}</script>"

    def fetch(url):
        return empty_html if url.endswith("/4") else good_html

    conn = NowCoderConnector(
        post_urls=[f"https://nowcoder.com/p/{i}" for i in range(1, 5)],
        fetcher=fetch,
    )
    result = conn.search([])
    assert result.status == "degraded"
    assert len(result.posts) == 3
    assert all(post.raw_text for post in result.posts)
    assert "1/4" in result.message


def test_parse_handles_only_title_or_only_content():
    title_only_html = "<div class='content-post-title'><h1>仅标题</h1></div>"
    conn = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/3"], fetcher=lambda url: title_only_html
    )
    result = conn.search([])
    assert result.status == "ok"
    assert result.posts[0].raw_text == "仅标题"

    content_only_html = "<div class='nc-slate-editor-content'><p>正文段落</p></div>"
    conn2 = NowCoderConnector(
        post_urls=["https://nowcoder.com/p/4"], fetcher=lambda url: content_only_html
    )
    result2 = conn2.search([])
    assert result2.status == "ok"
    assert "正文段落" in result2.posts[0].raw_text
