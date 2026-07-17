# Evidence-First Question Extraction Design

## Goal

Convert collected `RawPost` records into a repeatable, auditable question set
without allowing semantic automation to create untraceable interview claims.
The resulting set must be more useful than a raw corpus, accurate enough to
trust, and capable of being targeted to a role and resume by the existing agent
workflow.

## Product Decision

Use a hybrid pipeline:

1. Deterministic Python code finds candidate source spans and keeps each span
   immutable.
2. The agent performs the semantic work that rules cannot do reliably in Chinese:
   identify actual interview questions, give each a readable display text,
   normalize its intent, assign topic and role tags, and discard irrelevant
   candidates.
3. Deterministic Python code accepts only well-formed decisions tied to an
   existing candidate, converts them to `Question` records, and passes them to
   `prepare_questions()`.

No LLM SDK, network API, crawler, or report generator is added in this slice.
The current agent is the semantic executor and Python remains the trust boundary.

## Architecture

Add `scripts/corpus/extraction.py` with four focused responsibilities:

- `ExtractionCandidate`: serializable immutable source span with `candidate_id`,
  `source_url`, `excerpt`, source-derived `display_text`, `posted_at`, and
  `modality_origin`.
- `ExtractionDecision`: serializable agent response with `candidate_id`,
  `accepted`, `canonical_text`, `topic`, and `role_tags`.
- `extract_candidates(raw_posts)`: deterministic segmentation of textual
  `content_text` into plausible interview-question spans.
- `materialize_questions(candidates, decisions)`: fail-closed conversion from
  accepted decisions to `Question` values with `QuestionEvidence` copied from
  the immutable candidate.

The data flow is:

```text
RawPost -> ExtractionCandidate[] -> agent decisions -> Question[]
       -> prepare_questions(raw_posts, questions) -> ranked questions + diagnostics
```

`ExtractionCandidate` is intentionally not a `Question`. A candidate means only
that a span is worth semantic review; it does not claim that the span is a real
interview question. The agent may reject a candidate, but it may not create a
decision for an unknown candidate or substitute a different evidence excerpt.

Candidate IDs are stable for the same normalized source URL, ordinal, and source
span. A rerun over unchanged input therefore produces IDs that an agent can
reference consistently. Duplicate candidate IDs are not silently repaired.

## Candidate Extraction

`extract_candidates()` is conservative and deterministic. It works over
`RawPost.content_text` (falling back to `raw_text`) and produces candidates from
non-empty lines or list items that show at least one interview-like signal:

- Chinese or English question punctuation, such as `?` or `？`.
- common interview framing such as `问`, `问题`, `一面`, `二面`, `面试官`,
  `追问`, or numbered question-list markers.
- a question-like list item where a numbered list uses a nearby interview framing
  line as context.

The extractor never rewrites source text. It strips only surrounding whitespace,
limits each candidate to a single source line/list item, and preserves the exact
remaining excerpt. Its `display_text` only removes a leading list marker or
interview framing prefix from that excerpt; the original excerpt remains the
evidence shown to users and validated downstream. Lines that are clearly narrative
without a question signal are not sent to the agent. This bounds review volume
without pretending that rules can decide semantic relevance.

The candidate modality is derived from the `RawPost`: text posts yield `text`;
image posts whose main content is OCR yield `ocr`; content explicitly supplied by
a vision fallback yields `vision`. The agent cannot change it.

## Agent Decision Contract

`SKILL.md` will require the agent to read `extraction_candidates.json` and write
one structured decision per reviewed candidate. The permitted shape is:

```json
{
  "candidate_id": "candidate identifier from the input",
  "accepted": true,
  "canonical_text": "Short semantic intent used to merge paraphrases",
  "topic": "Optional topical label",
  "role_tags": ["Optional role or skill labels"]
}
```

For `accepted: false`, semantic fields are ignored. The agent should
reject navigation text, unrelated discussion, generic advice, and ambiguous
fragments. It may use role direction and resume terms to decide relevance and
assign tags, but neither can alter source URL, date, evidence excerpt, or source
frequency. It also cannot submit a replacement display question: the final
`Question.text` is the candidate's deterministic source-derived `display_text`.

An accepted decision requires non-empty `canonical_text`. One candidate can
produce at most one question; splitting compound source lines belongs to a future
extraction improvement after real failure examples exist.

## Validation and Failure Behavior

`materialize_questions()` returns an `ExtractionMaterializationResult` containing
accepted questions, rejected decisions, and structured `ExtractionIssue` values.
It rejects, without raising, these malformed inputs:

- unknown or duplicate decision candidate IDs;
- duplicate candidate IDs;
- accepted decisions missing canonical intent;
- non-string or empty role tags;
- candidates with blank URL or excerpt.

For every accepted decision, it constructs exactly one `Question` using the
candidate's source-derived `display_text`, and one `QuestionEvidence` using its
immutable URL, excerpt, date, and modality. It does not accept agent-provided
question text or evidence fields. Then `prepare_questions()` remains responsible
for recency filtering, source lookup, excerpt verification, de-duplication, and
independent-source ranking. A question rejected by either stage is excluded from
the report and recorded in diagnostics.

## Persistence and Workflow

Extend `scripts/corpus/store.py` with explicit save/load helpers for candidates
and decisions, using the same JSON conventions as raw posts and questions. A
standard run writes:

- `corpus_cache/raw_posts.json`
- `corpus_cache/extraction_candidates.json`
- `corpus_cache/extraction_decisions.json`
- `corpus_cache/questions.json`

The skill workflow will instruct the agent to expose extraction and grounding
diagnostics in the final preparation package. "High frequency" still requires
two evidence-validated independent URLs; candidates and ungrounded drafts never
qualify.

## Testing Strategy

Add focused fixture-free tests for:

- Chinese question lines, interview-framed numbered lines, and non-question
  narrative rejection;
- stable candidate IDs and correct text/OCR/vision modality assignment;
- successful materialization preserving immutable evidence;
- unknown ID, duplicate ID, blank mandatory fields, and malformed tags;
- an end-to-end in-memory flow from `RawPost` to ranked grounded question,
  including a negative case that proves decisions cannot replace source-derived
  display text or evidence.

Existing `prepare_questions()` and ranking tests remain the regression contract.
Run the complete test suite, compile all scripts, and check documentation diffs
before integration.

## Deferred Work

- A CLI runner or GitHub Actions end-to-end job (Plan 9).
- LLM-provider integration or a standalone graphical interface.
- Douyin ingestion and video ASR (Plan 10).
- Golden-set evaluation and trace replay, which should use the new artifacts in a
  later quality-evaluation slice.
