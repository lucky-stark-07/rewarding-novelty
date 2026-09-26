import json
import logging
import uuid
from fastapi import APIRouter, HTTPException, Request, Response
from ..novelty import score_submission
from ..schemas import ScoreRequest, ScoreResult
from ..telemetry import RequestTrace, current_trace
router = APIRouter(tags=["scoring"])
logger = logging.getLogger("rewarding_novelty.requests")


def _trace_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "").strip()[:100]
    return supplied if supplied and all(char.isalnum() or char in "-_." for char in supplied) else uuid.uuid4().hex


@router.post("/score", response_model=ScoreResult)
async def score(submission: ScoreRequest, request: Request, response: Response) -> ScoreResult:
    state = request.app.state
    stats = state.stats
    trace = RequestTrace(_trace_id(request))
    response.headers["x-request-id"] = trace.trace_id
    if stats.in_flight >= state.settings.max_inflight_requests:
        stats.rejected += 1
        raise HTTPException(status_code=503, detail="The scoring service is at capacity. Retry shortly.", headers={"Retry-After": "1", "x-request-id": trace.trace_id})
    stats.in_flight += 1
    token = current_trace.set(trace)
    outcome = "error"
    try:
        result = await score_submission(submission, state.index, state.llm, settings=state.settings, add_to_corpus=submission.add_to_corpus)
        outcome = "degraded" if result.degraded else "ok"
    finally:
        stats.in_flight -= 1
        current_trace.reset(token)
        stats.record(outcome, trace.elapsed_ms(), trace)
        state.trace_sink.write(trace, outcome=outcome)
    log_meta = {key: value for key, value in result.meta.items() if key != "spans"}
    logger.info(json.dumps({"event": "score_request", "submission_score": result.submission_score, **log_meta}, sort_keys=True))
    return result
