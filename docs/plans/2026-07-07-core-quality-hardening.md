# Core Quality Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and execute each task in red-green order.

**Goal:** Make retrieval and ranking failures explicit while improving the evidence quality of high-frequency questions.

**Architecture:** Keep existing connector and corpus APIs, add narrowly scoped classification/scoring helpers, and evolve `Question` with one backward-compatible field. Agent behavior is updated through `SKILL.md`; deterministic behavior remains in Python.

**Tech Stack:** Python dataclasses, pytest, BeautifulSoup, existing JSON persistence.

---

### Task 1: Connector Partial Results

**Files:** `tests/test_nowcoder_connector.py`, `tests/test_github_connector.py`, `scripts/connectors/nowcoder.py`, `scripts/connectors/github.py`

- [ ] Add tests where the first URL succeeds and the second fails; require the successful post plus `degraded` status.
- [ ] Add tests that empty parsed posts are removed and make the result degraded.
- [ ] Add GitHub tests for query fallback and empty effective hints.
- [ ] Run targeted tests and confirm failures.
- [ ] Move exception handling inside each URL loop and aggregate diagnostics.
- [ ] Run targeted tests and confirm passes.

### Task 2: Explicit Recency States

**Files:** `tests/test_recency.py`, `scripts/corpus/recency.py`

- [ ] Add tests for `undated`, `invalid`, `future`, one-day tolerance, and `keep_undated=False`.
- [ ] Run targeted tests and confirm failures.
- [ ] Implement `classify_recency` and update `filter_recent` without changing its default treatment of missing dates.
- [ ] Run targeted tests and confirm passes.

### Task 3: Canonical Dedupe And Source-Diverse Ranking

**Files:** `tests/test_models.py`, `tests/test_dedupe_rank.py`, `scripts/models.py`, `scripts/corpus/dedupe_rank.py`

- [ ] Add backward-compatible round-trip tests for `canonical_text`.
- [ ] Add tests that canonical paraphrases merge and that two independent sources outrank repeated same-source occurrences.
- [ ] Add tests for a public ranking score breakdown.
- [ ] Run targeted tests and confirm failures.
- [ ] Implement the optional model field, canonical key, and source-diverse scoring.
- [ ] Run targeted tests and confirm passes.

### Task 4: Contract And Documentation Alignment

**Files:** `SKILL.md`, `README.md`, `assets/schema.md`

- [ ] Require canonical intent generation while preserving source wording and entities.
- [ ] Define high frequency as independent-source support, with occurrence count only secondary.
- [ ] Explain known-date cutoff and undated fallback accurately.
- [ ] Remove the unsupported `90%+` coverage statement.

### Task 5: Verification

**Files:** all changed files

- [ ] Run the complete pytest suite.
- [ ] Run aggregate-only quality checks against existing ignored cache.
- [ ] Inspect diff for compatibility and unrelated changes.
- [ ] Remove temporary root planning files.
