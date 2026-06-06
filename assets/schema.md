# Data Structures

- **RawPost** `{ source, url, post_type(text|image|mixed), raw_text, locator_text, content_text, image_ocr_text|null, needs_vision_fallback, extraction_quality, posted_at(ISO date|null), asset_paths[], comments[] }`
  One scraped unit (a question-like line, post, or image). `posted_at` is the source post date
  (ISO `YYYY-MM-DD`) or null for undated sources. Produced by connectors. Filtered to the recency
  window by `corpus/recency.py`. `raw_text` is the current best primary content for legacy pipeline
  compatibility; `locator_text` is source metadata for retrieval/filtering.
- **Question** `{ text, source_refs[], freq, latest_posted_at(ISO date|null), role_tags[], topic, modality_origin(text|ocr|vision) }`
  A normalized interview question. `latest_posted_at` is the most recent date among merged
  duplicates. Produced by the agent's extraction step from RawPosts, then merged/ranked (by
  frequency AND recency) by `corpus/dedupe_rank.py`.
- **FollowUpChain** `{ seed_question, resume_anchor, followups[], is_grounded }`
  A personalized follow-up chain. Produced by the agent's project-anchoring step.
  `is_grounded=false` means it degraded to a plain 八股 question (no resume anchor found).

Persistence: normalized JSON under `corpus_cache/` via `corpus/store.py`.

## Image posts & OCR

Image-based posts (小红书) use `post_type="image"`. The connector downloads images to
`corpus_cache/assets/xhs/{note_id}/`, runs OCR in image order, and stores the merged page text in
`image_ocr_text` and `content_text`. Captions/tags stay in `locator_text` so extraction reads the
image content first. Low-quality OCR sets `needs_vision_fallback=true`.
