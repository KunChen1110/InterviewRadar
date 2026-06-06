import json
from pathlib import Path

import pytest

from scripts.connectors.base import SearchResult
from scripts.connectors.xiaohongshu import (
    parse_mediacrawler_export,
    XiaohongshuConnector,
)
from scripts.scrape.mediacrawler_driver import MediaCrawlerDriver, _Result

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
    conn = XiaohongshuConnector(
        export_path="whatever.json",
        loader=lambda p: SAMPLE_JSON,
        enable_image_ocr=False,
    )
    result = conn.search(["agent"])
    assert result.status == "ok"
    assert len(result.posts) == 2
    assert result.posts[0].posted_at == "2025-09-20"


def test_connector_degrades_when_loader_fails():
    def boom(path):
        raise FileNotFoundError("no export")

    conn = XiaohongshuConnector(export_path="missing.json", loader=boom, enable_image_ocr=False)
    result = conn.search(["agent"])
    assert result.status == "degraded"
    assert result.posts == []
    assert "mediacrawler" in result.message.lower()


def test_connector_requires_export_path_or_driver():
    with pytest.raises(ValueError):
        XiaohongshuConnector()


def _make_driver_fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "mc"
    (home / "data" / "xhs" / "json").mkdir(parents=True)
    (home / "main.py").write_text("")
    return home


def test_connector_driver_mode_scrapes_and_returns_posts(tmp_path: Path):
    home = _make_driver_fake_home(tmp_path)
    out_dir = home / "data" / "xhs" / "json"

    # Fake runner writes a MediaCrawler-native notes JSON when invoked
    native_notes = [
        {
            "note_id": "n1",
            "title": "AI Agent 面经",
            "desc": "字节一面问了 MCP",
            "time": 1758326400000,
            "image_list": ["https://x.example/img1.jpg"],
        }
    ]

    def fake_runner(cmd, cwd, timeout):
        (out_dir / "search_contents_fresh.json").write_text(
            json.dumps(native_notes), encoding="utf-8"
        )
        return _Result(returncode=0)

    driver = MediaCrawlerDriver(home=home, runner=fake_runner)
    conn = XiaohongshuConnector(driver=driver, enable_image_ocr=False)
    result = conn.search(["AI Agent"])

    assert result.status == "ok"
    assert len(result.posts) == 1
    post = result.posts[0]
    assert post.source == "xiaohongshu"
    assert "MCP" in post.raw_text
    assert post.asset_paths == ["https://x.example/img1.jpg"]


def test_connector_driver_mode_degrades_on_scrape_failure(tmp_path: Path):
    home = _make_driver_fake_home(tmp_path)

    def boom(cmd, cwd, timeout):
        return _Result(returncode=1, stderr="login expired")

    driver = MediaCrawlerDriver(home=home, runner=boom)
    conn = XiaohongshuConnector(driver=driver, enable_image_ocr=False)
    result = conn.search(["foo"])

    assert result.status == "degraded"
    assert result.posts == []
    msg = result.message.lower()
    assert "登录" in result.message or "mediacrawler" in msg


def test_connector_driver_mode_requires_queries(tmp_path: Path):
    home = _make_driver_fake_home(tmp_path)
    driver = MediaCrawlerDriver(home=home, runner=lambda *a, **k: _Result(0))
    conn = XiaohongshuConnector(driver=driver, enable_image_ocr=False)
    result = conn.search([])

    assert result.status == "degraded"
    assert "关键词" in result.message
