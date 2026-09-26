"""Corpus-aware novelty scoring for review claims."""
from collections.abc import Callable
from typing import Any
import time
import uuid
import numpy as np
from .claims import extract_claims
from .config import Settings, get_settings
from .corpus import CorpusStore
from .embeddings import cosine_sim, embed
from .llm_client import LLMClient
from .reference import REFERENCE_PRODUCT_DESCRIPTION
from .schemas import Claim, ClaimAssessment, CorpusEntry, EntailmentResponse, FieldName, FieldScore, RelevanceResponse, ScoreResult, Submission

FIELD_INTENTS = {
    FieldName.WHAT_YOU_LIKE: "a concrete positive capability, benefit, or user experience of the product",
    FieldName.WHAT_YOU_DISLIKE: "a concrete limitation, frustration, missing capability, or improvement request",
    FieldName.PROBLEM_SOLVED: "a concrete product-team problem, workflow, or outcome the product solves",
}

def _bounded_score(value: Any, *, label: str) -> float:
    try: score = float(value)
    except (TypeError, ValueError) as exc: raise ValueError(f"Judge response has no valid {label}.") from exc
    return max(0.0, min(1.0, score))

def _relevance(claim: Claim, client: LLMClient, settings: Settings) -> RelevanceResponse:
    return client.complete_json(model=settings.judge_model, system="You are a strict relevance judge. Return JSON only as {\"relevance_score\": number, \"reason\": \"one sentence\"}. Score 0 for gibberish, off-topic text, or claims unrelated to the product. Score 1 only for a specific claim directly relevant to the reference product and stated review field.", prompt=f"Reference product:\n{REFERENCE_PRODUCT_DESCRIPTION}\n\nReview field: {claim.field.value}\nField intent: {FIELD_INTENTS[claim.field]}\nClaim: {claim.text}", response_model=RelevanceResponse)

def _entailment(existing: Claim, candidate: Claim, client: LLMClient, settings: Settings) -> EntailmentResponse:
    return client.complete_json(model=settings.judge_model, system="You check whether an existing product-review claim semantically covers a candidate claim. Return JSON only as {\"covered\": true|false, \"reason\": \"one sentence\"}. Treat paraphrases and the same underlying product observation as covered; do not treat merely related claims as covered.", prompt=f"Existing claim: {existing.text}\nCandidate claim: {candidate.text}", response_model=EntailmentResponse)

def _combine(novelty: float, relevance: float) -> float:
    return novelty * relevance

def _score_claim(claim: Claim, corpus_claims: list[Claim], similarities: np.ndarray | None, client: LLMClient, settings: Settings) -> ClaimAssessment:
    relevance = _relevance(claim, client, settings)
    if not corpus_claims or similarities is None:
        return ClaimAssessment(claim=claim, novelty_status="novel", novelty_score=1.0, relevance_score=relevance.relevance_score, relevance_reason=relevance.reason)
    index = int(np.argmax(similarities))
    nearest_similarity, nearest_claim = float(similarities[index]), corpus_claims[index]
    if nearest_similarity >= settings.high_threshold: status, novelty = "covered", 0.0
    elif nearest_similarity <= settings.low_threshold: status, novelty = "novel", 1.0
    else:
        judgment = _entailment(nearest_claim, claim, client, settings)
        status, novelty = ("covered", 0.0) if judgment.covered else ("novel", 1.0)
        return ClaimAssessment(claim=claim, novelty_status=status, novelty_score=novelty, relevance_score=relevance.relevance_score, relevance_reason=relevance.reason, nearest_claim=nearest_claim, nearest_similarity=nearest_similarity, entailment_judged=True, entailment_reason=judgment.reason)
    return ClaimAssessment(claim=claim, novelty_status=status, novelty_score=novelty, relevance_score=relevance.relevance_score, relevance_reason=relevance.reason, nearest_claim=nearest_claim, nearest_similarity=nearest_similarity)

def score_submission(submission: Submission, corpus: CorpusStore | None = None, *, llm: LLMClient | None = None, embedder: Callable[[list[str]], np.ndarray] = embed, settings: Settings | None = None, request_id: str | None = None, add_to_corpus: bool = False) -> ScoreResult:
    """Score a submission using OpenRouter judgments and local corpus-vector search."""
    active_settings = settings or get_settings()
    total_start = time.perf_counter()
    store = corpus or CorpusStore(active_settings.corpus_path)
    stage_start = time.perf_counter()
    corpus_entries = store.list()
    corpus_load_seconds = time.perf_counter() - stage_start
    client = llm or LLMClient(active_settings)
    normalize = lambda value: " ".join(value.casefold().split())
    duplicate = next((entry for entry in corpus_entries if all(normalize(entry.submission.field_text(field)) == normalize(submission.field_text(field)) for field in FieldName)), None)
    if duplicate:
        fields = []
        for field in FieldName:
            raw_text = submission.field_text(field).strip()
            matching = next((claim for claim in duplicate.claims if claim.field == field), None)
            claim = Claim(id=f"duplicate-{field.value}", field=field, text=raw_text, source_submission_id=duplicate.id)
            assessment = ClaimAssessment(claim=claim, novelty_status="covered", novelty_score=0.0, relevance_score=1.0, relevance_reason="The exact submission already exists in the comparison corpus.", nearest_claim=matching, nearest_similarity=1.0 if matching else None)
            fields.append(FieldScore(field=field, score=0.0, novelty_fraction=0.0, relevance_gate=1.0, claims=[assessment] if raw_text else []))
        meta = _request_meta(request_id, client, {"claim_extraction": 0.0, "corpus_load": corpus_load_seconds, "embeddings": 0.0, "judging_and_aggregation": 0.0}, total_start)
        meta["claims_per_field"] = {field.value: 1 if submission.field_text(field).strip() else 0 for field in FieldName}
        meta["decisions"] = {"covered": sum(1 for field in FieldName if submission.field_text(field).strip()), "novel": 0, "ambiguous_judged": 0}
        return ScoreResult(submission_score=0.0, field_scores=fields, scoring_mode="novelty × relevance", message="This submission matches an existing corpus entry.", meta=meta, add_to_corpus_requested=add_to_corpus)
    stage_start = time.perf_counter()
    new_claims = extract_claims(submission, client)
    extraction_seconds = time.perf_counter() - stage_start
    if not new_claims:
        meta = _request_meta(request_id, client, {"claim_extraction": extraction_seconds, "corpus_load": corpus_load_seconds, "embeddings": 0.0, "judging_and_aggregation": 0.0}, total_start)
        meta["claims_per_field"] = {field.value: 0 for field in FieldName}
        meta["decisions"] = {"covered": 0, "novel": 0, "ambiguous_judged": 0}
        return ScoreResult(submission_score=0.0, field_scores=[FieldScore(field=field, score=0.0, novelty_fraction=0.0, relevance_gate=0.0) for field in FieldName], scoring_mode="novelty × relevance", reason="no extractable claims", message="No product claims could be extracted from the submission.", meta=meta, add_to_corpus_requested=add_to_corpus)
    corpus_claims = [claim for entry in corpus_entries for claim in entry.claims]
    similar_rows: list[np.ndarray | None] = [None] * len(new_claims)
    claims_by_field = {field: [claim for claim in corpus_claims if claim.field == field] for field in FieldName}
    stage_start = time.perf_counter()
    if corpus_claims:
        vectors = embedder([claim.text for claim in new_claims] + [claim.text for claim in corpus_claims])
        new_vectors, corpus_vectors = vectors[:len(new_claims)], vectors[len(new_claims):]
        corpus_offsets: dict[FieldName, list[int]] = {field: [] for field in FieldName}
        for offset, claim in enumerate(corpus_claims): corpus_offsets[claim.field].append(offset)
        for index, claim in enumerate(new_claims):
            offsets = corpus_offsets[claim.field]
            if offsets:
                row = cosine_sim(new_vectors[index:index + 1], corpus_vectors[offsets])[0]
                similar_rows[index] = row
    embedding_seconds = time.perf_counter() - stage_start
    stage_start = time.perf_counter()
    assessments = [_score_claim(claim, claims_by_field[claim.field], similar_rows[index], client, active_settings) for index, claim in enumerate(new_claims)]
    fields: list[FieldScore] = []
    for field in FieldName:
        items = [item for item in assessments if item.claim.field == field]
        if not items:
            fields.append(FieldScore(field=field, score=0.0, novelty_fraction=0.0, relevance_gate=0.0))
            continue
        novelty = sum(item.novelty_score for item in items) / len(items)
        relevance = sum(item.relevance_score for item in items) / len(items)
        fields.append(FieldScore(field=field, score=_combine(novelty, relevance), novelty_fraction=novelty, relevance_gate=relevance, claims=items))
    active_fields = [item.score for item in fields if item.claims]
    submission_score = sum(active_fields) / len(active_fields)
    added_to_corpus = False
    if add_to_corpus and submission_score >= active_settings.corpus_acceptance_threshold:
        entry_id = str(uuid.uuid4())
        stored_claims = [claim.model_copy(update={"source_submission_id": entry_id}) for claim in new_claims]
        store.replace([*corpus_entries, CorpusEntry(id=entry_id, submission=submission, claims=stored_claims)])
        added_to_corpus = True
    meta = _request_meta(request_id, client, {"claim_extraction": extraction_seconds, "corpus_load": corpus_load_seconds, "embeddings": embedding_seconds, "judging_and_aggregation": time.perf_counter() - stage_start}, total_start)
    meta["claims_per_field"] = {field.value: sum(1 for claim in new_claims if claim.field == field) for field in FieldName}
    meta["decisions"] = {"covered": sum(1 for item in assessments if item.novelty_status == "covered"), "novel": sum(1 for item in assessments if item.novelty_status == "novel"), "ambiguous_judged": sum(1 for item in assessments if item.entailment_judged)}
    meta["corpus_update"] = "added" if added_to_corpus else "not_added"
    return ScoreResult(submission_score=submission_score, field_scores=fields, scoring_mode="novelty × relevance", message="Score multiplies claim novelty by relevance so off-topic claims remain low-scoring.", meta=meta, add_to_corpus_requested=add_to_corpus, added_to_corpus=added_to_corpus)


def _request_meta(request_id: str | None, client: LLMClient, stages: dict[str, float], total_start: float) -> dict:
    metrics = getattr(client, "metrics", {})
    return {
        "request_id": request_id,
        "stage_latency_seconds": {**stages, "total": time.perf_counter() - total_start},
        "llm_calls": metrics.get("calls", 0),
        "llm_cache_hits": metrics.get("cache_hits", 0),
        "prompt_tokens": metrics.get("prompt_tokens", 0),
        "completion_tokens": metrics.get("completion_tokens", 0),
        "estimated_cost_usd": metrics.get("estimated_cost_usd", 0.0),
    }
