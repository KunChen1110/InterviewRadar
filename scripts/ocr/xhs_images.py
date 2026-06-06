from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from scripts.models import RawPost
from scripts.ocr.extract import OcrEngine, extract_text_from_image


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class OCRPage:
    path: str
    text: str
    confidence: float
    needs_vision: bool


def _safe_note_id(note_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", note_id.strip())
    return cleaned or "unknown"


def _extension_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in _IMAGE_EXTENSIONS:
        return suffix
    return ".jpg"


def _join_text(parts: list[str]) -> str:
    return "\n".join(part.strip() for part in parts if part and part.strip())


def build_locator_text(title: str, desc: str, tags: list[str] | None = None) -> str:
    tag_text = " ".join(tag.strip() for tag in (tags or []) if tag and tag.strip())
    return _join_text([title, desc, tag_text])


def rapidocr_engine() -> OcrEngine | None:
    try:
        from rapidocr import RapidOCR
    except Exception:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception:
            return None

    ocr = RapidOCR()

    def _engine(path: str) -> tuple[str, float]:
        result = ocr(path)
        if isinstance(result, tuple):
            result = result[0]
        if not result:
            return "", 0.0

        if hasattr(result, "txts"):
            texts = [str(text).strip() for text in (result.txts or []) if str(text).strip()]
            scores = [float(score) for score in (result.scores or [])]
            confidence = sum(scores) / len(scores) if scores else 0.0
            return "\n".join(texts), confidence

        texts: list[str] = []
        confidences: list[float] = []
        for item in result:
            if len(item) < 3:
                continue
            text = str(item[1]).strip()
            if not text:
                continue
            texts.append(text)
            try:
                confidences.append(float(item[2]))
            except (TypeError, ValueError):
                continue
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return "\n".join(texts), confidence

    return _engine


class XHSAssetDownloader:
    def __init__(
        self,
        asset_root: str | Path = "corpus_cache/assets/xhs",
        http_get=None,
        timeout: int = 20,
    ):
        self.asset_root = Path(asset_root)
        self.http_get = http_get or requests.get
        self.timeout = timeout

    def download(self, note_id: str, image_urls: list[str]) -> list[Path]:
        note_dir = self.asset_root / _safe_note_id(note_id)
        note_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for index, url in enumerate(image_urls, start=1):
            path = note_dir / f"{index:03d}{_extension_from_url(url)}"
            if not path.exists():
                try:
                    response = self.http_get(url, timeout=self.timeout)
                    response.raise_for_status()
                    path.write_bytes(response.content)
                except Exception:
                    continue
            paths.append(path)
        return paths


class XHSImageOCRProcessor:
    def __init__(
        self,
        ocr_root: str | Path = "corpus_cache/ocr/xhs",
        engine: OcrEngine | None = None,
        min_confidence: float = 0.6,
    ):
        self.ocr_root = Path(ocr_root)
        self.engine = engine if engine is not None else rapidocr_engine()
        self.min_confidence = min_confidence

    def process(self, note_id: str, image_paths: list[Path]) -> list[OCRPage]:
        self.ocr_root.mkdir(parents=True, exist_ok=True)
        cache_path = self.ocr_root / f"{_safe_note_id(note_id)}.json"
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                return [OCRPage(**page) for page in cached.get("pages", [])]
            except Exception:
                pass

        pages: list[OCRPage] = []
        for path in image_paths:
            result = extract_text_from_image(
                str(path), engine=self.engine, min_confidence=self.min_confidence
            )
            pages.append(
                OCRPage(
                    path=str(path),
                    text=result.text,
                    confidence=result.confidence,
                    needs_vision=result.needs_vision,
                )
            )
        cache_path.write_text(
            json.dumps({"pages": [asdict(page) for page in pages]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return pages


class PageMerger:
    def merge(self, page_texts: list[str]) -> str:
        sections = []
        for index, text in enumerate(page_texts, start=1):
            text = text.strip()
            if text:
                sections.append(f"[图片 OCR 第 {index} 页]\n{text}")
        return "\n\n".join(sections)


def _garbled_ratio(text: str) -> float:
    compact = "".join(ch for ch in text if not ch.isspace())
    if not compact:
        return 1.0
    garbled = sum(1 for ch in compact if ch == "\ufffd" or ord(ch) < 32)
    return garbled / len(compact)


def _is_low_quality(pages: list[OCRPage], merged_text: str, min_chars: int = 8) -> bool:
    if not merged_text.strip():
        return True
    if len(merged_text.strip()) < min_chars:
        return True
    if _garbled_ratio(merged_text) > 0.2:
        return True
    return any(page.needs_vision for page in pages)


def process_xhs_note_images(
    *,
    note_id: str,
    note_url: str,
    title: str,
    desc: str,
    tags: list[str] | None,
    image_urls: list[str],
    posted_at: str | None = None,
    asset_root: str | Path = "corpus_cache/assets/xhs",
    ocr_root: str | Path = "corpus_cache/ocr/xhs",
    http_get=None,
    ocr_engine: OcrEngine | None = None,
    enable_ocr: bool = True,
) -> RawPost:
    locator_text = build_locator_text(title, desc, tags)
    if not image_urls or not enable_ocr:
        return RawPost(
            source="xiaohongshu",
            url=note_url,
            post_type="image",
            raw_text=locator_text,
            posted_at=posted_at,
            asset_paths=list(image_urls),
            locator_text=locator_text,
            content_text=locator_text,
            extraction_quality="text_only",
        )

    downloader = XHSAssetDownloader(asset_root=asset_root, http_get=http_get)
    asset_paths = downloader.download(note_id, image_urls)
    if not asset_paths:
        return RawPost(
            source="xiaohongshu",
            url=note_url,
            post_type="image",
            raw_text=locator_text,
            posted_at=posted_at,
            asset_paths=[],
            locator_text=locator_text,
            content_text=locator_text,
            needs_vision_fallback=True,
            extraction_quality="text_only",
        )

    pages = XHSImageOCRProcessor(ocr_root=ocr_root, engine=ocr_engine).process(note_id, asset_paths)
    image_ocr_text = PageMerger().merge([page.text for page in pages])
    if not image_ocr_text:
        return RawPost(
            source="xiaohongshu",
            url=note_url,
            post_type="image",
            raw_text=locator_text,
            posted_at=posted_at,
            asset_paths=[str(path) for path in asset_paths],
            locator_text=locator_text,
            content_text=locator_text,
            image_ocr_text=None,
            needs_vision_fallback=True,
            extraction_quality="text_only",
        )

    needs_vision = _is_low_quality(pages, image_ocr_text)
    return RawPost(
        source="xiaohongshu",
        url=note_url,
        post_type="image",
        raw_text=image_ocr_text,
        posted_at=posted_at,
        asset_paths=[str(path) for path in asset_paths],
        locator_text=locator_text,
        content_text=image_ocr_text,
        image_ocr_text=image_ocr_text,
        needs_vision_fallback=needs_vision,
        extraction_quality="ocr_low_quality" if needs_vision else "ocr_ok",
    )
