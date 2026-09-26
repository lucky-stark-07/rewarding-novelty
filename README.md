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
Next.js form
    │ POST /score
    ▼
FastAPI backend
    ├── Claim extraction (OpenRouter fast model)
    ├── Local CPU embeddings (Sentence Transformers)
    ├── Similarity search against local corpus claims
    ├── Entailment and relevance judging (OpenRouter judge model)
    └── Field and submission-score aggregation
    ▼
ScoreResult: overall score + field scores + claim-level explanations

Local JSON files
    ├── backend/corpus.json         generated comparison submissions
    └── backend/.cache/             hashed OpenRouter responses; avoids repeat spend
```

The intended scoring pipeline is:

1. Extract atomic claims for each of the three review fields.
2. Embed each claim locally on CPU.
3. Compare a new claim with corpus claims using cosine similarity: above `HIGH_THRESHOLD` is covered, below `LOW_THRESHOLD` is novel, and the middle band is checked for entailment by the judge model.
4. Score each claim's relevance to the fixed reference content and the field's intent.
5. Multiply field novelty by relevance, then average populated fields into the final 0.0–1.0 submission score.

## Design decisions

Novelty and relevance use multiplication. This makes relevance a direct gate: a novel claim with relevance 0 receives 0, while a relevant but covered claim also receives 0. A geometric mean would soften the relevance penalty and could let unrelated novelty earn a noticeable score, which conflicts with the challenge. When the comparison corpus is empty, an extractable claim is treated as novel because there is no comparison evidence; relevance still gates its score. An exact duplicate submission receives 0 without an LLM call. The threshold sweep suggested low `0.35` and high `0.65`; this band was selected on a small dataset and should not be mistaken for broad calibration. Corpus state affects future scores: the form has an opt-in to add a submission after scoring, only when it meets `CORPUS_ACCEPTANCE_THRESHOLD` (default `0.60`). First submissions against an empty corpus are therefore assessed as novel until a baseline is established.

## What is built today

Working end to end:

- Next.js review form and score-result view.
- FastAPI endpoints: `GET /health`, `POST /score`, `GET /corpus`, and `POST /corpus/regenerate`.
- Request validation through Pydantic schemas and CORS for local frontend development.
- OpenRouter-compatible JSON client with a disk cache keyed by model and prompt.
- Local JSON corpus storage, CPU-only embeddings, and cosine-similarity utilities.
- Opt-in synthetic corpus generation.
- Fifteen automated tests covering scoring cases, adversarial examples, API metadata, and input validation.

The live scoring path now:

- Extracts atomic claims with `FAST_MODEL` through OpenRouter.
- Embeds new and corpus claims locally, then classifies high- and low-similarity matches using the configured thresholds.
- Uses `JUDGE_MODEL` for relevance and the ambiguous similarity band.
- Combines average field novelty and relevance with multiplication.
- Returns the nearest corpus claim and similarity for every assessed claim.
- Returns request id, per-stage latency, LLM usage, cache hits, and estimated call cost in `meta`; the backend emits one JSON log line per score request.

Before scoring meaningful submissions, generate the corpus. Without `backend/corpus.json`, new claims have no comparison baseline and are treated as novel.

## Configuration

Your `.env` should contain an OpenRouter key and, optionally, model and threshold overrides:

```dotenv
OPENROUTER_API_KEY=your_openrouter_key
FAST_MODEL=google/gemini-2.5-flash-lite
JUDGE_MODEL=google/gemini-2.5-flash
FALLBACK_MODEL=
HIGH_THRESHOLD=0.65
LOW_THRESHOLD=0.35
CORPUS_ACCEPTANCE_THRESHOLD=0.60
```

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

Expected output is `15 passed`. Tests use hand-written LLM response fixtures and the real local Sentence Transformer embeddings and scoring math. They do not call OpenRouter. The first run downloads the embedding weights if they are not cached locally.

Run the evidence scripts explicitly when you want to use OpenRouter:

```bash
make smoke
make eval
.venv/bin/python -m scripts.corpus_stats
```

`make eval` writes the per-case and aggregate results to `reports/eval.json` and `reports/eval.md`.

## Limitations

- Novelty is not truthfulness; a fabricated claim can be novel and relevant.
- Synthetic corpus content comes from the same model family used for extraction, which can introduce shared blind spots.
- Relevance and entailment depend on an LLM judge and can reflect model bias or inconsistent judgments.
- Thresholds were compared with a small labeled set and are not robustly calibrated for every product or corpus.
- Similarity is a retrieval heuristic; small new details inside an otherwise covered claim currently receive a binary covered/novel decision.

## Make targets

`make setup`, `make gen-corpus`, `make test`, `make eval`, `make smoke`, and `make dev` cover installation, corpus creation, tests, evaluation, live smoke checks, and local development.
