# AI Declaration

This document explains how I approached the theme, what I built, and exactly how AI coding assistants were used. Every number quoted here comes from a file in this repository and can be re-run.

## The problem

The theme asks for a scorer that rewards **new and relevant** product feedback. Each review has three parts (what the reviewer likes, dislikes, and what problem the product solves). It must be compared with:

- a fixed product description of 100 words or fewer, and
- a corpus of about 50 earlier reviews.

The score must be high only when a review is both **novel** (it says something the corpus does not) and **relevant** (it is about this product). Repeated, paraphrased, off-topic, and nonsensical reviews should score low.

## Why I chose it

- **It is a real product problem.** Review platforms and feedback tools are full of repetitive, generic, or off-topic reviews. Rewarding reviewers for genuinely new, useful detail improves the signal for everyone who reads them.
- **The two requirements pull against each other.** Novelty alone rewards nonsense, because gibberish is "new". Relevance alone rewards repetition. The design has to make relevance a real gate rather than a small adjustment, and that is an interesting design problem rather than a single model call.
- **Correctness can actually be measured.** Unlike open-ended generation, each review can be labelled (novel and relevant, paraphrase, off-topic, gibberish, vague), so I could build an evaluation and prove, or disprove, that the system works.
- **It exercises the full range of applied AI engineering**: LLM prompting, local embeddings, LLM-as-a-judge, evaluation, and a production harness around an agent.

## The solution

NoveltyLens is an **agent** (three LLM roles plus two local tools) wrapped in a **harness** that controls latency, cost, safety, and failure.

**Scoring pipeline**

1. **Guardrails first.** Secrets and personal data are masked locally before any model call or storage. Content moderation runs in parallel with scoring.
2. **Claim extraction.** An LLM splits each of the three fields into small, single-fact claims, with the three fields processed concurrently.
3. **Embedding and search.** Claims are embedded on the local CPU and compared with the corpus, whose embeddings are computed once at startup, in a single matrix multiplication.
4. **Three-band routing.**
   - Clearly repeated claims (similarity ≥ 0.75) are marked covered without an LLM call.
   - Clearly new claims (≤ 0.35) are marked novel without an LLM call.
   - Only the uncertain middle band goes to an LLM judge. The judge compares the claim with its three closest corpus claims and answers *full*, *partial*, or *none*, which earn 0, 0.5, or 1 novelty.
5. **Relevance judge.** A graded rubric scores each claim's relevance to the product and to its field.
6. **Scoring.** Each claim scores **novelty × relevance**, so an off-topic claim scores 0 however new it is. Fields are averaged, and a filled-in field with no usable claims counts as 0.

**Key design decisions**

- **Claim-level scoring instead of whole-review scoring.** A review mixing one new insight with filler gets partial credit, and each decision is explained per claim in the UI.
- **Cheap math decides the easy cases; the LLM decides only the hard ones.** This keeps cost and latency down and makes behaviour more predictable.
- **Relevance multiplies novelty per claim.** Averaging first would let a relevant repeated claim lend relevance to an irrelevant new one.
- **Prompts are versioned Markdown files** (`backend/prompts/`), and the version is part of the response-cache key, so a prompt edit can never be served a stale cached answer.

**Production harness around the agent**

- **Concurrency and retries:** async model calls with a concurrency limit, and retries with backoff that honour the provider's retry-after hints.
- **Failure handling:** model fallbacks, a circuit breaker and budget cap that fall back to a clearly labelled embedding-only "degraded" mode, and validation of every model output with one repair attempt.
- **Caching and observability:** an in-memory and on-disk response cache, request tracing (`logs/traces.jsonl`, and a trace panel in the UI), and a `/stats` endpoint.
- **Guardrails:** secret and PII masking, LLM content moderation on a swappable endpoint (OpenRouter today, a self-hosted model later), a deterministic block rule for directed abuse, and an admin-only, token-protected corpus rebuild.

**Evidence**

| Check | Result | Source |
| --- | --- | --- |
| Automated tests | 91 passing | `make test` |
| Tuning set (25 cases; thresholds and prompts were tuned on it, so this is in-sample) | separation margin +0.389, ROC-AUC 1.000 | `reports/eval.md` |
| **Held-out set** (15 cases written after tuning, never used to tune) | **12 / 15 passed**, margin +0.111, ROC-AUC 1.000 | `reports/holdout.md` |
| Load test (cold: caches off) | p50 3.6 s at 1 concurrent user, $0.0018 per review | `reports/load.md` |
| Load test (warm: cached) | p50 13 ms at 1 concurrent user | `reports/load.md` |

The three held-out failures are documented rather than tuned away:

- two paraphrases scored 0.36–0.39, because the corpus claims drop some details;
- one novel review scored 0.50, because claim extraction removed the product from a sentence.

## How I used AI coding assistants

I used AI assistants for most of the code. The problem choice, the design direction, the review of every change, the decisions about trade-offs, and the acceptance or rejection of results were mine.

| Phase | Assistant and model | What it did |
| --- | --- | --- |
| Research and solution design | Claude Pro, Opus 5.5 | Explored approaches to measuring novelty and relevance; shaped the claim-level pipeline, the three-band routing, and the evaluation plan. |
| Repository setup and first pipeline | Codex, GPT-6 Luna | Scaffolded the FastAPI backend and Next.js frontend; built the first working pipeline (extraction, embeddings, similarity, judge), the first tests, the evaluation script, and the smoke test. |
| UI/UX | Antigravity, Gemini Flash 3.8 | Designed and built the Next.js interface: review form, presets, score gauge, claim cards, corpus inspector. |
| Enhancements, fixes, harness, tests, corpus | Claude Pro, Opus 5.5 and Sonnet 5 | Audited the codebase and fixed scoring defects. Built the production harness (async calls, batching, retries, circuit breaker, caching, tracing, `/stats`, load test) and the held-out evaluation. Added guardrails (masking, moderation, admin-only corpus rebuild), the trace and architecture views, test cases, and remaining tasks. |

The comparison corpus (`backend/corpus.json`, 50 reviews) was **generated by an LLM** from the product description; it is synthetic, not real customer data. The labelled evaluation cases were written with AI assistance and reviewed by me.

## How I checked the AI's work

I treated AI output as a draft to verify, not as a result. Several problems were found only because I measured, asked for skeptical audits, and tested in a real browser:

| Problem found | How it surfaced | What was done |
| --- | --- | --- |
| The relevance judge scored genuinely new details as 0 because they were "not mentioned in the product description" | Reading the judge's reasons on failing eval cases | Rewrote the rubric; separation margin went from −0.083 to positive |
| The coverage judge called specific new claims "partial" whenever the corpus had a vaguer claim | Per-claim eval review | Clarified the prompt definition |
| "It's good / Could be better" scored 0.625 | A skeptical audit with unseen cases | Filler is capped at relevance 0.25, and empty fields count as 0 |
| The headline eval numbers were in-sample | The same audit | Added a held-out set and reported its weaker result honestly |
| A fresh clone had no corpus | Fresh-clone test | Corpus committed to the repository |
| "fuck off" was only flagged, not blocked | My own manual UI testing | Local rule plus a clearer moderation policy |
| An empty `TRACE_LOG_PATH` setting crashed every request | Browser testing | Fixed, with a test |
| UI labels showed stale thresholds (48% and 82%) | My own manual UI testing | Labels now read the real thresholds from the server |

## Limitations I am aware of

- **Novelty is not truth.** An invented claim can be novel and relevant.
- **Shared model family.** The corpus and the judges come from the same model family, which can share blind spots.
- **Small evaluation sets.** Thresholds were tuned on 25 cases and checked on 15, which is not broad calibration.
- **Gaps in guardrails:**
  - person names and street addresses are not yet detected;
  - there is no local toxicity model;
  - there is no per-user authentication or rate limit on scoring.
