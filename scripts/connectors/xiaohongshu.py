import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from scripts.connectors.base import Connector, SearchResult
from scripts.models import RawPost
from scripts.ocr.xhs_images import build_locator_text, process_xhs_note_images
from scripts.scrape.mediacrawler_driver import MediaCrawlerDriver
from scripts.scrape.normalize_xhs import normalize


def _epoch_ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None
    return dt.date().isoformat()


def _posts_from_notes(notes: list[dict]) -> list[RawPost]:
    posts: list[RawPost] = []
    for note in notes:
        title = (note.get("title") or "").strip()
        desc = (note.get("desc") or "").strip()
        tags = _coerce_tags(note.get("tags") or note.get("tag_list"))
        raw_text = build_locator_text(title, desc, tags)
        posts.append(
            RawPost(
                source="xiaohongshu",
                url=note.get("note_url", ""),
                post_type="image",
                raw_text=raw_text,
                posted_at=_epoch_ms_to_iso(note.get("time")),
                asset_paths=list(note.get("image_list") or []),
                locator_text=raw_text,
                content_text=raw_text,
                extraction_quality="text_only",
            )
        )
    return posts


def parse_mediacrawler_export(json_text: str) -> list[RawPost]:
    return _posts_from_notes(json.loads(json_text))


def _coerce_tags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        tags = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("name") or item.get("tag_name") or item.get("text")
            text = str(item).strip()
            if text:
                tags.append(text)
        return tags
    if isinstance(value, str):
        normalized = value.replace("#", ",").replace("，", ",")
        return [part.strip() for part in normalized.split(",") if part.strip()]
    return []


def _note_id_from(note: dict) -> str:
    note_id = str(note.get("note_id") or "").strip()
    if note_id:
        return note_id
    note_url = str(note.get("note_url") or "").rstrip("/")
    return note_url.rsplit("/", 1)[-1] if note_url else "unknown"


def _default_loader(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


class XiaohongshuConnector(Connector):
    name = "xiaohongshu"

    def __init__(
        self,
        export_path: str | None = None,
        driver: MediaCrawlerDriver | None = None,
        loader: Callable[[str], str] | None = None,
        login_type: str = "qrcode",
        asset_root="corpus_cache/assets/xhs",
        ocr_root="corpus_cache/ocr/xhs",
        http_get=None,
        ocr_engine=None,
        enable_image_ocr: bool = True,
    ):
        if export_path is None and driver is None:
            raise ValueError(
                "XiaohongshuConnector requires either export_path (pre-scraped JSON) "
                "or driver (MediaCrawlerDriver for on-demand scraping)"
            )
        self.export_path = export_path
        self.driver = driver
        self.loader = loader or _default_loader
        self.login_type = login_type
        self.asset_root = asset_root
        self.ocr_root = ocr_root
        self.http_get = http_get
        self.ocr_engine = ocr_engine
        self.enable_image_ocr = enable_image_ocr

    def _posts_with_images(self, notes: list[dict]) -> list[RawPost]:
        posts: list[RawPost] = []
        for note in notes:
            title = (note.get("title") or "").strip()
            desc = (note.get("desc") or "").strip()
            image_urls = list(note.get("image_list") or [])
            posts.append(
                process_xhs_note_images(
                    note_id=_note_id_from(note),
                    note_url=note.get("note_url", ""),
                    title=title,
                    desc=desc,
                    tags=_coerce_tags(note.get("tags") or note.get("tag_list")),
                    image_urls=image_urls,
                    posted_at=_epoch_ms_to_iso(note.get("time")),
                    asset_root=self.asset_root,
                    ocr_root=self.ocr_root,
                    http_get=self.http_get,
                    ocr_engine=self.ocr_engine,
                    enable_ocr=self.enable_image_ocr,
                )
            )
        return posts

    def search(self, queries: list[str]) -> SearchResult:
        try:
            if self.driver is not None:
                if not queries:
                    return SearchResult.degraded(
                        self.name,
                        "需要关键词才能用 MediaCrawler 驱动模式;请传入 queries",
                    )
                notes_path = self.driver.scrape_xhs(queries, login_type=self.login_type)
                native = json.loads(Path(notes_path).read_text(encoding="utf-8"))
                posts = self._posts_with_images(normalize(native))
            else:
                notes = json.loads(self.loader(self.export_path))
                posts = self._posts_with_images(notes)
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            return SearchResult.degraded(
                self.name,
                f"无法获取小红书数据 ({exc});若用 driver 模式请检查 MediaCrawler 登录态是否过期"
                "(qrcode 模式重扫码,cookie 模式重新拿 web_session 填进 config.COOKIES),"
                "或确认 MediaCrawler 是否安装在 $MEDIACRAWLER_HOME / ~/.mediacrawler/",
            )
        return SearchResult(posts=posts, status="ok", message=f"{len(posts)} posts")
