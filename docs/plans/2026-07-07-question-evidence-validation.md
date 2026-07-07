# Question Evidence Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and execute every behavior in red-green order.

**Goal:** Build a deterministic evidence gate between Agent extraction and question ranking.

**Architecture:** Extend the existing dataclasses compatibly, then add a pure corpus quality module that filters sources, validates excerpts, synchronizes metadata, and delegates ranking to `dedupe_and_rank`.

**Tech Stack:** Python dataclasses, standard library URL/text normalization, pytest.

---

### Task 1: Evidence Model

**Files:** `scripts/models.py`, `tests/test_models.py`, `tests/test_store.py`

- [ ] Add failing round-trip and legacy compatibility tests.
- [ ] Add `QuestionEvidence` and nested `Question.from_dict` conversion.
- [ ] Run model/store tests.

### Task 2: Evidence Gate

**Files:** `scripts/corpus/quality.py`, `tests/test_quality_pipeline.py`

- [ ] Add failing tests for valid excerpts, hallucinated excerpts, stale sources, whitespace normalization, and legacy mode.
- [ ] Implement structured issues and `prepare_questions`.
- [ ] Run quality tests.

### Task 3: Dedupe Integration

**Files:** `scripts/corpus/dedupe_rank.py`, `tests/test_dedupe_rank.py`

- [ ] Add a failing test for evidence merging across canonical duplicates.
- [ ] Merge evidence without duplicates.
- [ ] Run ranking tests.

### Task 4: Agent Contract

**Files:** `SKILL.md`, `README.md`, `assets/schema.md`

- [ ] Require evidence excerpts during extraction.
- [ ] Route the deterministic stages through `prepare_questions`.
- [ ] Document strict and legacy behavior.

### Task 5: Verification

- [ ] Run full pytest and compile checks.
- [ ] Confirm old ignored caches still deserialize.
- [ ] Inspect diff, remove temporary root planning files, and commit.
