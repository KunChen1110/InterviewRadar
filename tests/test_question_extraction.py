from scripts.corpus.extraction import (
    ExtractionCandidate,
    ExtractionDecision,
    extract_candidates,
    materialize_questions,
)
from scripts.models import RawPost


def _post(text: str, post_type: str = "text", **kwargs) -> RawPost:
    return RawPost(
        source="nowcoder",
        url="https://example.com/post-1",
        post_type=post_type,
        raw_text=text,
        posted_at="2026-06-01",
        **kwargs,
    )


def test_extract_candidates_keeps_source_lines_and_removes_only_display_prefixes():
    post = _post(
        "面试官主要问：\n"
        "1. 介绍一下你做的 RAG 项目\n"
        "2. RAG 系统如何评估效果？\n"
        "最后聊了薪资和入职时间。"
    )

    candidates = extract_candidates([post])

    assert [item.excerpt for item in candidates] == [
        "1. 介绍一下你做的 RAG 项目",
        "2. RAG 系统如何评估效果？",
    ]
    assert [item.display_text for item in candidates] == [
        "介绍一下你做的 RAG 项目",
        "RAG 系统如何评估效果？",
    ]
    assert [item.source_url for item in candidates] == [post.url, post.url]
    assert [item.posted_at for item in candidates] == ["2026-06-01", "2026-06-01"]


def test_extract_candidates_skips_plain_narrative_and_is_stable():
    post = _post("今天准备了一下午资料，最后聊了薪资和入职时间。")
    question = _post("你如何评估招聘渠道？")

    assert extract_candidates([post]) == []
    first = extract_candidates([question])
    second = extract_candidates([question])
    assert [item.candidate_id for item in first] == [item.candidate_id for item in second]


def test_extract_candidates_derives_modality_from_raw_post_content():
    text = _post("你如何评估招聘渠道？")
    ocr = _post(
        "1. 介绍一下 RAG 项目",
        post_type="image",
        image_ocr_text="1. 介绍一下 RAG 项目",
        content_text="1. 介绍一下 RAG 项目",
    )
    vision = _post(
        "1. 介绍一下 Agent 项目",
        post_type="image",
        needs_vision_fallback=True,
    )

    assert [item.modality_origin for item in extract_candidates([text, ocr, vision])] == [
        "text",
        "ocr",
        "vision",
    ]


def test_materialize_uses_candidate_text_and_immutable_evidence():
    post = _post("面试官主要问：\n1. 如何评估招聘渠道？")
    candidate = extract_candidates([post])[0]
    decision = ExtractionDecision(
        candidate_id=candidate.candidate_id,
        accepted=True,
        canonical_text="评估招聘渠道",
        topic="招聘",
        role_tags=["市场实习"],
    )

    result = materialize_questions([candidate], [decision])

    assert result.issues == []
    assert result.rejected_decisions == []
    assert len(result.questions) == 1
    question = result.questions[0]
    assert question.text == "如何评估招聘渠道？"
    assert question.canonical_text == "评估招聘渠道"
    assert question.evidence[0].excerpt == "1. 如何评估招聘渠道？"
    assert question.evidence[0].source_url == post.url
    assert question.evidence[0].modality_origin == "text"


def test_materialize_rejects_invalid_or_ambiguous_decisions_without_raising():
    candidate = ExtractionCandidate(
        candidate_id="candidate_1",
        source_url="https://example.com/post-1",
        excerpt="如何评估招聘渠道？",
        display_text="如何评估招聘渠道？",
    )
    invalid = [
        ExtractionDecision("missing", True, canonical_text="未知"),
        ExtractionDecision("candidate_1", True, canonical_text=""),
        ExtractionDecision("candidate_1", True, canonical_text="评估招聘渠道"),
    ]

    result = materialize_questions([candidate], invalid)

    assert result.questions == []
    assert [issue.code for issue in result.issues] == [
        "unknown_candidate",
        "missing_canonical_text",
        "duplicate_decision",
    ]
    assert result.rejected_decisions == invalid


def test_materialize_rejects_duplicate_candidates_without_raising():
    candidate = ExtractionCandidate(
        candidate_id="candidate_1",
        source_url="https://example.com/post-1",
        excerpt="如何评估招聘渠道？",
        display_text="如何评估招聘渠道？",
    )
    decision = ExtractionDecision("candidate_1", True, canonical_text="评估招聘渠道")

    result = materialize_questions([candidate, candidate], [decision])

    assert result.questions == []
    assert [issue.code for issue in result.issues] == [
        "duplicate_candidate_id",
        "unknown_candidate",
    ]


def test_materialize_rejects_bad_role_tags():
    candidate = ExtractionCandidate(
        candidate_id="candidate_1",
        source_url="https://example.com/post-1",
        excerpt="如何评估招聘渠道？",
        display_text="如何评估招聘渠道？",
    )
    decision = ExtractionDecision(
        "candidate_1", True, canonical_text="评估招聘渠道", role_tags=["市场", ""]
    )

    result = materialize_questions([candidate], [decision])

    assert result.questions == []
    assert [issue.code for issue in result.issues] == ["invalid_role_tags"]
