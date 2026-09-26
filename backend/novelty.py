"""Corpus-aware novelty scoring for review claims."""
import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
import numpy as np
from .claims import extract_claims
from .config import Settings, get_settings
from .corpus import CorpusIndex
from .guardrails import mask_submission, moderate, warnings_for
from .llm_client import LLM_UNAVAILABLE, LLMClient
from .prompts import FIELD_INTENTS, JUDGE_COVERAGE, JUDGE_RELEVANCE
from .reference import REFERENCE_PRODUCT_DESCRIPTION
from .schemas import Claim, ClaimAssessment, CorpusEntry, Coverage, CoverageBatchResponse, CoverageJudgment, FieldName, FieldScore, Neighbor, RelevanceBatchResponse, RelevanceJudgment, ScoreResult, Submission
from .telemetry import RequestTrace, current_trace, span

SCORING_MODE = "mean(novelty × relevance) per claim"
Neighbors = list[tuple[Claim, float]]


def _expect_ids(expected: set[str]):
    def check(data: RelevanceBatchResponse | CoverageBatchResponse) -> None:
        returned = [item.id for item in data.results]
        if set(returned) != expected or len(returned) != len(expected):
            raise ValueError(f"expected exactly one result for each id {sorted(expected)}, got {returned}")
    return check


async def judge_relevance(field: FieldName, claims: list[Claim], llm: LLMClient, settings: Settings) -> list[RelevanceJudgment]:
    """One judge call for all of a field's claims. Positional ids keep identical submissions cacheable."""
    if not claims:
        return []
    items = [{"id": f"r{i}", "claim": claim.text} for i, claim in enumerate(claims)]
    data = await llm.complete_json(
        JUDGE_RELEVANCE,
        model=settings.judge_model,
        variables={"reference": REFERENCE_PRODUCT_DESCRIPTION, "field": field.value, "field_intent": FIELD_INTENTS[field.value], "claims": json.dumps(items, indent=1)},
        response_model=RelevanceBatchResponse,
        check=_expect_ids({item["id"] for item in items}),
    )
    by_id = {item.id: item for item in data.results}
    return [by_id[f"r{i}"] for i in range(len(claims))]


async def judge_coverage(field: FieldName, items: list[tuple[Claim, Neighbors]], llm: LLMClient, settings: Settings) -> list[CoverageJudgment]:
    """One judge call for all of a field's ambiguous claims against their top-k corpus neighbours."""
    if not items:
        return []
    # Corpus text before the user's candidate, so user text comes last in the prompt.
    payload = [{"id": f"e{i}", "existing": [{"n": n + 1, "text": neighbor.text} for n, (neighbor, _) in enumerate(neighbors)], "candidate": claim.text} for i, (claim, neighbors) in enumerate(items)]

    def check(data: CoverageBatchResponse) -> None:
        _expect_ids({item["id"] for item in payload})(data)
        for result in data.results:
            limit = len(items[int(result.id[1:])][1])
            if result.matched_existing is not None and result.matched_existing > limit:
                raise ValueError(f"{result.id}: matched_existing {result.matched_existing} exceeds {limit} existing claims")

    data = await llm.complete_json(
        JUDGE_COVERAGE,
        model=settings.judge_model,
        variables={"field": field.value, "items": json.dumps(payload, indent=1)},
        response_model=CoverageBatchResponse,
        check=check,
    )
    by_id = {item.id: item for item in data.results}
    return [by_id[f"e{i}"] for i in range(len(items))]


def _clamp(similarity: float) -> float:
    return max(-1.0, min(1.0, similarity))


def _degrade(stage: str, exc: BaseException, attrs: dict[str, Any]) -> None:
    reason = f"{stage}:{type(exc).__name__}"
    attrs.update(degraded=True, degraded_reason=reason)
    if (trace := current_trace.get()) is not None:
        trace.degrade(reason)


async def _judge_field(field: FieldName, indices: list[int], claims: list[Claim], vectors: np.ndarray, neighbor_lists: list[Neighbors], ambiguous: set[int], index: CorpusIndex, llm: LLMClient, settings: Settings) -> tuple[dict[int, tuple[float, str]], dict[int, CoverageJudgment | None]]:
    """Relevance and coverage for one field, run concurrently. On LLM failure, fall back to
    embedding-only judgments for this field: relevance = similarity to the reference text
    passes a threshold; ambiguous-band coverage = partial."""
    field_claims = [claims[i] for i in indices]
    field_ambiguous = [i for i in indices if i in ambiguous]
    coverage_items = [(claims[i], [(c, s) for c, s in neighbor_lists[i] if s > settings.low_threshold]) for i in field_ambiguous]

    async def relevance() -> dict[int, tuple[float, str]]:
        with span("relevance", field=field.value, claims=len(field_claims)) as attrs:
            try:
                judged = await judge_relevance(field, field_claims, llm, settings)
                return {i: (item.relevance_score, item.reason) for i, item in zip(indices, judged)}
            except LLM_UNAVAILABLE as exc:
                _degrade("relevance", exc, attrs)
                if index.reference_vector is None:
                    return {i: (1.0, "Degraded: relevance not judged (no reference embedding).") for i in indices}
                similarity = vectors[indices] @ index.reference_vector
                return {i: (1.0 if s >= settings.degraded_relevance_threshold else 0.0, f"Degraded: embedding similarity to the reference text is {s:.2f} (threshold {settings.degraded_relevance_threshold:.2f}).") for i, s in zip(indices, similarity)}

    async def coverage() -> dict[int, CoverageJudgment | None]:
        if not coverage_items:
            return {}
        with span("entail", field=field.value, ambiguous=len(coverage_items), k=settings.entailment_top_k) as attrs:
            try:
                judged = await judge_coverage(field, coverage_items, llm, settings)
                return dict(zip(field_ambiguous, judged))
            except LLM_UNAVAILABLE as exc:
                _degrade("entail", exc, attrs)
                return {i: None for i in field_ambiguous}

    return await asyncio.gather(relevance(), coverage())


def _assess(claim: Claim, neighbors: Neighbors, relevance: tuple[float, str], judgment: CoverageJudgment | None, judged_neighbors: Neighbors | None, settings: Settings) -> ClaimAssessment:
    base: dict[str, Any] = {"claim": claim, "relevance_score": relevance[0], "relevance_reason": relevance[1], "neighbors": [Neighbor(claim=item, similarity=_clamp(sim)) for item, sim in neighbors]}
    if neighbors:
        base.update(nearest_claim=neighbors[0][0], nearest_similarity=_clamp(neighbors[0][1]))
    if not neighbors or neighbors[0][1] <= settings.low_threshold:
        return ClaimAssessment(**base, novelty_status="novel", novelty_score=1.0)
    if neighbors[0][1] >= settings.high_threshold:
        return ClaimAssessment(**base, novelty_status="covered", novelty_score=0.0)
    if judgment is None:
        return ClaimAssessment(**base, novelty_status="partial", novelty_score=settings.partial_novelty_credit, entailment_reason="Degraded: ambiguous similarity band was not judged; partial credit applied.")
    if judgment.matched_existing is not None and judged_neighbors:
        matched, similarity = judged_neighbors[judgment.matched_existing - 1]
        base.update(nearest_claim=matched, nearest_similarity=_clamp(similarity))
    status, novelty = {Coverage.FULL: ("covered", 0.0), Coverage.PARTIAL: ("partial", settings.partial_novelty_credit), Coverage.NONE: ("novel", 1.0)}[judgment.coverage]
    return ClaimAssessment(**base, novelty_status=status, novelty_score=novelty, entailment_judged=True, entailment_reason=judgment.reason)


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


async def score_submission(submission: Submission, index: CorpusIndex, llm: LLMClient, *, settings: Settings | None = None, request_id: str | None = None, add_to_corpus: bool = False, guard: LLMClient | None = None) -> ScoreResult:
    """Score a submission against the in-memory corpus index. Uses the active request trace, or opens one.

    Guardrails: secrets and PII are masked first, and nothing downstream (LLM calls, caches, corpus,
    logs, response) ever sees the original text. Moderation runs concurrently with scoring on the
    guard client; a block verdict replaces the result, and only an allow verdict permits storage."""
    active = settings or get_settings()
    trace = current_trace.get()
    token = None
    if trace is None:
        trace = RequestTrace(request_id)
        token = current_trace.set(trace)
    try:
        with span("guard.pii") as attrs:
            masked, counts = mask_submission(submission)
            attrs.update(masked=sum(counts.values()), types=",".join(sorted(counts)))
        if index.find_duplicate(masked):
            async def already_moderated() -> tuple[str, list[str], str]:
                return "allow", [], "Matches an existing corpus entry, which passed moderation when it was stored."
            moderation = asyncio.create_task(already_moderated())
        else:
            moderation = asyncio.create_task(moderate(masked, guard or llm, active))

        async def storage_allowed() -> bool:
            return (await moderation)[0] == "allow"

        try:
            result = await _score(masked, index, llm, active, trace, add_to_corpus, storage_allowed)
        except BaseException:
            moderation.cancel()
            raise
        verdict, categories, reason = await moderation
        # The UI labels similarity bands from these, so they always match the thresholds actually used.
        result.meta["thresholds"] = {"low": active.low_threshold, "high": active.high_threshold}
        guardrails = {"masked": dict(counts), "moderation": verdict, "categories": categories, "moderation_reason": reason, "warnings": warnings_for(counts)}
        if verdict == "block":
            return _result(trace, index, submission_score=0.0, field_scores=[FieldScore(field=field, score=0.0, novelty_fraction=0.0, relevance_gate=0.0) for field in FieldName], scoring_mode=SCORING_MODE, reason="content_policy",
                           message=f"Blocked by the content policy ({', '.join(categories) or 'unsafe content'}). The review was not scored or stored.", add_to_corpus_requested=add_to_corpus, guardrails=guardrails)
        if verdict != "allow":
            guardrails["warnings"].append("This review was scored but will not be added to the corpus" + (" because it was flagged by moderation." if verdict == "flag" else " because moderation could not be completed."))
        return result.model_copy(update={"guardrails": guardrails})
    finally:
        if token is not None:
            current_trace.reset(token)


def _result(trace: RequestTrace, index: CorpusIndex, **fields: Any) -> ScoreResult:
    extra = fields.pop("meta_extra", {})
    reason = "; ".join(trace.degraded_reasons) or None
    return ScoreResult(**fields, degraded=trace.degraded, degraded_reason=reason, meta=request_meta(trace, index, **extra))


async def _score(submission: Submission, index: CorpusIndex, llm: LLMClient, settings: Settings, trace: RequestTrace, add_to_corpus: bool, storage_allowed: Callable[[], Awaitable[bool]]) -> ScoreResult:
    with span("dedupe", corpus_entries=len(index.entries)):
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
        return _result(trace, index, submission_score=0.0, field_scores=fields, scoring_mode=SCORING_MODE, message="This submission matches an existing corpus entry.", add_to_corpus_requested=add_to_corpus,
                       meta_extra={"claims_per_field": {field.value: int(field in populated) for field in FieldName}, "decisions": {"covered": len(populated), "partial": 0, "novel": 0, "ambiguous_judged": 0}})

    claims = await extract_claims(submission, llm, settings)
    if not claims:
        return _result(trace, index, submission_score=0.0, field_scores=[FieldScore(field=field, score=0.0, novelty_fraction=0.0, relevance_gate=0.0) for field in FieldName], scoring_mode=SCORING_MODE, reason="no extractable claims", message="No product claims could be extracted from the submission.", add_to_corpus_requested=add_to_corpus,
                       meta_extra={"claims_per_field": {field.value: 0 for field in FieldName}, "decisions": {"covered": 0, "partial": 0, "novel": 0, "ambiguous_judged": 0}})

    with span("embed", claims=len(claims)):
        vectors = await index.embed([claim.text for claim in claims])
    with span("search", k=settings.entailment_top_k, corpus_claims=index.claim_count):
        neighbor_lists = index.search(vectors, [claim.field for claim in claims], settings.entailment_top_k)
    ambiguous = {i for i, neighbors in enumerate(neighbor_lists) if neighbors and settings.low_threshold < neighbors[0][1] < settings.high_threshold}

    fields_present = [field for field in FieldName if any(claim.field == field for claim in claims)]
    judged = await asyncio.gather(*(_judge_field(field, [i for i, claim in enumerate(claims) if claim.field == field], claims, vectors, neighbor_lists, ambiguous, index, llm, settings) for field in fields_present))
    relevance: dict[int, tuple[float, str]] = {}
    coverage: dict[int, CoverageJudgment | None] = {}
    for field_relevance, field_coverage in judged:
        relevance.update(field_relevance)
        coverage.update(field_coverage)

    with span("aggregate", claims=len(claims)) as attrs:
        assessments = [_assess(claim, neighbor_lists[i], relevance[i], coverage.get(i), [(c, s) for c, s in neighbor_lists[i] if s > settings.low_threshold] if i in ambiguous else None, settings) for i, claim in enumerate(claims)]
        fields = _field_scores(assessments)
        # Every field the reviewer filled in counts; one that yields no claims ("Could be better.") scores 0
        # instead of being dropped, so filler cannot raise the average.
        populated = {field for field in FieldName if submission.field_text(field).strip()}
        scored_fields = [item.score for item in fields if item.field in populated or item.claims]
        submission_score = sum(scored_fields) / len(scored_fields)
        attrs.update(submission_score=round(submission_score, 4), empty_fields=sorted(field.value for field in populated if not any(item.field == field and item.claims for item in fields)))

    added_to_corpus = False
    # Degraded judgments are provisional; never let them change the comparison baseline.
    if add_to_corpus and not trace.degraded and submission_score >= settings.corpus_acceptance_threshold and await storage_allowed():
        entry_id = str(uuid.uuid4())
        stored_claims = [claim.model_copy(update={"source_submission_id": entry_id}) for claim in claims]
        with span("corpus_append"):
            await index.add(CorpusEntry(id=entry_id, submission=submission, claims=stored_claims))
        added_to_corpus = True

    message = "Each claim's novelty is multiplied by its relevance, so off-topic claims stay low-scoring."
    if trace.degraded:
        message = "Scored in degraded mode (embedding similarity only, no LLM judge); treat this score as provisional."
    return _result(
        trace, index, submission_score=submission_score, field_scores=fields, scoring_mode=SCORING_MODE, message=message, add_to_corpus_requested=add_to_corpus, added_to_corpus=added_to_corpus,
        meta_extra={
            "claims_per_field": {field.value: sum(1 for claim in claims if claim.field == field) for field in FieldName},
            "decisions": {status: sum(1 for item in assessments if item.novelty_status == status) for status in ("covered", "partial", "novel")} | {"ambiguous_judged": sum(1 for item in assessments if item.entailment_judged)},
            "corpus_update": "added" if added_to_corpus else "not_added",
        },
    )


def request_meta(trace: RequestTrace, index: CorpusIndex, **extra: Any) -> dict[str, Any]:
    totals = trace.totals
    return {
        "trace_id": trace.trace_id,
        "total_latency_ms": round(trace.elapsed_ms(), 2),
        "total_cost": round(totals.cost_usd, 8),
        "llm_calls": totals.llm_calls,
        "cache_hits": totals.cache_hits,
        "prompt_tokens": totals.prompt_tokens,
        "completion_tokens": totals.completion_tokens,
        "cached_tokens": totals.cached_tokens,
        "degraded": trace.degraded,
        "degraded_reason": "; ".join(trace.degraded_reasons) or None,
        "corpus_entries": len(index.entries),
        "spans": trace.span_dicts(),
        **extra,
    }
