# Interview Intelligence Skill — Design Spec

Date: 2026-05-28
Status: Approved for planning

## 1. Purpose

An AI-native **Interview Intelligence Skill** packaged as a Claude Code / Agent Skill.
Given a user's **resume (image/PDF)** and a **fuzzy target role**, it broad-net retrieves
real interview-experience (面经) content from UGC platforms, extracts high-frequency
questions, and produces a **personalized static prep package** — including project-anchored
follow-up questions grounded in the user's actual resume.

It is explicitly **not**: a static question bank, a generic GPT mock interviewer, or a
JD-matching tool. The differentiator is turning scattered, multimodal, real-world 面经
content into personalized interview intelligence.

**Recency is a core, non-negotiable requirement.** Interview questions go stale fast, so the
skill must surface content from roughly the **last 2 years** and discard older material.
Timeliness is treated as a first-class pipeline concern: posts carry a date, the pipeline
filters to the recency window, and ranking is weighted toward more recent content. This is why
live timestamped UGC (牛客, 小红书) — not static archived corpora or years-old GitHub repos — is
the primary source of value.

## 2. Scope (V1)

**In scope**
- Input: resume image/PDF + a fuzzy role term (e.g. "AI 应用开发"). **No JD.**
- **Iterative, data-driven retrieval** (replaces one-shot role-name expansion): seed by role
  direction + resume skills/topics, harvest the *actual* role names/tags/terms that appear in
  first-pass results, re-query, repeat until no new vocabulary emerges. Relevance is judged by
  **content semantics**, not by matching a pre-guessed role-name list. A human-in-the-loop
  checkpoint lets the user confirm/steer the *discovered* directions after seeing real data.
- Retrieval from UGC sources, prioritized by timeliness:
  - **Primary (timestamped, timely):** 牛客 NowCoder (text + images), 小红书 (image-based 八股
    questions, OCR).
  - **Supplementary:** GitHub interview repos (plain text) — convenient and always-available,
    but often stale, so it is a fallback/補充 source, not the main value driver.
- **Recency filtering**: extract each post's date and discard content older than ~2 years.
- Multimodal extraction with a **hybrid OCR strategy** (coarse OCR + vision-model fallback).
- Deduplication + ranking by frequency **and recency** (recent posts weighted higher).
- **Project-anchored reasoning**: match scraped questions against resume projects/skills;
  generate personalized follow-up chains where they connect, otherwise keep as plain 八股.
- Output: a personalized prep package (Markdown).

**Out of scope (future iterations)**
- JD-specific targeting (a later, narrower mode).
- ASR-based sources (抖音 / B站 video transcription).
- Interactive turn-by-turn mock interview (the agent acting as live interviewer).

## 3. End-to-End Workflow

```
[Resume image/PDF] + [fuzzy role term]
        │
(1) Resume understanding ── hybrid OCR/vision → structured resume (skills, projects, keywords)
        │
(2) Seed query generation ─ from role direction + resume skills/topics (agent, RAG, MCP,
                            LLM应用, prompt…), NOT a guessed role-name list
        │
(3) Iterative retrieval loop ─ connectors: github / nowcoder / xiaohongshu (unified iface + degrade)
        │   ├─ first pass: scrape with seed queries
        │   ├─ vocabulary harvest: agent reads results, harvests REAL role names/tags/terms
        │   ├─ re-query with harvested vocabulary; repeat until no new terms emerge
        │   └─ HUMAN-IN-THE-LOOP: show discovered directions/terms from real data; user steers
        │
(4) Content-semantic relevance ─ agent judges each post's relevance by content, not name match
        │
(5) Multimodal extraction ── xhs image questions: hybrid OCR; nowcoder text+image; github text
                             → normalized Question records (carry posted_at)
        │
(5b) Recency filter ──────── drop posts older than ~2 years (by posted_at)
        │
(6) Dedupe & rank ────────── semantic dedupe, rank by frequency AND recency → high-freq set
        │
(7) Project-anchored reasoning ─ per question, match against resume projects:
                                 connects → personalized follow-up chain
                                 no match → keep as plain 八股
        │
(8) Prep package ─────────── Markdown: role analysis / gap / high-freq 八股 /
                             personalized project follow-ups / reference approaches
```

Deterministic dirty work (scraping, coarse OCR, persistence, dedupe/rank) lives in Python
scripts. Judgment and reasoning (resume understanding, role expansion, query generation,
project anchoring, prep-package authoring) are performed by the agent per `SKILL.md`.

## 4. Skill Package Structure

```
interview-intelligence/
  SKILL.md                      # Orchestration: drives the 8-step workflow, tool-call conventions
  scripts/
    resume_extract.py           # Resume image/PDF → text (coarse OCR; flags complex layout for vision)
    connectors/
      base.py                   # Unified iface: search(queries) -> list[RawPost]
      github.py                 # GitHub interview repos (plain text; git clone / API)
      nowcoder.py               # 牛客 (text+image; cookie support, date extraction, degrade to manual import)
      xiaohongshu.py            # 小红书 (image questions; adapter over MediaCrawler, cookie reuse)
    ocr/
      extract.py                # Hybrid OCR: coarse pass + low-confidence/complex flag → vision fallback
    corpus/
      store.py                  # Persist results as normalized JSON (source/url/raw/asset paths)
      recency.py                # Filter RawPosts to the recency window (~2 years) by posted_at
      dedupe_rank.py            # Semantic dedupe + frequency-and-recency ranking
  assets/
    schema.md                   # RawPost / Question / FollowUpChain data structures
```

Division of labor principle: deterministic work in Python; judgment/reasoning by the agent.
Seed query generation is intentionally NOT backed by any preset word list — the agent derives
seeds (related role aliases + resume skills/topics) from its own domain knowledge, so the skill
generalizes to any field (marketing, quant, backend, …). Domain knowledge belongs in the
agent's reasoning, not in static config files that go stale and only cover one domain.

## 5. Data Structures

```
RawPost   { source, url, post_type(text|image|mixed), raw_text, posted_at(ISO date|null),
            asset_paths[], comments[] }
Question  { text, source_refs[], freq, latest_posted_at(ISO date|null), role_tags[], topic,
            modality_origin }
FollowUpChain { seed_question, resume_anchor(project/skill), followups[], is_grounded }
```

`posted_at` carries the source post's date (ISO `YYYY-MM-DD`, or null when a source has none,
e.g. an undated GitHub repo). The pipeline filters out RawPosts older than the recency window
(~2 years). On dedupe, the merged `Question` keeps `latest_posted_at` (the most recent date among
its duplicates) so ranking can weight recency alongside frequency.

Corpus persists to `./corpus_cache/` (normalized JSON + downloaded image assets), decoupling
scraping from reasoning: re-running reasoning does not require re-scraping, and grounding is
auditable for debugging/validation.

## 6. Third-Party Dependencies & Compliance

- **MediaCrawler** (NanmiCoder, ~28k★) — 小红书/抖音/B站/微博/知乎/贴吧; QR + cookie login,
  keyword + comment scraping, CSV/JSON output. `xiaohongshu.py` is a thin adapter over it; reuses
  its cached login state. Future 抖音/B站 sources use the same tool.
  ⚠️ Declared for **learning / non-commercial use only**. This skill is a personal prep tool — do
  not commercialize. Documented as a constraint.
- **Newcoder-scraper** (HaodongZhangUCD) — reference for `nowcoder.py` (topic-based 牛客 scraping).
  Note: static archived corpora (e.g. `aikuyun/IT-Interview-experience`) were considered and
  **rejected** — they are years stale and violate the recency requirement.
- Existing Claude resume skills (`Paramchoudhary/ResumeSkills`, `jiito/interview-prep-skills`,
  `varunr89/resume-tailoring-skill`) — referenced for `SKILL.md` structure only; they are
  JD-based, plain-text, no real-面经 retrieval, so the broad-net multimodal + project-anchoring
  workflow remains the differentiator.

## 7. Error Handling / Degradation

- **Connector degradation**: on scrape failure (login wall / anti-bot / site change) a connector
  returns an explicit status and prompts the user ("provide cookie / paste post links / export
  content") rather than crashing the pipeline. The always-available GitHub (supplementary) source
  keeps the pipeline runnable even when primary connectors degrade — but recency-wise it is a weak
  fallback, so a degraded primary source should be surfaced to the user, not silently tolerated.
- **OCR fallback**: low-confidence or complex layout → flag and hand the image to the agent's
  vision capability; no questions are silently dropped.
- **Grounding validation**: a project-anchored follow-up must trace to (resume project/skill +
  a scraped real question). Otherwise it degrades to a plain 八股 question — the agent must not
  fabricate follow-ups.

## 8. Testing Strategy

- Each connector: offline parsing tests against recorded sample pages, including date extraction.
- Recency filter: constructed posts with dates spanning the window boundary (kept vs dropped).
- OCR: regression on a few real 小红书 面经 images.
- Dedupe/rank: constructed duplicate-question sets; verify recency weighting affects order.
- Project anchoring: a sample resume + sample question set verifying grounded vs non-grounded
  routing.

## 9. Open Questions / Future

- JD-targeted mode (narrow the broad-net to one posting).
- ASR sources (抖音 / B站) for video 面经.
- Interactive live mock interview mode.
