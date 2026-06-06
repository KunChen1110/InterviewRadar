import json
from pathlib import Path

from scripts.scrape.normalize_xhs import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "mc_xhs_raw.json"


def _load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_skips_notes_with_no_id_and_no_url():
    out = normalize(_load())
    assert len(out) == 4
    assert "garbage" not in {n["desc"] for n in out}


def test_passes_through_normal_note():
    out = normalize(_load())
    first = out[0]
    assert first["note_id"] == "n1"
    assert first["note_url"] == "https://www.xiaohongshu.com/explore/n1"
    assert first["title"] == "字节 AI 应用开发 面经"
    assert first["desc"].startswith("一面")
    assert first["time"] == 1758326400000
    assert first["image_list"] == [
        "https://sns-img.xhs.cn/n1_a.jpg",
        "https://sns-img.xhs.cn/n1_b.jpg",
    ]


def test_splits_comma_image_list_and_strips_empties():
    out = normalize(_load())
    n2 = next(n for n in out if n["note_id"] == "n2")
    assert n2["image_list"] == [
        "https://sns-img.xhs.cn/n2_a.jpg",
        "https://sns-img.xhs.cn/n2_b.jpg",
    ]


def test_synthesizes_url_from_note_id_when_url_missing():
    out = normalize(_load())
    n3 = next(n for n in out if n["note_id"] == "n3")
    assert n3["note_url"] == "https://www.xiaohongshu.com/explore/n3"


def test_drops_unknown_keys_but_preserves_tags():
    out = normalize(_load())
    first = out[0]
    assert "liked_count" not in first
    assert "comments" not in first
    assert "tag_list" not in first
    assert "type" not in first
    assert first["tags"] == ["面经", "实习"]


def test_invalid_time_becomes_zero_and_null_image_list_becomes_empty():
    out = normalize(_load())
    n5 = next(n for n in out if n["note_id"] == "n5")
    assert n5["time"] == 0
    assert n5["image_list"] == []
    assert n5["title"] == ""
    assert n5["desc"] == ""


def test_preserves_input_order():
    out = normalize(_load())
    assert [n["note_id"] for n in out] == ["n1", "n2", "n3", "n5"]
