from scripts.corpus.extraction import ExtractionCandidate, ExtractionDecision
from scripts.models import Question, QuestionEvidence, RawPost
from scripts.corpus.store import (
    load_extraction_candidates,
    load_extraction_decisions,
    load_questions,
    load_raw_posts,
    save_extraction_candidates,
    save_extraction_decisions,
    save_questions,
    save_raw_posts,
)


def test_raw_posts_save_and_load(tmp_path):
    posts = [RawPost("github", "u1", "text", "Q1"), RawPost("github", "u2", "text", "Q2")]
    path = tmp_path / "raw.json"
    save_raw_posts(posts, path)
    assert load_raw_posts(path) == posts


def test_questions_save_and_load(tmp_path):
    qs = [
        Question(
            "Q1",
            ["u1"],
            evidence=[QuestionEvidence(source_url="u1", excerpt="Q1")],
        ),
        Question("Q2", ["u2"], freq=3),
    ]
    path = tmp_path / "q.json"
    save_questions(qs, path)
    assert load_questions(path) == qs


def test_extraction_artifacts_save_and_load(tmp_path):
    candidates = [
        ExtractionCandidate(
            "candidate_1", "u1", "1. 如何评估招聘渠道？", "如何评估招聘渠道？"
        )
    ]
    decisions = [
        ExtractionDecision("candidate_1", True, "评估招聘渠道", role_tags=["市场"])
    ]

    candidate_path = tmp_path / "candidates.json"
    decision_path = tmp_path / "decisions.json"
    save_extraction_candidates(candidates, candidate_path)
    save_extraction_decisions(decisions, decision_path)

    assert load_extraction_candidates(candidate_path) == candidates
    assert load_extraction_decisions(decision_path) == decisions
