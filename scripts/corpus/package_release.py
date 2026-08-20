"""Create a sealed, auditable release from an existing RAG import package."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from scripts.corpus.build_role_taxonomy import build_taxonomy


FILES = ("production_documents.jsonl", "research_review_queue.jsonl", "content_audit.jsonl")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def package_release(source: Path, destination: Path) -> dict:
    if destination.exists():
        raise FileExistsError(destination)
    production = read_jsonl(source / "production_documents.jsonl")
    if not all(row.get("review_state") == "reviewed" for row in production):
        raise ValueError("production rows must all be reviewed")
    if not all(row.get("metadata", {}).get("license") in {"MIT", "Apache-2.0"} for row in production):
        raise ValueError("production rows must have an approved license")
    destination.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(source / name, destination / name)
    taxonomy = build_taxonomy()
    (destination / "role_taxonomy.json").write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n")
    (destination / "authorized_source_review_queue.jsonl").write_text("")
    files = {name: {"rows": len(read_jsonl(destination / name)), "sha256": hashlib.sha256((destination / name).read_bytes()).hexdigest()} for name in FILES}
    audit = {"production_count": len(production), "licenses": dict(Counter(row["metadata"]["license"] for row in production)), "source_types": dict(Counter(row["source_type"] for row in production)), "role_tags": dict(Counter(tag for row in production for tag in row["role_tags"])), "admission_policy": "reviewed, provenance-bearing MIT/Apache-2.0 records only"}
    (destination / "release_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    manifest = {"schema_version": "interviewradar-release/1.0", "source_package": str(source), "files": files, "production_count": len(production)}
    (destination / "release_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (destination / "README.md").write_text("# InterviewRadar RAG 发布包\n\n仅导入已审核、来源可追溯且许可证为 MIT 或 Apache-2.0 的生产题目。授权平台材料必须先进入人工审核队列，不能直接写入 production_documents.jsonl。\n")
    return manifest
