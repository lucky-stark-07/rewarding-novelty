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

```text
Next.js form ── POST /score ──▶ FastAPI (async, single process)
                                  │  admission control: >MAX_INFLIGHT_REQUESTS → 503 Retry-After
                                  ├── exact-duplicate lookup (O(1), no LLM)
                                  ├── claim extraction ─────────────┐
                                  ├── embed new claims (LRU cache)  │  LLMClient (shared)
                                  ├── top-k retrieval vs. in-memory │   · semaphore (LLM_MAX_CONCURRENCY)
                                  │   corpus matrix built at startup│   · disk cache + in-flight de-dup
                                  ├── ┌ relevance judge (1 batch) ──┤   · retries with jittered backoff
                                  │   └ coverage judge  (1 batch) ──┤   · circuit breaker → 503
                                  │     (run concurrently)          │   · usage + cost accounting
                                  └── per-claim novelty × relevance ┘
                                  ▼
ScoreResult + meta.trace (spans)          GET /stats: latency percentiles, outcomes, cache hit
                                          rates, breaker state, corpus size

Local files
    ├── backend/corpus.json   comparison submissions (atomic writes under an exclusive flock)
    └── backend/.cache/       hashed OpenRouter responses; avoids repeat spend
```

The scoring pipeline:

1. Extract atomic claims for each of the three review fields (one fast-model call).
2. Embed each new claim locally on CPU. Corpus claims were embedded once at startup.
3. Retrieve each claim's top-k (`ENTAILMENT_TOP_K`, default 3) nearest corpus claims in the same field. If the nearest is at or above `HIGH_THRESHOLD`, the claim is covered; at or below `LOW_THRESHOLD`, novel. Otherwise the judge compares it with every retrieved neighbour above `LOW_THRESHOLD` and answers `full`, `partial` or `none`, which earn novelty 0, `PARTIAL_NOVELTY_CREDIT` (0.5) or 1.
4. Judge every claim's relevance to the reference product and field intent on a graded rubric.
5. Steps 3 and 4 are one batched judge call each, run concurrently, so a submission costs at most three LLM calls however many claims it has.
6. Field score = mean over claims of novelty × relevance; submission score = mean over populated fields.

## Design decisions

Novelty and relevance use multiplication, **per claim**. Relevance is a direct gate: a novel claim with relevance 0 receives 0, and a relevant but covered claim also receives 0. Gating per claim (rather than multiplying field averages) stops a covered on-topic claim from lending relevance to a novel off-topic claim in the same field. A geometric mean would soften the relevance penalty and could let unrelated novelty earn a noticeable score.

The relevance rubric states explicitly that a claim does not need to appear in the reference description. The earlier prompt scored specific, genuinely new product details as 0 because they were "not mentioned", which penalised exactly what the score should reward.

Ambiguous claims are judged against the top-k neighbours, not just the nearest. Embedding rank does not always put the true paraphrase first, for example "cumbersome on a phone" versus "mobile experience is cumbersome". The `partial` verdict gives credit for a new concrete detail inside an otherwise known observation.

`HIGH_THRESHOLD` is `0.75`. With MiniLM, claims that merely share a topic ("release notes…") reach 0.65–0.72 similarity, so the old 0.65 cut-off auto-marked genuinely new claims as covered. Batching makes judging a few more claims almost free. On the 25-case set this moved the separation margin from −0.083 to +0.250 and ROC-AUC from 0.960 to 1.000. It is still a small dataset, not broad calibration.

When the comparison corpus is empty, an extractable claim is treated as novel because there is no comparison evidence; relevance still gates its score. An exact duplicate receives 0 without an LLM call. The form has an opt-in to add a submission after scoring, only when it meets `CORPUS_ACCEPTANCE_THRESHOLD` (default `0.60`). The in-memory index is updated incrementally, so the next request sees it.

## Production harness

- **Async end to end.** `AsyncOpenAI` for upstream calls; embeddings and file I/O run in worker threads so the event loop never blocks.
- **Concurrency limits.** A semaphore caps concurrent upstream calls (`LLM_MAX_CONCURRENCY`). Requests beyond `MAX_INFLIGHT_REQUESTS` are shed with `503` and `Retry-After`.
- **Caching.** The on-disk response cache is written atomically. Concurrent identical prompts share a single upstream call (in-flight de-duplication). A bounded LRU caches claim embeddings (`EMBEDDING_CACHE_SIZE`). Batch ids are positional, so identical submissions hit the cache.
- **Circuit breaker.** After `BREAKER_FAILURE_THRESHOLD` consecutive upstream failures (network, 429, 5xx after retries), calls fail fast with `503` for `BREAKER_COOLDOWN_SECONDS`. A single half-open probe then decides whether to close. Client errors (4xx) and a missing API key never trip it.
- **Structured-output repair.** Every batch response is validated for schema and for exactly one result per id. A failure triggers one repair prompt, then the fallback model if one is configured. Upstream failures return `502` with a generic message.
- **Tracing.** Each response carries `meta.trace`: spans for duplicate check, extraction, embedding, retrieval, each judge call and each upstream attempt, with model, cache hit, tokens, semaphore queue time and retry attempt. The UI shows this as a collapsible waterfall under the score. The JSON log line per request omits the trace.
- **`GET /stats`.** Request outcomes, in-flight and shed counts, rolling p50/p95/p99 latency, mean per-stage time, LLM calls, cache hit rate, de-duplicated calls, tokens, cost, breaker state, embedding-cache stats and corpus size.
- **Safe corpus writes.** Read-modify-write under an exclusive `flock`, then temp file and `os.replace`. Concurrent appends from any process cannot lose entries or leave a torn file.
- **Load test.** `make load` (see below).

Single-process assumption: `/stats`, the circuit breaker, the semaphore and the in-memory index are per process. Running several uvicorn workers keeps the corpus file safe, but each worker's index only sees its own appends until restart.

Before scoring meaningful submissions, generate the corpus. Without `backend/corpus.json`, new claims have no comparison baseline and are treated as novel.

## Configuration

Your `.env` should contain an OpenRouter key and, optionally, model and threshold overrides:

```dotenv
OPENROUTER_API_KEY=your_openrouter_key
FAST_MODEL=google/gemini-2.5-flash-lite
JUDGE_MODEL=google/gemini-2.5-flash
FALLBACK_MODEL=
HIGH_THRESHOLD=0.75
LOW_THRESHOLD=0.35
CORPUS_ACCEPTANCE_THRESHOLD=0.60
ENTAILMENT_TOP_K=3
PARTIAL_NOVELTY_CREDIT=0.5
LLM_MAX_CONCURRENCY=8
MAX_INFLIGHT_REQUESTS=32
BREAKER_FAILURE_THRESHOLD=5
BREAKER_COOLDOWN_SECONDS=30
EMBEDDING_CACHE_SIZE=4096
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

Expected output is `37 passed`. Tests use hand-written LLM response fixtures (or a fake upstream for the client tests), with the real local Sentence Transformer embeddings, retrieval, batching and scoring math. They cover the scoring cases, adversarial examples, partial credit, top-k judging and per-claim gating. On the harness side they cover semaphore bounds, in-flight de-duplication, repair prompts, circuit-breaker transitions, secret redaction, concurrent corpus appends, overload shedding, upstream error mapping, `/stats`, and concurrent API requests. They do not call OpenRouter. The first run downloads the embedding weights if they are not cached locally.

Run the evidence scripts explicitly when you want to use OpenRouter:

```bash
make smoke
make eval
.venv/bin/python -m scripts.corpus_stats
```

`make eval` writes the per-case and aggregate results to `reports/eval.json` and `reports/eval.md`.

### Load test

With the API running (`make dev`), run:

```bash
make load                                     # 100 requests, 16 concurrent
.venv/bin/python -m scripts.load_test --requests 200 --concurrency 32
```

By default it cycles through the five fixture submissions, so after the first pass every model call is a cache hit, and the run measures the harness rather than model latency or spend. `--unique` makes every submission new, which means real, paid calls. It prints client-side throughput, latency percentiles and status counts, then the server's `/stats`.

A reference run on a laptop CPU with 200 requests at 32 concurrent: all 200 returned 200, at 46 req/s. In-flight de-duplication collapsed 122 concurrent identical prompts, so only 6 upstream calls were made. Server p50 was 17 ms; p95 was 3.8 s, from the first wave waiting on the upstream model. The breaker stayed closed.

## Limitations

- Novelty is not truthfulness; a fabricated claim can be novel and relevant.
- Synthetic corpus content comes from the same model family used for extraction, which can introduce shared blind spots.
- Relevance and coverage depend on an LLM judge and can reflect model bias or inconsistent judgments. The judge sometimes calls a close paraphrase `partial` when it only adds wording, which lets some paraphrases earn half credit (the worst eval paraphrase scores 0.417).
- Thresholds were compared with a 25-case labeled set and are not robustly calibrated for every product or corpus.
- Partial credit is a fixed fraction, not a measure of how much is new.
- Harness state (`/stats`, breaker, in-memory index) is per process; see the single-process note above.
- `POST /corpus/regenerate` is unauthenticated and makes paid calls. Keep the API on a trusted network, or add auth before exposing it.

## Make targets

`make setup`, `make gen-corpus`, `make test`, `make eval`, `make smoke`, `make load`, and `make dev` cover installation, corpus creation, tests, evaluation, live smoke checks, load testing, and local development.
