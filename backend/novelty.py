"""Corpus-aware novelty scoring for review claims."""
import asyncio
import json
import uuid
from typing import Any
from .claims import extract_claims
from .config import Settings, get_settings
from .corpus import CorpusIndex
from .llm_client import LLMClient
from .reference import REFERENCE_PRODUCT_DESCRIPTION
from .schemas import Claim, ClaimAssessment, CorpusEntry, Coverage, CoverageBatchResponse, CoverageJudgment, FieldName, FieldScore, Neighbor, RelevanceBatchResponse, RelevanceJudgment, ScoreResult, Submission
from .telemetry import RequestTrace, current_trace, span

SCORING_MODE = "mean(novelty × relevance) per claim"
FIELD_INTENTS = {
    FieldName.WHAT_YOU_LIKE: "a concrete positive capability, benefit, or user experience of the product",
    FieldName.WHAT_YOU_DISLIKE: "a concrete limitation, frustration, missing capability, or improvement request",
    FieldName.PROBLEM_SOLVED: "a concrete problem, workflow, or outcome the product solves for its users",
}
RELEVANCE_SYSTEM = (
    "You are a relevance judge for product reviews. For each claim, rate its relevance to the reference product and to its review field.\n"
    "Rubric:\n"
    "1.0 - a specific statement about this product's use, capabilities, limitations, or outcomes that fits the field intent.\n"
    "0.75 - relevant to the product and field, but vague or generic.\n"
    "0.5 - about the product's domain but only loosely fits the field intent.\n"
    "0.25 - tangential: touches the domain but is mostly about something else.\n"
    "0.0 - gibberish, off-topic, about a different product, or keyword-stuffed text whose subject is not this product.\n"
    "A claim does NOT need to be mentioned in the reference description. Reviewers report specific features, edge cases, "
    "user groups, and workflows beyond it; those are relevant when they plausibly concern this product. Judge the claim's subject, not keyword overlap.\n"
    'Return JSON only as {"results":[{"id":"...","relevance_score":number,"reason":"one sentence"}]} with exactly one result per input id.'
)
COVERAGE_SYSTEM = (
    "You decide whether existing product-review claims already cover a candidate claim. For each item, compare the candidate with its numbered existing claims.\n"
    "full - an existing claim states the same underlying observation (a paraphrase, synonym, or more general version of it) and the candidate adds nothing material.\n"
    "partial - an existing claim covers the core observation, but the candidate adds a concrete new detail such as a specific mechanism, condition, audience, or consequence.\n"
    "none - no existing claim states the same observation. Claims that are merely on a related topic are not coverage.\n"
    'Return JSON only as {"results":[{"id":"...","coverage":"full|partial|none","matched_existing":number|null,"reason":"one sentence"}]} '
    "with exactly one result per input id. matched_existing is the 1-based number of the closest existing claim, or null for none."
)


def _expect_ids(expected: set[str]):
    def check(data: RelevanceBatchResponse | CoverageBatchResponse) -> None:
        returned = [item.id for item in data.results]
        if set(returned) != expected or len(returned) != len(expected):
            raise ValueError(f"expected exactly one result for each id {sorted(expected)}, got {returned}")
    return check


async def judge_relevance(claims: list[Claim], llm: LLMClient, settings: Settings) -> list[RelevanceJudgment]:
    """One judge call for every claim. Batch ids are positional so identical submissions reuse the cache."""
    if not claims:
        return []
    items = [{"id": f"r{i}", "field": claim.field.value, "field_intent": FIELD_INTENTS[claim.field], "claim": claim.text} for i, claim in enumerate(claims)]
    data = await llm.complete_json(
        model=settings.judge_model,
        system=RELEVANCE_SYSTEM,
        prompt=f"Reference product:\n{REFERENCE_PRODUCT_DESCRIPTION}\n\nClaims:\n{json.dumps(items, indent=1)}",
        response_model=RelevanceBatchResponse,
        check=_expect_ids({item["id"] for item in items}),
        span_name="llm.judge_relevance",
    )
    by_id = {item.id: item for item in data.results}
    return [by_id[f"r{i}"] for i in range(len(claims))]


async def judge_coverage(items: list[tuple[Claim, list[tuple[Claim, float]]]], llm: LLMClient, settings: Settings) -> list[CoverageJudgment]:
    """One judge call covering every ambiguous claim against its top-k corpus neighbours."""
    if not items:
        return []
    payload = [{"id": f"e{i}", "candidate": claim.text, "existing": [{"n": n + 1, "text": neighbor.text} for n, (neighbor, _) in enumerate(neighbors)]} for i, (claim, neighbors) in enumerate(items)]

    def check(data: CoverageBatchResponse) -> None:
        _expect_ids({item["id"] for item in payload})(data)
        for result in data.results:
            limit = len(items[int(result.id[1:])][1])
            if result.matched_existing is not None and result.matched_existing > limit:
                raise ValueError(f"{result.id}: matched_existing {result.matched_existing} exceeds {limit} existing claims")

    data = await llm.complete_json(
        model=settings.judge_model,
        system=COVERAGE_SYSTEM,
        prompt=f"Items:\n{json.dumps(payload, indent=1)}",
        response_model=CoverageBatchResponse,
        check=check,
        span_name="llm.judge_coverage",
    )
    by_id = {item.id: item for item in data.results}
    return [by_id[f"e{i}"] for i in range(len(items))]


def _clamp(similarity: float) -> float:
    return max(-1.0, min(1.0, similarity))


def _field_scores(assessments: list[ClaimAssessment]) -> list[FieldScore]:
    fields = []
    for field in FieldName:
        items = [item for item in assessments if item.claim.field == field]
        if not items:
            fields.append(FieldScore(field=field, score=0.0, novelty_fraction=0.0, relevance_gate=0.0))
            continue
        # Gate per claim: a novel off-topic claim cannot borrow relevance from a covered on-topic one.
        score = sum(item.novelty_score * item.relevance_score for item in items) / len(items)
        fields.append(FieldScore(field=field, score=score, novelty_fraction=sum(item.novelty_score for item in items) / len(items), relevance_gate=sum(item.relevance_score for item in items) / len(items), claims=items))
    return fields


async def score_submission(submission: Submission, index: CorpusIndex, llm: LLMClient, *, settings: Settings | None = None, request_id: str | None = None, add_to_corpus: bool = False) -> ScoreResult:
    """Score a submission against the in-memory corpus index using batched LLM judgments."""
    trace = current_trace.get()
    token = None
    if trace is None:
        trace = RequestTrace(request_id)
        token = current_trace.set(trace)
    try:
        return await _score(submission, index, llm, settings or get_settings(), trace, add_to_corpus)
    finally:
        if token is not None:
            current_trace.reset(token)


async def _score(submission: Submission, index: CorpusIndex, llm: LLMClient, settings: Settings, trace: RequestTrace, add_to_corpus: bool) -> ScoreResult:
    with span("corpus.duplicate_check", corpus_entries=len(index.entries)):
        duplicate = index.find_duplicate(submission)
    if duplicate:
        fields = []
        for field in FieldName:
            raw_text = submission.field_text(field).strip()
            matching = next((claim for claim in duplicate.claims if claim.field == field), None)
            claim = Claim(id=f"duplicate-{field.value}", field=field, text=raw_text, source_submission_id=duplicate.id)
            assessment = ClaimAssessment(claim=claim, novelty_status="covered", novelty_score=0.0, relevance_score=1.0, relevance_reason="The exact submission already exists in the comparison corpus.", nearest_claim=matching, nearest_similarity=1.0 if matching else None)
            fields.append(FieldScore(field=field, score=0.0, novelty_fraction=0.0, relevance_gate=1.0, claims=[assessment] if raw_text else []))
        populated = [field for field in FieldName if submission.field_text(field).strip()]
        meta = _request_meta(trace, index, claims_per_field={field.value: int(field in populated) for field in FieldName}, decisions={"covered": len(populated), "partial": 0, "novel": 0, "ambiguous_judged": 0})
        return ScoreResult(submission_score=0.0, field_scores=fields, scoring_mode=SCORING_MODE, message="This submission matches an existing corpus entry.", meta=meta, add_to_corpus_requested=add_to_corpus)

    new_claims = await extract_claims(submission, llm)
    if not new_claims:
        meta = _request_meta(trace, index, claims_per_field={field.value: 0 for field in FieldName}, decisions={"covered": 0, "partial": 0, "novel": 0, "ambiguous_judged": 0})
        return ScoreResult(submission_score=0.0, field_scores=[FieldScore(field=field, score=0.0, novelty_fraction=0.0, relevance_gate=0.0) for field in FieldName], scoring_mode=SCORING_MODE, reason="no extractable claims", message="No product claims could be extracted from the submission.", meta=meta, add_to_corpus_requested=add_to_corpus)

    with span("embed.claims", claims=len(new_claims)):
        vectors = await asyncio.to_thread(index.embedder, [claim.text for claim in new_claims])
    k = settings.entailment_top_k
    with span("retrieval.knn", k=k, corpus_claims=index.claim_count):
        neighbor_lists = [index.neighbors(claim.field, vectors[i], k) for i, claim in enumerate(new_claims)]
    ambiguous: list[int] = []
    for i, neighbors in enumerate(neighbor_lists):
        if neighbors and settings.low_threshold < neighbors[0][1] < settings.high_threshold:
            ambiguous.append(i)
    coverage_items = [(new_claims[i], [(claim, sim) for claim, sim in neighbor_lists[i] if sim > settings.low_threshold]) for i in ambiguous]
    with span("judge.batch", claims=len(new_claims), ambiguous=len(ambiguous)):
        relevance, coverage = await asyncio.gather(judge_relevance(new_claims, llm, settings), judge_coverage(coverage_items, llm, settings))
    coverage_by_index = dict(zip(ambiguous, coverage))

    assessments = []
    for i, claim in enumerate(new_claims):
        neighbors = neighbor_lists[i]
        base: dict[str, Any] = {
            "claim": claim,
            "relevance_score": relevance[i].relevance_score,
            "relevance_reason": relevance[i].reason,
            "neighbors": [Neighbor(claim=item, similarity=_clamp(sim)) for item, sim in neighbors],
        }
        if neighbors:
            base.update(nearest_claim=neighbors[0][0], nearest_similarity=_clamp(neighbors[0][1]))
        if not neighbors or neighbors[0][1] <= settings.low_threshold:
            assessments.append(ClaimAssessment(**base, novelty_status="novel", novelty_score=1.0))
        elif neighbors[0][1] >= settings.high_threshold:
            assessments.append(ClaimAssessment(**base, novelty_status="covered", novelty_score=0.0))
        else:
            judgment = coverage_by_index[i]
            judged_neighbors = coverage_items[ambiguous.index(i)][1]
            if judgment.matched_existing is not None:
                matched, similarity = judged_neighbors[judgment.matched_existing - 1]
                base.update(nearest_claim=matched, nearest_similarity=_clamp(similarity))
            status, novelty = {Coverage.FULL: ("covered", 0.0), Coverage.PARTIAL: ("partial", settings.partial_novelty_credit), Coverage.NONE: ("novel", 1.0)}[judgment.coverage]
            assessments.append(ClaimAssessment(**base, novelty_status=status, novelty_score=novelty, entailment_judged=True, entailment_reason=judgment.reason))

    fields = _field_scores(assessments)
    active_fields = [item.score for item in fields if item.claims]
    submission_score = sum(active_fields) / len(active_fields)
    added_to_corpus = False
    if add_to_corpus and submission_score >= settings.corpus_acceptance_threshold:
        entry_id = str(uuid.uuid4())
        stored_claims = [claim.model_copy(update={"source_submission_id": entry_id}) for claim in new_claims]
        with span("corpus.append"):
            await index.add(CorpusEntry(id=entry_id, submission=submission, claims=stored_claims))
        added_to_corpus = True
    meta = _request_meta(
        trace, index,
        claims_per_field={field.value: sum(1 for claim in new_claims if claim.field == field) for field in FieldName},
        decisions={status: sum(1 for item in assessments if item.novelty_status == status) for status in ("covered", "partial", "novel")} | {"ambiguous_judged": len(ambiguous)},
        corpus_update="added" if added_to_corpus else "not_added",
    )
    return ScoreResult(submission_score=submission_score, field_scores=fields, scoring_mode=SCORING_MODE, message="Each claim's novelty is multiplied by its relevance, so off-topic claims stay low-scoring.", meta=meta, add_to_corpus_requested=add_to_corpus, added_to_corpus=added_to_corpus)


STAGES = {"claim_extraction": "llm.extract_claims", "embeddings": "embed.claims", "retrieval": "retrieval.knn", "judging": "judge.batch", "corpus_append": "corpus.append"}


def _request_meta(trace: RequestTrace, index: CorpusIndex, **extra: Any) -> dict[str, Any]:
    spans = trace.sorted_spans()
    durations = {name: sum(item["duration_ms"] for item in spans if item["name"] == span_name) / 1000 for name, span_name in STAGES.items()}
    return {
        "request_id": trace.request_id,
        "stage_latency_seconds": {**durations, "total": trace.elapsed_seconds()},
        "llm_calls": int(trace.usage["calls"]),
        "llm_cache_hits": int(trace.usage["cache_hits"]),
        "prompt_tokens": int(trace.usage["prompt_tokens"]),
        "completion_tokens": int(trace.usage["completion_tokens"]),
        "estimated_cost_usd": trace.usage["estimated_cost_usd"],
        "corpus_entries": len(index.entries),
        "trace": spans,
        **extra,
    }
