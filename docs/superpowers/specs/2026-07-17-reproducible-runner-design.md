# Reproducible Corpus Runner Design

**Date:** 2026-07-17
**Status:** Approved for implementation under the repository owner's standing
autonomous-product-direction instruction

## Problem

The repository now has deterministic primitives for source normalization,
candidate extraction, reviewer decisions, evidence-based question
materialization, recency filtering, and ranking. They are valuable in
isolation, but a user cannot yet run the chain once and retain an auditable
record of exactly what produced a question list. That makes failures difficult
to reproduce and makes it too easy to accidentally prepare an interview from a
stale or altered corpus.

This milestone makes the existing offline portion of the pipeline reproducible.
It deliberately does not claim to automate browser search, authenticated site
collection, resume interpretation, semantic reviewer decisions, or final
preparation prose.

## Alternatives Considered

1. **Online all-in-one runner.** It would search platforms and call an agent
   before extraction. This is not selected: credentials, site policies, and
   judgement-based search terms would be hidden dependencies, so the result
   would not be reliably reproducible.
2. **Artifact-only runner (selected).** The operator supplies the normalized
   `raw_posts.json` and explicit `extraction_decisions.json`; the runner writes
   every deterministic intermediate result and an integrity manifest. The
   agent/browser steps remain visible, replaceable inputs.
3. **Documentation-only procedure.** This would describe a manual sequence but
   leave users to join modules and would not protect against inconsistent
   intermediate files. It is not sufficient.

## Public Interface

Add `scripts/corpus/runner.py` with a testable API:

```python
def run_pipeline(
    raw_posts_path: Path,
    decisions_path: Path,
    output_dir: Path,
    *,
    today: date | None = None,
) -> PipelineRunResult:
    ...
```

The module also exposes a CLI:

```text
python -m scripts.corpus.runner \
  --raw-posts corpus_cache/raw_posts.json \
  --decisions corpus_cache/extraction_decisions.json \
  --output corpus_cache/runs/2026-07-17-backend \
  --today 2026-07-17
```

`--today` is optional. It accepts only ISO calendar dates. Users who need
byte-for-byte repeatability pass it explicitly; otherwise the current local
date is used solely as the existing recency policy's reference date.

## Data Flow

The runner performs these operations in this exact order:

1. Read each input file once into an immutable byte snapshot, calculate its
   SHA-256 from that snapshot, and deserialize the same bytes.
2. Extract immutable evidence candidates with `extract_candidates(raw_posts)`.
3. Materialize source-derived questions with
   `materialize_questions(candidates, decisions)`.
4. Apply `prepare_questions(raw_posts, materialized_questions, today=today)`.
5. Write a fresh run directory containing canonical copies of inputs,
   extraction artifacts, quality output, and a manifest.

`prepare_questions()` remains the only authority that rejects insufficient
evidence or stale questions and that determines rank order. The runner must not
reimplement its rules.

## Run Package

The selected output directory must not exist. This avoids mixing a new run with
stale files and prevents destructive overwrites. The runner reserves it with an
atomic directory creation before processing, so concurrent runs cannot both
claim the same destination. It removes the directory it reserved when
processing fails; a run becomes consumable only once `manifest.json` exists.

Each successful run contains:

| Path | Contents |
| --- | --- |
| `raw_posts.json` | Canonical stored copy of supplied normalized posts. |
| `extraction_decisions.json` | Canonical stored copy of supplied reviewer decisions. |
| `extraction_candidates.json` | Evidence candidates before reviewer selection. |
| `materialized_questions.json` | All questions accepted by valid decisions, before quality filtering. |
| `ranked_questions.json` | The only question list that downstream preparation may consume. |
| `rejected_questions.json` | Questions removed by evidence or recency policy. |
| `diagnostics.json` | Materialization issues, quality issues, and recency counts. |
| `manifest.json` | Schema, source-input hashes, artifact hashes, and count summary. |

The manifest excludes a hash of itself to avoid a circular identity. It includes
SHA-256 hashes of all preceding artifacts, the source-byte hashes of both
provided input paths, and the effective ISO `today` value used by recency
filtering. It includes neither absolute paths nor wall-clock timestamps. Its
schema version starts at `1`.

All JSON is written with the repository's existing canonical serializers and a
stable filename order. With byte-identical source inputs and the same explicit
`today`, every JSON file in separately named output directories is
byte-identical.

## Error Handling

- A missing, malformed, or schema-invalid input propagates the existing
  validation error and produces no final directory.
- An existing output path is rejected before any work begins, including an
  empty directory, so a retry must use a new run identifier.
- Invalid decisions and candidates without any decision remain represented by
  materialization issues; neither can become questions silently.
- Invalid `--today` is reported by argparse as a command-line error.
- The runner removes its reserved output directory on any write or processing
  failure.

## Documentation and CI

`SKILL.md` gains the operational handoff: after collection and explicit
decisions, run the offline package command, inspect diagnostics, and feed only
`ranked_questions.json` into preparation. `README.md` records the completed,
honest scope of the reproducible runner rather than claiming an online
end-to-end agent.

The GitHub Actions test job keeps its Python 3.11/3.12 matrix and additionally
runs `python -m compileall -q scripts`. End-to-end coverage runs through pytest
using only small in-repository fixture objects; no network, credentials, resume,
or live corpus data are added.

## Verification

Tests must cover a successful run, artifact and manifest hash correctness,
byte-stable replay with a fixed date, stale-question diagnostics, byte-snapshot
integrity, atomic destination reservation, missing-decision diagnostics, refusal
to overwrite an existing destination, and CLI date parsing. The existing full
test suite and compile check must pass on the supported interpreter baseline.

## Scope Boundary

This package is an auditable bridge from already-collected normalized evidence
to ranked interview questions. Search query generation, connectors, browser
collection, reviewer decision generation, resume tailoring, and final answer
writing remain separate agents or operator steps. Their outputs are explicit
inputs or downstream consumers, not hidden runner behavior.
