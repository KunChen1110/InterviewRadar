from scripts.corpus.build_role_taxonomy import build_taxonomy


def test_taxonomy_has_required_major_role_families() -> None:
    taxonomy = build_taxonomy()

    assert {"研发与算法", "产品与设计", "增长与商业化", "职能与专业服务", "行业与业务"} <= set(taxonomy["families"])
    assert taxonomy["schema_version"] == "role-taxonomy/1.0"
