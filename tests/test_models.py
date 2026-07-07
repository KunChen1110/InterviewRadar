from scripts.models import FollowUpChain, Question, QuestionEvidence, RawPost


def test_rawpost_roundtrips_through_dict():
    post = RawPost(
        source="github",
        url="https://example.com/p1",
        post_type="text",
        raw_text="What is MCP?",
        asset_paths=[],
        comments=["see docs"],
    )
    assert RawPost.from_dict(post.to_dict()) == post


def test_question_roundtrips_through_dict():
    q = Question(
        text="What is MCP?",
        source_refs=["https://example.com/p1"],
        freq=2,
        role_tags=["agent"],
        topic="protocols",
        modality_origin="text",
    )
    assert Question.from_dict(q.to_dict()) == q


def test_question_roundtrips_with_canonical_text():
    q = Question(
        "招聘渠道应该怎么评估？",
        ["u1"],
        canonical_text="评估招聘渠道",
    )

    assert Question.from_dict(q.to_dict()) == q


def test_question_from_legacy_dict_defaults_canonical_text():
    q = Question.from_dict({"text": "什么是 RAG？", "source_refs": ["u1"]})

    assert q.canonical_text == ""


def test_question_roundtrips_with_structured_evidence():
    q = Question(
        "招聘渠道应该怎么评估？",
        ["https://example.com/p1"],
        evidence=[
            QuestionEvidence(
                source_url="https://example.com/p1",
                excerpt="面试官问：招聘渠道应该怎么评估？",
                posted_at="2026-05-01",
                modality_origin="text",
            )
        ],
    )

    restored = Question.from_dict(q.to_dict())

    assert restored == q
    assert isinstance(restored.evidence[0], QuestionEvidence)


def test_question_from_legacy_dict_defaults_evidence():
    q = Question.from_dict({"text": "什么是 RAG？", "source_refs": ["u1"]})

    assert q.evidence == []


def test_followupchain_roundtrips_through_dict():
    chain = FollowUpChain(
        seed_question="What is MCP?",
        resume_anchor="skill-driven project",
        followups=["How does your skill engine work?"],
        is_grounded=True,
    )
    assert FollowUpChain.from_dict(chain.to_dict()) == chain


def test_rawpost_has_optional_posted_at_defaulting_none():
    post = RawPost("github", "u1", "text", "Q1")
    assert post.posted_at is None
    dated = RawPost("nowcoder", "u2", "text", "Q2", posted_at="2025-09-01")
    assert RawPost.from_dict(dated.to_dict()) == dated
    assert dated.posted_at == "2025-09-01"


def test_rawpost_new_content_fields_default_from_raw_text():
    post = RawPost("xiaohongshu", "u1", "image", "图片正文")
    assert post.locator_text == "图片正文"
    assert post.content_text == "图片正文"
    assert post.image_ocr_text is None
    assert post.needs_vision_fallback is False
    assert post.extraction_quality == "text_only"


def test_rawpost_from_dict_accepts_legacy_cache_without_new_fields():
    post = RawPost.from_dict(
        {
            "source": "xiaohongshu",
            "url": "u1",
            "post_type": "image",
            "raw_text": "旧缓存正文",
            "asset_paths": [],
            "comments": [],
        }
    )
    assert post.locator_text == "旧缓存正文"
    assert post.content_text == "旧缓存正文"
    assert post.raw_text == "旧缓存正文"


def test_question_has_optional_latest_posted_at_defaulting_none():
    q = Question("Q1", ["u1"])
    assert q.latest_posted_at is None
    dated = Question("Q2", ["u2"], latest_posted_at="2025-09-01")
    assert Question.from_dict(dated.to_dict()) == dated
