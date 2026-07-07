# Question Evidence Validation Design

## Goal

Prevent a question from entering ranking merely because an Agent attached a source URL. Every new question must carry a source excerpt that can be found in a retained RawPost.

## Model

`QuestionEvidence` stores `source_url`, `excerpt`, authoritative `posted_at`, and `modality_origin`. `Question` gains `evidence[]`. Missing fields default cleanly so old JSON remains readable.

## Validation

`prepare_questions(raw_posts, questions)` classifies and filters RawPosts, validates evidence URLs after tracking-parameter normalization, and compares whitespace-normalized excerpts against `content_text/raw_text`. Valid evidence is rebuilt using the RawPost date. Invalid evidence produces structured issue codes and is removed. A question with no valid evidence is rejected by default.

`require_evidence=False` is an explicit migration mode for old caches. It keeps legacy questions but records `legacy_unverified`; reports must not call these grounded or high-frequency.

## Output

The result contains ranked questions, rejected questions, structured issues, and recency counts. Canonical duplicates merge evidence as well as source URLs. Only the validated ranked list may feed the report's high-frequency section.

## Non-Goals

- Calling an LLM or implementing automatic question extraction.
- Semantic verification that a paraphrase is logically equivalent to an excerpt.
- Replacing the full Agent orchestration workflow.
