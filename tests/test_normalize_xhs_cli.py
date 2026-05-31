import json
from pathlib import Path

from scripts.scrape.normalize_xhs import _main
from scripts.connectors.xiaohongshu import parse_mediacrawler_export

FIXTURE = Path(__file__).parent / "fixtures" / "mc_xhs_raw.json"


def test_cli_writes_normalized_file(tmp_path, capsys):
    out_path = tmp_path / "xhs_export.json"
    rc = _main([str(FIXTURE), "-o", str(out_path)])
    assert rc == 0
    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert isinstance(written, list)
    assert len(written) == 4
    assert written[0]["note_url"] == "https://www.xiaohongshu.com/explore/n1"
    captured = capsys.readouterr()
    assert "wrote 4 notes" in captured.out


def test_end_to_end_with_plan3_connector(tmp_path):
    out_path = tmp_path / "xhs_export.json"
    _main([str(FIXTURE), "-o", str(out_path)])
    posts = parse_mediacrawler_export(out_path.read_text(encoding="utf-8"))
    assert len(posts) == 4
    n1 = posts[0]
    assert n1.source == "xiaohongshu"
    assert n1.post_type == "image"
    assert n1.posted_at == "2025-09-20"
    assert n1.asset_paths == [
        "https://sns-img.xhs.cn/n1_a.jpg",
        "https://sns-img.xhs.cn/n1_b.jpg",
    ]
    n2 = next(p for p in posts if "RAG" in p.raw_text)
    assert n2.posted_at is None
