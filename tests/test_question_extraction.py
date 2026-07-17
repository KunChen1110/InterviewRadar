from scripts.corpus.extraction import extract_candidates
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
