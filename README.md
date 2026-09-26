# Rewarding Novelty — Theme 3

Rewarding Novelty scores user generated product reviews on a **0.0–1.0** scale. It rewards claims that are new relative to a reference corpus while requiring relevance to a fixed product description.

The project uses OpenRouter's OpenAI-compatible API. It does not require a Google AI Studio key: models such as Gemini can be selected through OpenRouter in `.env`.

## The challenge

Each submission is evaluated against two things:

1. A fixed product description of 100 words or fewer in `backend/reference.py`.
2. A comparison corpus of approximately 50 previous submissions stored locally in `backend/corpus.json`.

A good score should be given only when the submission is both novel relative to the corpus and relevant to the reference product. Repeated, paraphrased, off-topic, and nonsensical content should score low.

## Submission format

The UI and API accept a G2-style product review with three discrete properties:

| Property | Meaning |
| --- | --- |
| `what_you_like` | A positive product observation or benefit. |
| `what_you_dislike` | A limitation, frustration, or improvement opportunity. |
| `problem_solved` | The user need or workflow the product addresses. |

## Architecture

The app is an **agent** (three LLM roles plus two local tools) wrapped in a **harness** that bounds its latency, cost and failure modes. The UI's Architecture tab draws the same picture with live models, thresholds, prompt versions and breaker state from `/stats`.

```text
POST /score ─▶ HARNESS ───────────────────────────────────────────────────────────────────────
               admission (>MAX_INFLIGHT_REQUESTS → 503) · trace_id · exact-duplicate check
               ┌─ AGENT ───────────────────────────────────────────────────────────────────┐
               │ extract  ×3 fields in parallel          FAST_MODEL    (1 call per field)  │
               │ embed    all claims, one encode call    MiniLM, CPU thread pool           │
               │ search   top-k, one matmul vs. the corpus matrix built at startup         │
               │ judge    relevance ×field ∥ coverage ×field   JUDGE_MODEL (batched)       │
               └───────────────────────────────────────────────────────────────────────────┘
               aggregate: per claim novelty × relevance → field mean → submission mean
               ▼
               ScoreResult + meta {trace_id, total_latency_ms, total_cost, llm_calls,
                                   cache_hits, degraded, spans[]}  → logs/traces.jsonl, /stats

Around every LLM call: LRU → disk cache, in-flight de-dup, budget cap, circuit breaker,
semaphore(8), tenacity retries (Retry-After), OpenRouter model fallbacks, Pydantic + 1 repair.

backend/prompts/*.md   versioned agent prompts      backend/.cache/  hashed LLM responses
backend/corpus.json    comparison corpus (flock + atomic writes)
```

The scoring pipeline:

1. Extract atomic claims for each populated review field, **one fast-model call per field, all three concurrently**.
2. Embed every new claim in **one** encode call on a thread-pool executor. Corpus claims were embedded once at startup into one normalized matrix.
3. Retrieve each claim's top-k (`ENTAILMENT_TOP_K`, default 3) same-field neighbours with a single matmul. If the nearest is at or above `HIGH_THRESHOLD`, the claim is covered; at or below `LOW_THRESHOLD`, novel. Otherwise the coverage judge compares it with every retrieved neighbour above `LOW_THRESHOLD` and answers `full`, `partial` or `none`, which earn novelty 0, `PARTIAL_NOVELTY_CREDIT` (0.5) or 1.
4. Judge every claim's relevance to the reference product and field intent on a graded rubric.
5. Steps 3 and 4 are batched: **one relevance call and at most one coverage call per field**, all running concurrently. A submission costs at most 9 LLM calls (3 extract + 3 relevance + ≤3 coverage), and wall time is about two model round-trips.
6. Field score = mean over claims of novelty × relevance; submission score = mean over populated fields.

## Design decisions

Novelty and relevance use multiplication, **per claim**. Relevance is a direct gate: a novel claim with relevance 0 receives 0, and a relevant but covered claim also receives 0. Gating per claim (rather than multiplying field averages) stops a covered on-topic claim from lending relevance to a novel off-topic claim in the same field. A geometric mean would soften the relevance penalty and could let unrelated novelty earn a noticeable score.

The relevance rubric states explicitly that a claim does not need to appear in the reference description. The earlier prompt scored specific, genuinely new product details as 0 because they were "not mentioned", which penalised exactly what the score should reward.

Ambiguous claims are judged against the top-k neighbours, not just the nearest. Embedding rank does not always put the true paraphrase first, for example "cumbersome on a phone" versus "mobile experience is cumbersome". The `partial` verdict gives credit for a new concrete detail inside an otherwise known observation.

`HIGH_THRESHOLD` is `0.75`. With MiniLM, claims that merely share a topic ("release notes…") reach 0.65–0.72 similarity, so the old 0.65 cut-off auto-marked genuinely new claims as covered. Batching makes judging a few more claims almost free.

The coverage prompt (v4) says explicitly that a *broader* claim about the same feature area is not coverage. Without that, the judge called specific new gaps "partial" whenever the corpus had a vague claim such as "reporting could be better".

On the 25-case set the separation margin went from −0.083 (original) to +0.451, with ROC-AUC 1.000 (see `reports/eval.md`). It is still a small dataset, not broad calibration.

When the comparison corpus is empty, an extractable claim is treated as novel because there is no comparison evidence; relevance still gates its score. An exact duplicate receives 0 without an LLM call. The form has an opt-in to add a submission after scoring, only when it meets `CORPUS_ACCEPTANCE_THRESHOLD` (default `0.60`). The in-memory index is updated incrementally, so the next request sees it.

## Prompts

All agent prompts live in `backend/prompts/` as Markdown: `extract_claims.md`, `judge_relevance.md`, `judge_coverage.md`, `generate_corpus.md`, and `field_intents.md`. Each file has front matter (`name`, `version`), a `# System` section with the static instructions, and a `# User` section. The user section is a `string.Template` that places the reference text first and the user's text last, which keeps the static prefix cacheable upstream. `backend/prompts/__init__.py` loads them into constants such as `JUDGE_COVERAGE`, whose `PROMPT_VERSION` is `judge_coverage@4`. **Bump `version` whenever you edit a prompt**: the version is part of the response-cache key.

## Production harness

- **Async and latency.** `AsyncOpenAI`; per-field extraction and per-field judge calls run concurrently with `asyncio.gather`; one global `asyncio.Semaphore(LLM_MAX_CONCURRENCY=8)` wraps upstream calls. Embeddings run through `run_in_executor` on a dedicated thread, one encode call per submission. Nearest neighbours are one matmul against the startup matrix.
- **Retries.** `tenacity`, max 3 attempts, on timeouts, connection errors, 429 and 5xx. The wait is exponential backoff plus jitter, or the server's `Retry-After` / `retry-after-ms` (capped at `LLM_MAX_RETRY_AFTER_SECONDS`). Other 4xx errors are not retried.
- **Model fallbacks.** `FAST_MODEL_FALLBACKS` / `JUDGE_MODEL_FALLBACKS` (comma-separated) are sent as `extra_body={"models": [...]}`, so OpenRouter fails over server-side. The model that actually served each response is logged (`llm_call … served_model=…`), recorded on its span, and counted in `/stats`.
- **Validation.** Every output is parsed with Pydantic, and batch outputs are also checked for exactly one result per id. A failure triggers exactly one re-ask that includes the validation error.
- **Circuit breaker and budget, then degraded mode.** Three consecutive failed LLM calls open the breaker for `BREAKER_COOLDOWN_SECONDS`, and a single half-open probe then decides. Spend reaching `LLM_BUDGET_USD` also stops upstream calls. Either way, the affected stage falls back to **embedding-only scoring**:
  - extraction splits sentences;
  - the ambiguous band gets partial credit;
  - relevance is 1 if the claim's cosine similarity to the reference text is at least `DEGRADED_RELEVANCE_THRESHOLD` (0.10), else 0.

  The response is still `200`, with `degraded: true` and a `degraded_reason`, and is never added to the corpus. The per-claim novelty × relevance aggregation is unchanged.
- **Cost and usage.** Each response's `usage` is read, including `prompt_tokens`, `completion_tokens`, `cost` (OpenRouter usage accounting) and `prompt_tokens_details.cached_tokens`. When cost is not reported, it is estimated from the configured rates for the requested model.
- **Tracing.** A contextvars span tracer gives each request a `trace_id` (from `x-request-id` or generated). It records spans for `dedupe`, `extract` (per field), `embed`, `search`, `relevance` and `entail` (per field), `aggregate` and each upstream `llm.call`. Every span carries `duration_ms`, tokens, `cost_usd`, `cache_hit` and `served_model`. Spans are returned in `meta.spans` and appended, one line per span, to `logs/traces.jsonl`.
- **`GET /stats`.** Request count, p50/p95/p99 latency, total cost, cache hit rate, degraded count, outcomes, shed requests, retries, served models, breaker state, embedding-cache stats and corpus size.
- **Cache correctness.** The key is `sha256(model, prompt_version, temperature, schema_hash, messages)`. An in-memory LRU (`LLM_MEMORY_CACHE_SIZE`) sits in front of the atomic disk cache. Concurrent identical prompts share one upstream call. Embeddings are cached by `sha256(text)`. `CACHE_ENABLED=false` turns all of this off, which the load test's cold phase uses.
- **Admission control.** Beyond `MAX_INFLIGHT_REQUESTS`, requests get `503` with `Retry-After`.
- **Safe corpus writes.** Read-modify-write under an exclusive `flock`, then temp file and `os.replace`.

Single-process assumption: `/stats`, the circuit breaker, the semaphore and the in-memory index are per process. Running several uvicorn workers keeps the corpus file safe, but each worker's index only sees its own appends until restart.

Before scoring meaningful submissions, generate the corpus. Without `backend/corpus.json`, new claims have no comparison baseline and are treated as novel.

## Configuration

Your `.env` should contain an OpenRouter key and, optionally, model and threshold overrides:

```dotenv
OPENROUTER_API_KEY=your_openrouter_key
FAST_MODEL=google/gemini-2.5-flash-lite
JUDGE_MODEL=google/gemini-2.5-flash
FAST_MODEL_FALLBACKS=            # comma-separated, sent as OpenRouter extra_body.models
JUDGE_MODEL_FALLBACKS=
HIGH_THRESHOLD=0.75
LOW_THRESHOLD=0.35
CORPUS_ACCEPTANCE_THRESHOLD=0.60
ENTAILMENT_TOP_K=3
PARTIAL_NOVELTY_CREDIT=0.5
LLM_MAX_CONCURRENCY=8
LLM_MAX_ATTEMPTS=3
MAX_INFLIGHT_REQUESTS=32
BREAKER_FAILURE_THRESHOLD=3
BREAKER_COOLDOWN_SECONDS=30
# LLM_BUDGET_USD=1.00            # optional lifetime spend cap per process → degraded mode
DEGRADED_RELEVANCE_THRESHOLD=0.10
CACHE_ENABLED=true
LLM_MEMORY_CACHE_SIZE=1024
EMBEDDING_CACHE_SIZE=4096
TRACE_LOG_PATH=logs/traces.jsonl
```

The API key is loaded as a `SecretStr`, so it never appears in settings `repr`, `str` or `model_dump` output.

Never commit `.env`. It is already ignored by Git.

The reference description is deliberately a short, editable Python string in `backend/reference.py`. Replace it with the product context you want reviewers to discuss, keeping it at 100 words or fewer.

## Run locally

Fresh checkout quickstart:

```bash
make setup
```

Add your `OPENROUTER_API_KEY` to `.env`, then generate the comparison corpus (this makes paid model calls):

```bash
make gen-corpus
```

Start the frontend and API together:

```bash
make dev
```

Visit `http://localhost:3000`, enter the three review fields, and submit. Claim cards show novelty status, nearest match text and similarity, relevance score and reason, plus an entailment reason when the judge was used. The score panel displays request latency and estimated model cost.

`make dev` starts the API and frontend. If you prefer separate terminals, use:

```bash
.venv/bin/uvicorn backend.main:app --reload
```

```bash
npm --prefix frontend run dev
```

## Generate the comparison corpus

With `OPENROUTER_API_KEY` configured and after reviewing the reference description, run:

```bash
source .venv/bin/activate
python -m backend.data_gen
```

The command requests 50 varied synthetic reviews with their claims and saves them to `backend/corpus.json`. It is never run automatically on startup or during the default tests. Responses are cached and the command prints estimated token use and cost. Run `make smoke` and `make eval` for additional explicit live API checks; both also print their usage estimates.

## Test the pipeline

```bash
make test
curl http://localhost:8000/health
```

Expected output is `51 passed`. Tests use hand-written LLM response fixtures (or a fake upstream for the client tests), with the real local Sentence Transformer embeddings, retrieval, batching and scoring math.

- **Scoring:** the scoring cases, adversarial examples, partial credit, top-k judging, per-claim gating, per-field batching and concurrent extraction.
- **Prompts and cache:** prompt loading and ordering, and cache-key composition, the memory LRU, the disk cache and the cache-disable flag.
- **Upstream reliability:** semaphore bounds, retries on 429, 5xx and timeouts, the Retry-After wait, non-retry of 4xx, OpenRouter fallbacks, served model and usage accounting, repair re-asks, breaker transitions and the budget cap.
- **Degraded mode, corpus and API:** degraded scoring (including off-topic rejection), concurrent corpus appends, the single-matrix search, the trace JSONL, `/stats`, overload shedding and concurrent API requests. They do not call OpenRouter. The first run downloads the embedding weights if they are not cached locally.

Run the evidence scripts explicitly when you want to use OpenRouter:

```bash
make smoke
make eval
.venv/bin/python -m scripts.corpus_stats
```

`make eval` writes the per-case and aggregate results to `reports/eval.json` and `reports/eval.md`.

### Load test

```bash
make load                                   # cold + warm, concurrency 1/5/10, 20 requests each
.venv/bin/python -m scripts.load_test --warm-only   # no paid cold phase
```

The script starts its own API servers, so no running `make dev` is needed. The cold phase uses `CACHE_ENABLED=false`: no response cache, no de-dup and no embedding cache. The warm phase runs with caches on, primed by one unmeasured pass. Both use 20 labelled submissions (4 per eval category) and write `reports/load.md`.

Live spend is capped at `--cap` (default $0.50). The script stops dispatching once spend plus the worst case for in-flight requests would pass the cap. It also passes the remaining budget to the server as `LLM_BUDGET_USD`, so the server degrades rather than overspends.

Measured on a laptop CPU (`reports/load.md`):

| Phase | Concurrency | p50 | p95 | Errors | Cost / request |
| --- | ---: | ---: | ---: | ---: | ---: |
| cold | 1 | 3.6 s | 13.9 s | 0% | $0.0018 |
| cold | 5 | 6.5 s | 10.4 s | 0% | $0.0017 |
| cold | 10 | 12.8 s | 16.7 s | 0% | $0.0018 |
| warm | 1 | 13 ms | 22 ms | 0% | $0 |
| warm | 5 | 58 ms | 73 ms | 0% | $0 |
| warm | 10 | 101 ms | 109 ms | 0% | $0 |

The whole run cost $0.113, with no degraded responses and no retries. Traces show where cold time goes. Each upstream call takes about 1.4 s (p50) at every concurrency level, and a cold request is two model round-trips (extract, then judges). The growth with concurrency is time queued at the global `LLM_MAX_CONCURRENCY=8` semaphore: queue p50 is 0 ms at c=1, 1.6 s at c=5 and 5.0 s at c=10, since each request makes about 7 calls. Raise the limit if your OpenRouter rate limits allow it. The cold c=1 p95 comes from one upstream judge call that took 11.7 s on its first attempt; the harness does not hedge slow requests.

## Limitations

- Novelty is not truthfulness; a fabricated claim can be novel and relevant.
- Synthetic corpus content comes from the same model family used for extraction, which can introduce shared blind spots.
- Relevance and coverage depend on an LLM judge and can reflect model bias or inconsistent judgments. The judge sometimes calls a close paraphrase `partial` when it only adds wording, which lets some paraphrases earn half credit (the worst eval paraphrase scores 0.424).
- Degraded-mode relevance (embedding similarity to the reference text) is coarse. On the eval set it keeps about 80% of relevant claims and rejects about 80% of off-topic ones, so degraded scores are flagged as provisional and never enter the corpus.
- There is no hedging of slow upstream calls; one slow provider response sets the request's tail latency (see the load test).
- Thresholds were compared with a 25-case labeled set and are not robustly calibrated for every product or corpus.
- Partial credit is a fixed fraction, not a measure of how much is new.
- Harness state (`/stats`, breaker, in-memory index) is per process; see the single-process note above.
- `POST /corpus/regenerate` is unauthenticated and makes paid calls. Keep the API on a trusted network, or add auth before exposing it.

## Make targets

`make setup`, `make gen-corpus`, `make test`, `make eval`, `make smoke`, `make load`, and `make dev` cover installation, corpus creation, tests, evaluation, live smoke checks, load testing, and local development.
