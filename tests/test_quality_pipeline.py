from datetime import date

from scripts.corpus.quality import prepare_questions
from scripts.models import Question, QuestionEvidence, RawPost


TODAY = date(2026, 7, 7)


def _post(url: str, text: str, posted_at: str | None = "2026-06-01") -> RawPost:
    return RawPost(
        source="nowcoder",
        url=url,
        post_type="text",
        raw_text=text,
        posted_at=posted_at,
    )


def _question(text: str, url: str, excerpt: str, canonical_text: str = "") -> Question:
    return Question(
        text=text,
        canonical_text=canonical_text,
        evidence=[QuestionEvidence(source_url=url, excerpt=excerpt)],
    )


def test_valid_evidence_is_synchronized_from_raw_post():
    post = _post("https://example.com/p1", "一面问题：\n如何评估招聘渠道？")
    question = _question(
        "招聘渠道应该怎么评估？",
        post.url,
        "一面问题： 如何评估招聘渠道？",
        canonical_text="评估招聘渠道",
    )

    result = prepare_questions([post], [question], today=TODAY)

    assert result.rejected_questions == []
    assert result.recency_counts == {"recent": 1}
    assert len(result.ranked_questions) == 1
    grounded = result.ranked_questions[0]
    assert grounded.source_refs == [post.url]
    assert grounded.latest_posted_at == "2026-06-01"
    assert grounded.evidence[0].posted_at == "2026-06-01"
    assert grounded.evidence[0].excerpt == "一面问题： 如何评估招聘渠道？"


def test_hallucinated_excerpt_rejects_question():
    post = _post("https://example.com/p1", "只问了自我介绍")
    question = _question("如何评估招聘渠道？", post.url, "如何评估招聘渠道？")

    result = prepare_questions([post], [question], today=TODAY)

    assert result.ranked_questions == []
    assert result.rejected_questions == [question]
    assert [issue.code for issue in result.issues] == ["excerpt_not_found"]


def test_stale_source_cannot_ground_question():
    post = _post("https://example.com/old", "什么是 RAG？", posted_at="2020-01-01")
    question = _question("什么是 RAG？", post.url, "什么是 RAG？")

    result = prepare_questions([post], [question], today=TODAY)

    assert result.ranked_questions == []
    assert result.recency_counts == {"stale": 1}
    assert [issue.code for issue in result.issues] == ["source_outside_recency"]


def test_unknown_source_url_is_rejected():
    question = _question("什么是 MCP？", "https://example.com/missing", "什么是 MCP？")

    result = prepare_questions([], [question], today=TODAY)

    assert result.ranked_questions == []
    assert [issue.code for issue in result.issues] == ["source_missing"]


def test_empty_source_url_cannot_ground_question():
    post = _post("", "什么是 MCP？")
    question = _question("什么是 MCP？", "", "什么是 MCP？")

    result = prepare_questions([post], [question], today=TODAY)

    assert result.ranked_questions == []
    assert [issue.code for issue in result.issues] == ["source_missing"]


def test_missing_evidence_requires_explicit_legacy_mode():
    post = _post("https://example.com/p1", "什么是 MCP？")
    legacy = Question("什么是 MCP？", [post.url])

    strict = prepare_questions([post], [legacy], today=TODAY)
    compatible = prepare_questions(
        [post],
        [legacy],
        today=TODAY,
        require_evidence=False,
    )

    assert strict.ranked_questions == []
    assert [issue.code for issue in strict.issues] == ["missing_evidence"]
    assert len(compatible.ranked_questions) == 1
    assert compatible.ranked_questions[0].source_refs == [post.url]
    assert compatible.ranked_questions[0].latest_posted_at == "2026-06-01"
    assert [issue.code for issue in compatible.issues] == ["legacy_unverified"]


def test_legacy_mode_distinguishes_missing_source_from_stale_source():
    stale = _post("https://example.com/old", "旧题", posted_at="2020-01-01")
    missing = Question("未知来源题", ["https://example.com/missing"])
    old = Question("旧题", [stale.url])

    result = prepare_questions(
        [stale],
        [missing, old],
        today=TODAY,
        require_evidence=False,
    )

    assert result.ranked_questions == []
    assert [issue.code for issue in result.issues] == [
        "source_missing",
        "source_outside_recency",
    ]


def test_valid_canonical_duplicates_merge_sources_and_evidence():
    first = _post("https://example.com/p1", "如何评估招聘渠道？")
    second = _post("https://example.com/p2", "招聘渠道应该怎么评估？")
    questions = [
        _question(
            "如何评估招聘渠道？",
            first.url,
            "如何评估招聘渠道？",
            canonical_text="评估招聘渠道",
        ),
        _question(
            "招聘渠道应该怎么评估？",
            second.url,
            "招聘渠道应该怎么评估？",
            canonical_text="评估招聘渠道",
        ),
    ]

    result = prepare_questions([first, second], questions, today=TODAY)

    assert len(result.ranked_questions) == 1
    merged = result.ranked_questions[0]
    assert merged.freq == 2
    assert merged.source_refs == [first.url, second.url]
    assert len(merged.evidence) == 2
