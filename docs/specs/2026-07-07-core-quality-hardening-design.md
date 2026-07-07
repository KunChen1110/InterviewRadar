# Core Quality Hardening Design

## Context

InterviewRadar's components are well tested, but three implementation details weaken its core promise: a single connector failure can erase valid results, unknown and malformed dates are treated identically, and question frequency is based on exact-string occurrence counts rather than independent source support.

## Considered Approaches

1. **Documentation-only correction.** Lowest risk, but does not improve generated packages.
2. **Targeted quality hardening (selected).** Fix connector isolation, recency states, canonical dedupe, and source-diverse ranking while keeping existing cache formats readable.
3. **Full evidence-pipeline rewrite.** Best long-term architecture, but too broad for a first bug-fix pass and would mix schema, runner, extraction, and evaluation changes.

## Connector Behavior

Each URL is fetched independently. Successful posts survive failures from other URLs. Empty parsed posts are discarded. Any failed or empty URL makes the result `degraded`, with counts in the message. GitHub relevance uses explicit `relevance_hints` first and falls back to non-empty search queries; an empty effective hint set degrades instead of silently ingesting unrelated repositories.

## Recency Behavior

Dates are classified as `recent`, `stale`, `undated`, `invalid`, or `future`. `filter_recent` keeps recent posts and, by default, undated supplemental posts. It drops stale, malformed, and implausibly future-dated posts. A one-day future tolerance handles timezone boundaries. Documentation must say that the hard cutoff applies to known dates and that undated content is retained at the lowest ranking weight.

## Dedupe And Ranking

`Question` gains an optional `canonical_text` field. Existing caches remain valid because the field defaults to empty. The Agent produces a short canonical intent that preserves technical entities and business distinctions. Dedupe uses `canonical_text` when present, otherwise the original text.

Ranking prioritizes the number of distinct source URLs, multiplied by recency weight. Occurrence count is only a tie-breaker, preventing duplicate lines from one repository from masquerading as broad interview frequency. A public score breakdown exposes source count, occurrence count, recency weight, and total score for report generation and testing.

## Compatibility

Existing JSON without `canonical_text` continues to load. `dedupe_and_rank` keeps its return type. Existing callers of `filter_recent` keep undated posts by default, but malformed dates no longer pass through.

## Verification

- Regression tests reproduce partial connector loss, invalid-date leakage, same-source frequency inflation, and canonical paraphrase non-merging.
- Targeted tests must fail before implementation and pass afterward.
- Full pytest must pass on the repository environment.
- Aggregate checks against the ignored real cache must not read or print personal content.
