# Data Structures

- **RawPost** `{ source, url, post_type(text|image|mixed), raw_text, locator_text, content_text, image_ocr_text|null, needs_vision_fallback, extraction_quality, posted_at(ISO date|null), asset_paths[], comments[] }`
  One scraped unit (a question-like line, post, or image). `posted_at` is the source post date
  (ISO `YYYY-MM-DD`) or null for undated sources. Produced by connectors. Filtered to the recency
  window by `corpus/recency.py`. `raw_text` is the current best primary content for legacy pipeline
  compatibility; `locator_text` is source metadata for retrieval/filtering.
- **ExtractionCandidate** `{ candidate_id, source_url, excerpt, display_text, posted_at, modality_origin }`
  An immutable plausible question span. `excerpt` is the verbatim source proof;
  `display_text` is a deterministic source-derived label with only list/framing
  prefixes removed. It is not yet a validated question.
- **ExtractionDecision** `{ candidate_id, accepted, canonical_text, topic, role_tags[] }`
  The agent's constrained semantic decision for one candidate. It cannot provide
  question wording, URLs, dates, or evidence excerpts.
- **QuestionEvidence** `{ source_url, excerpt, posted_at(ISO date|null), modality_origin(text|ocr|vision) }`
  A verbatim source excerpt for one question occurrence. The quality pipeline verifies that the URL
  belongs to a retained RawPost and that the whitespace-normalized excerpt appears in its primary
  content. `posted_at` is synchronized from RawPost rather than trusted from Agent output.
- **Question** `{ text, canonical_text, evidence[], source_refs[], freq, latest_posted_at(ISO date|null), role_tags[], topic, modality_origin(text|ocr|vision) }`
  A normalized interview question. `latest_posted_at` is the most recent date among merged
  duplicates. `canonical_text` is a short semantic intent used to merge wording variants while
  preserving technical entities and important conditions. Produced by the agent's extraction step
  from RawPosts, validated by `corpus/quality.py`, then merged/ranked by independent source count
  and recency in `corpus/dedupe_rank.py`; occurrence count only breaks ties.
- **FollowUpChain** `{ seed_question, resume_anchor, followups[], is_grounded }`
  A personalized follow-up chain. Produced by the agent's project-anchoring step.
  `is_grounded=false` means it degraded to a plain 八股 question (no resume anchor found).

Persistence: normalized JSON under `corpus_cache/` via `corpus/store.py`.

## Image posts & OCR

Image-based posts (小红书) use `post_type="image"`. The connector downloads images to
`corpus_cache/assets/xhs/{note_id}/`, runs OCR in image order, and stores the merged page text in
`image_ocr_text` and `content_text`. Captions/tags stay in `locator_text` so extraction reads the
image content first. Low-quality OCR sets `needs_vision_fallback=true`.
