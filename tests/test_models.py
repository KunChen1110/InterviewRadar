from scripts.models import RawPost, Question, FollowUpChain


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


def test_question_has_optional_latest_posted_at_defaulting_none():
    q = Question("Q1", ["u1"])
    assert q.latest_posted_at is None
    dated = Question("Q2", ["u2"], latest_posted_at="2025-09-01")
    assert Question.from_dict(dated.to_dict()) == dated
