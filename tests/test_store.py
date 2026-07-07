from scripts.models import Question, QuestionEvidence, RawPost
from scripts.corpus.store import (
    save_raw_posts, load_raw_posts, save_questions, load_questions,
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
