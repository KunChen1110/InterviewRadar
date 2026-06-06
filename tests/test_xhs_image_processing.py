import json
from pathlib import Path

from scripts.connectors.xiaohongshu import XiaohongshuConnector
from scripts.ocr.xhs_images import (
    PageMerger,
    XHSAssetDownloader,
    XHSImageOCRProcessor,
    process_xhs_note_images,
)


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


def test_downloader_preserves_image_order_and_names_pages(tmp_path):
    seen_urls = []

    def fake_get(url, timeout):
        seen_urls.append(url)
        return FakeResponse(f"bytes:{url}".encode("utf-8"))

    downloader = XHSAssetDownloader(asset_root=tmp_path, http_get=fake_get)
    paths = downloader.download(
        "n1",
        ["https://img.example/a.png", "https://img.example/b.webp", "https://img.example/c"],
    )

    assert seen_urls == [
        "https://img.example/a.png",
        "https://img.example/b.webp",
        "https://img.example/c",
    ]
    assert [p.name for p in paths] == ["001.png", "002.webp", "003.jpg"]
    assert [p.parent.name for p in paths] == ["n1", "n1", "n1"]


def test_page_merger_keeps_page_boundaries_in_order():
    text = PageMerger().merge(["第一页题目", "第二页追问"])
    assert text == "[图片 OCR 第 1 页]\n第一页题目\n\n[图片 OCR 第 2 页]\n第二页追问"


def test_process_uses_image_ocr_as_primary_content_not_caption(tmp_path):
    image_paths = []

    def fake_get(url, timeout):
        return FakeResponse(b"img")

    def engine(path):
        image_paths.append(Path(path).name)
        return (f"{Path(path).stem} OCR 问题", 0.92)

    post = process_xhs_note_images(
        note_id="n1",
        note_url="https://www.xiaohongshu.com/explore/n1",
        title="阿里系面经",
        desc="希望帮到大家 #面经",
        tags=["阿里", "大模型"],
        image_urls=["https://img.example/one.jpg", "https://img.example/two.jpg"],
        asset_root=tmp_path / "assets",
        ocr_root=tmp_path / "ocr",
        http_get=fake_get,
        ocr_engine=engine,
    )

    assert image_paths == ["001.jpg", "002.jpg"]
    assert post.locator_text == "阿里系面经\n希望帮到大家 #面经\n阿里 大模型"
    assert "[图片 OCR 第 1 页]\n001 OCR 问题" in post.image_ocr_text
    assert post.content_text == post.image_ocr_text
    assert post.raw_text == post.image_ocr_text
    assert "希望帮到大家" not in post.raw_text
    assert post.asset_paths == [
        str(tmp_path / "assets" / "n1" / "001.jpg"),
        str(tmp_path / "assets" / "n1" / "002.jpg"),
    ]
    assert post.extraction_quality == "ocr_ok"
    assert post.needs_vision_fallback is False


def test_process_marks_low_quality_ocr_without_mixing_caption(tmp_path):
    post = process_xhs_note_images(
        note_id="n1",
        note_url="https://www.xiaohongshu.com/explore/n1",
        title="阿里系面经",
        desc="caption 干扰文本",
        tags=[],
        image_urls=["https://img.example/one.jpg"],
        asset_root=tmp_path / "assets",
        ocr_root=tmp_path / "ocr",
        http_get=lambda url, timeout: FakeResponse(b"img"),
        ocr_engine=lambda path: ("短", 0.2),
    )

    assert post.raw_text == "[图片 OCR 第 1 页]\n短"
    assert "caption 干扰文本" not in post.raw_text
    assert post.needs_vision_fallback is True
    assert post.extraction_quality == "ocr_low_quality"


def test_process_without_images_falls_back_to_locator_text(tmp_path):
    post = process_xhs_note_images(
        note_id="n1",
        note_url="https://www.xiaohongshu.com/explore/n1",
        title="标题",
        desc="正文",
        tags=[],
        image_urls=[],
        asset_root=tmp_path / "assets",
        ocr_root=tmp_path / "ocr",
    )

    assert post.raw_text == "标题\n正文"
    assert post.content_text == "标题\n正文"
    assert post.locator_text == "标题\n正文"
    assert post.image_ocr_text is None
    assert post.extraction_quality == "text_only"


def test_connector_integrates_downloader_ocr_and_primary_content(tmp_path):
    sample = [
        {
            "note_id": "n1",
            "note_url": "https://www.xiaohongshu.com/explore/n1",
            "title": "阿里系面经",
            "desc": "caption 不进主正文",
            "time": 1758326400000,
            "image_list": ["https://img.example/one.jpg"],
            "tag_list": ["阿里", "面经"],
        }
    ]
    conn = XiaohongshuConnector(
        export_path="whatever.json",
        loader=lambda path: json.dumps(sample, ensure_ascii=False),
        asset_root=tmp_path / "assets",
        ocr_root=tmp_path / "ocr",
        http_get=lambda url, timeout: FakeResponse(b"img"),
        ocr_engine=lambda path: ("自我介绍\nagent 项目拷打", 0.95),
    )

    result = conn.search(["阿里"])

    assert result.status == "ok"
    post = result.posts[0]
    assert post.raw_text == "[图片 OCR 第 1 页]\n自我介绍\nagent 项目拷打"
    assert post.content_text == post.raw_text
    assert "caption 不进主正文" not in post.raw_text
    assert "caption 不进主正文" in post.locator_text
    assert post.asset_paths == [str(tmp_path / "assets" / "n1" / "001.jpg")]
    assert post.extraction_quality == "ocr_ok"
