from datetime import date

from scripts.models import Question, QuestionEvidence
from scripts.corpus.dedupe_rank import dedupe_and_rank, normalize, question_rank_score


def test_normalize_strips_case_punctuation_whitespace():
    assert normalize("  What is  MCP??  ") == normalize("what is mcp")


def test_dedupe_merges_and_sums_freq():
    qs = [
        Question("What is MCP?", ["u1"], role_tags=["agent"]),
        Question("what is  mcp", ["u2"], role_tags=["llm"]),
        Question("What is RAG?", ["u3"]),
    ]
    out = dedupe_and_rank(qs)
    assert len(out) == 2
    top = out[0]
    assert top.freq == 2
    assert top.source_refs == ["u1", "u2"]
    assert top.role_tags == ["agent", "llm"]


def test_rank_sorts_by_freq_desc():
    qs = [
        Question("rare", ["a"]),
        Question("common", ["b"]),
        Question("common", ["c"]),
    ]
    out = dedupe_and_rank(qs)
    assert out[0].text == "common"
    assert out[0].freq == 2
    assert out[1].text == "rare"


def test_merge_keeps_most_recent_date():
    qs = [
        Question("What is MCP?", ["u1"], latest_posted_at="2024-01-01"),
        Question("what is  mcp", ["u2"], latest_posted_at="2025-06-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert len(out) == 1
    assert out[0].latest_posted_at == "2025-06-01"
    assert out[0].freq == 2


def test_recency_weight_can_outrank_lower_freq_when_close():
    # old item freq=2 → score 2*0.3=0.6 ; fresh item freq=1 → score 1*1.0=1.0
    qs = [
        Question("old hot", ["a"], freq=2, latest_posted_at="2023-01-01"),
        Question("fresh", ["b"], freq=1, latest_posted_at="2026-04-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert out[0].text == "fresh"


def test_undated_ranks_below_known_stale():
    # New policy: undated (0.2) ranks BELOW known-stale (0.3).
    # freq all 1: fresh(1.0) > stale(0.3) > undated(0.2)
    qs = [
        Question("stale", ["a"], latest_posted_at="2022-01-01"),
        Question("undated", ["b"], latest_posted_at=None),
        Question("fresh", ["c"], latest_posted_at="2026-05-01"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert [q.text for q in out] == ["fresh", "stale", "undated"]


def test_malformed_date_treated_as_undated():
    # Malformed posted_at should weight the same as None (0.2), i.e. rank below known-stale.
    qs = [
        Question("stale", ["a"], latest_posted_at="2022-01-01"),
        Question("garbled", ["b"], latest_posted_at="not-a-date"),
    ]
    out = dedupe_and_rank(qs, today=date(2026, 5, 28))
    assert [q.text for q in out] == ["stale", "garbled"]


def test_canonical_text_merges_paraphrased_questions():
    qs = [
        Question(
            "如何评估招聘渠道？",
            ["u1"],
            canonical_text="评估招聘渠道",
        ),
        Question(
            "招聘渠道应该怎么评估？",
            ["u2"],
            canonical_text="评估招聘渠道",
        ),
    ]

    out = dedupe_and_rank(qs, today=date(2026, 5, 28))

    assert len(out) == 1
    assert out[0].freq == 2
    assert out[0].source_refs == ["u1", "u2"]
    assert out[0].canonical_text == "评估招聘渠道"


def test_canonical_merge_preserves_distinct_evidence():
    qs = [
        Question(
            "如何评估招聘渠道？",
            ["u1"],
            canonical_text="评估招聘渠道",
            evidence=[QuestionEvidence("u1", "如何评估招聘渠道？")],
        ),
        Question(
            "招聘渠道应该怎么评估？",
            ["u2"],
            canonical_text="评估招聘渠道",
            evidence=[QuestionEvidence("u2", "招聘渠道应该怎么评估？")],
        ),
    ]

    out = dedupe_and_rank(qs, today=date(2026, 5, 28))

    assert len(out[0].evidence) == 2
    assert [item.source_url for item in out[0].evidence] == ["u1", "u2"]


def test_independent_sources_outrank_repeats_from_one_source():
    qs = [
        *[
            Question("单一来源重复题", ["same-url"], latest_posted_at="2026-05-01")
            for _ in range(5)
        ],
        Question("跨来源题", ["u1"], latest_posted_at="2026-05-01"),
        Question("跨来源题", ["u2"], latest_posted_at="2026-05-01"),
    ]

    out = dedupe_and_rank(qs, today=date(2026, 5, 28))

    assert out[0].text == "跨来源题"
    assert out[0].freq == 2
    assert out[1].freq == 5


def test_rank_score_exposes_source_breadth_occurrences_and_recency():
    q = Question(
        "What is MCP?",
        ["u1", "u2", "u2"],
        freq=3,
        latest_posted_at="2026-05-01",
    )

    score = question_rank_score(q, today=date(2026, 5, 28))

    assert score.source_count == 2
    assert score.occurrence_count == 3
    assert score.recency_weight == 1.0
    assert score.total == 2.0


def test_rank_score_treats_tracking_variants_as_one_source():
    q = Question(
        "如何评估招聘渠道？",
        [
            "https://www.xiaohongshu.com/explore/n1?xsec_token=first#comments",
            "https://www.xiaohongshu.com/explore/n1?xsec_token=second",
        ],
        freq=2,
        latest_posted_at="2026-05-01",
    )

    score = question_rank_score(q, today=date(2026, 5, 28))

    assert score.source_count == 1
    assert score.total == 1.0


def test_rank_score_preserves_query_parameters_that_identify_content():
    q = Question(
        "如何评估招聘渠道？",
        [
            "https://example.com/article?id=1&utm_source=feed",
            "https://example.com/article?id=2&utm_source=feed",
        ],
        freq=2,
        latest_posted_at="2026-05-01",
    )

    score = question_rank_score(q, today=date(2026, 5, 28))

    assert score.source_count == 2
    assert score.total == 2.0


def test_merge_ignores_malformed_date_when_valid_date_exists():
    qs = [
        Question("What is MCP?", ["u1"], latest_posted_at="not-a-date"),
        Question("what is mcp", ["u2"], latest_posted_at="2026-05-01"),
    ]

    out = dedupe_and_rank(qs, today=date(2026, 5, 28))

    assert out[0].latest_posted_at == "2026-05-01"
