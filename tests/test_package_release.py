import json

from scripts.corpus.package_release import package_release


def test_release_package_rejects_non_reviewed_production_rows(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "production_documents.jsonl").write_text(json.dumps({"review_state": "research", "metadata": {"license": "MIT"}}) + "\n")
    (source / "research_review_queue.jsonl").write_text("")
    (source / "content_audit.jsonl").write_text("")

    try:
        package_release(source, tmp_path / "release")
    except ValueError as error:
        assert "reviewed" in str(error)
    else:
        raise AssertionError("non-reviewed production row was accepted")
