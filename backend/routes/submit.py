import json
import logging
import math
import uuid
from fastapi import APIRouter, HTTPException, Request, Response
from ..llm_client import CircuitOpenError, UpstreamError
from ..novelty import score_submission
from ..schemas import ScoreRequest, ScoreResult
from ..telemetry import RequestTrace, current_trace
router = APIRouter(tags=["scoring"])
logger = logging.getLogger("rewarding_novelty.requests")


def _request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "").strip()[:100]
    return supplied if supplied and all(char.isalnum() or char in "-_." for char in supplied) else str(uuid.uuid4())


@router.post("/score", response_model=ScoreResult)
async def score(submission: ScoreRequest, request: Request, response: Response) -> ScoreResult:
    state = request.app.state
    stats = state.stats
    request_id = _request_id(request)
    response.headers["x-request-id"] = request_id
    if stats.in_flight >= state.settings.max_inflight_requests:
        stats.rejected += 1
        raise HTTPException(status_code=503, detail="The scoring service is at capacity. Retry shortly.", headers={"Retry-After": "1", "x-request-id": request_id})
    stats.in_flight += 1
    trace = RequestTrace(request_id)
    token = current_trace.set(trace)
    outcome = "error"
    try:
        result = await score_submission(submission, state.index, state.llm, settings=state.settings, request_id=request_id, add_to_corpus=submission.add_to_corpus)
        outcome = "ok"
    except CircuitOpenError as exc:
        outcome = "circuit_open"
        raise HTTPException(status_code=503, detail="The scoring model is temporarily unavailable. Retry shortly.", headers={"Retry-After": str(math.ceil(exc.retry_after)), "x-request-id": request_id}) from exc
    except UpstreamError as exc:
        outcome = "upstream_error"
        logger.warning(json.dumps({"event": "score_upstream_error", "request_id": request_id, "error": str(exc)}))
        raise HTTPException(status_code=502, detail="The scoring model failed or returned invalid output. Try again.", headers={"x-request-id": request_id}) from exc
    finally:
        stats.in_flight -= 1
        current_trace.reset(token)
        stats.record(outcome, trace.elapsed_seconds(), trace.spans if outcome == "ok" else None)
    log_meta = {key: value for key, value in result.meta.items() if key != "trace"}
    logger.info(json.dumps({"event": "score_request", "submission_score": result.submission_score, **log_meta}, sort_keys=True))
    return result
