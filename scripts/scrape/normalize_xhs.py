"""Normalize MediaCrawler's native 小红书 notes export into the schema that
`scripts/connectors/xiaohongshu.py:parse_mediacrawler_export` consumes.

Field assumptions about MediaCrawler's output (based on the public repo,
NanmiCoder/MediaCrawler, 小红书 module). If MediaCrawler changes their schema,
only this file needs to be touched.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_NOTE_URL_TEMPLATE = "https://www.xiaohongshu.com/explore/{note_id}"


def _coerce_image_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _coerce_tags(note: dict) -> list[str]:
    value = note.get("tags")
    if value is None:
        value = note.get("tag_list")
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


def _coerce_time(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def normalize(notes: list[dict]) -> list[dict]:
    out: list[dict] = []
    for note in notes:
        note_id = note.get("note_id")
        note_url = note.get("note_url")
        if not note_id and not note_url:
            continue
        if not note_url:
            note_url = _NOTE_URL_TEMPLATE.format(note_id=note_id)
        out.append(
            {
                "note_id": note_id or "",
                "note_url": note_url,
                "title": note.get("title") or "",
                "desc": note.get("desc") or "",
                "time": _coerce_time(note.get("time")),
                "image_list": _coerce_image_list(note.get("image_list")),
                "tags": _coerce_tags(note),
            }
        )
    return out


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize MediaCrawler 小红书 notes JSON into XiaohongshuConnector input."
    )
    parser.add_argument("input", help="Path to MediaCrawler notes JSON.")
    parser.add_argument("-o", "--output", required=True, help="Path to write normalized JSON.")
    args = parser.parse_args(argv)

    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    normalized = normalize(raw)
    Path(args.output).write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(normalized)} notes to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
