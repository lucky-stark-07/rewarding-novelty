import json
import logging

from fastapi.testclient import TestClient

from backend.main import app
from backend.routes import submit as submit_route
from backend.schemas import FieldName, FieldScore, ScoreResult


def test_score_route_returns_request_meta_and_structured_log(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="rewarding_novelty.requests")
    def fixture_score_result(submission, request_id=None, add_to_corpus=False):
        return ScoreResult(
            submission_score=0.5,
            field_scores=[FieldScore(field=field, score=0.5, novelty_fraction=0.5, relevance_gate=1.0) for field in FieldName],
            scoring_mode="novelty × relevance",
            message="fixture",
            meta={"request_id": request_id, "estimated_cost_usd": 0.0},
            add_to_corpus_requested=add_to_corpus,
            added_to_corpus=add_to_corpus,
        )

    monkeypatch.setattr(submit_route, "score_submission", fixture_score_result)
    response = TestClient(app).post(
        "/score",
        headers={"x-request-id": "test-request-123"},
        json={"what_you_like": "Useful", "what_you_dislike": "Slow", "problem_solved": "Planning", "add_to_corpus": True},
    )
    assert response.status_code == 200
    assert response.json()["meta"]["request_id"] == "test-request-123"
    assert response.json()["add_to_corpus_requested"] is True
    assert response.json()["added_to_corpus"] is True
    log_record = next(record for record in caplog.records if record.name == "rewarding_novelty.requests")
    assert json.loads(log_record.message)["request_id"] == "test-request-123"


def test_score_route_rejects_overlong_field() -> None:
    response = TestClient(app).post(
        "/score",
        json={"what_you_like": "x" * 4001, "what_you_dislike": "", "problem_solved": ""},
    )
    assert response.status_code == 422
