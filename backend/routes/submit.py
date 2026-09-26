import json
import logging
import uuid
from fastapi import APIRouter
from fastapi import Request
from ..novelty import score_submission
from ..schemas import ScoreRequest, ScoreResult
router = APIRouter(tags=["scoring"])
logger = logging.getLogger("rewarding_novelty.requests")

@router.post("/score", response_model=ScoreResult)
def score(submission: ScoreRequest, request: Request) -> ScoreResult:
    supplied_id = request.headers.get("x-request-id", "").strip()
    request_id = supplied_id[:100] if supplied_id and all(char.isalnum() or char in "-_." for char in supplied_id[:100]) else str(uuid.uuid4())
    result = score_submission(submission, request_id=request_id, add_to_corpus=submission.add_to_corpus)
    logger.info(json.dumps({"event": "score_request", "request_id": request_id, "submission_score": result.submission_score, **result.meta}, sort_keys=True))
    return result
