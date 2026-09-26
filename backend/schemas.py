from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field

class FieldName(str, Enum):
    WHAT_YOU_LIKE = "what_you_like"
    WHAT_YOU_DISLIKE = "what_you_dislike"
    PROBLEM_SOLVED = "problem_solved"

class Submission(BaseModel):
    what_you_like: str = Field(default="", max_length=4000)
    what_you_dislike: str = Field(default="", max_length=4000)
    problem_solved: str = Field(default="", max_length=4000)
    def field_text(self, field: FieldName) -> str:
        return getattr(self, field.value)

class ScoreRequest(Submission):
    add_to_corpus: bool = False

class Claim(BaseModel):
    id: str
    field: FieldName
    text: str
    source_submission_id: str | None = None

class ExtractedClaim(BaseModel):
    field: FieldName
    text: str = Field(min_length=1, max_length=1000)

class ClaimText(BaseModel):
    text: str = Field(min_length=1, max_length=1000)

class FieldClaimsResponse(BaseModel):
    claims: list[ClaimText] = Field(max_length=3)

class RelevanceJudgment(BaseModel):
    id: str
    relevance_score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=400)

class RelevanceBatchResponse(BaseModel):
    results: list[RelevanceJudgment]

class ModerationResponse(BaseModel):
    verdict: Literal["allow", "flag", "block"]
    categories: list[str] = Field(default_factory=list, max_length=8)
    reason: str = Field(min_length=1, max_length=400)

class Coverage(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"

class CoverageJudgment(BaseModel):
    id: str
    coverage: Coverage
    matched_existing: int | None = Field(default=None, ge=1, description="1-based index of the existing claim that covers the candidate most")
    reason: str = Field(min_length=1, max_length=400)

class CoverageBatchResponse(BaseModel):
    results: list[CoverageJudgment]

class GeneratedReview(BaseModel):
    what_you_like: str = Field(max_length=4000)
    what_you_dislike: str = Field(max_length=4000)
    problem_solved: str = Field(max_length=4000)
    claims: list[ExtractedClaim] = Field(default_factory=list, max_length=9)

class CorpusGenerationResponse(BaseModel):
    reviews: list[GeneratedReview] = Field(min_length=1, max_length=50)

class Neighbor(BaseModel):
    claim: Claim
    similarity: float = Field(ge=-1, le=1)

class ClaimAssessment(BaseModel):
    claim: Claim
    novelty_status: str = "pending"  # novel | partial | covered
    novelty_score: float = Field(ge=0, le=1)
    relevance_score: float = Field(ge=0, le=1)
    relevance_reason: str = ""
    nearest_claim: Claim | None = None
    nearest_similarity: float | None = Field(default=None, ge=-1, le=1)
    neighbors: list[Neighbor] = Field(default_factory=list)
    entailment_judged: bool = False
    entailment_reason: str | None = None

class FieldScore(BaseModel):
    field: FieldName
    score: float = Field(ge=0, le=1, description="Mean over claims of novelty × relevance")
    novelty_fraction: float = Field(ge=0, le=1)
    relevance_gate: float = Field(ge=0, le=1)
    claims: list[ClaimAssessment] = Field(default_factory=list)

class ScoreResult(BaseModel):
    submission_score: float = Field(ge=0, le=1)
    field_scores: list[FieldScore]
    scoring_mode: str
    message: str
    reason: str | None = None
    degraded: bool = False
    degraded_reason: str | None = None
    # {"masked": {"EMAIL": 1}, "moderation": "allow|flag|block|unavailable|disabled", "categories": [...], "warnings": [...]}; never contains masked values
    guardrails: dict = Field(default_factory=dict)
    meta: dict = Field(default_factory=dict)
    add_to_corpus_requested: bool = False
    added_to_corpus: bool = False

class CorpusEntry(BaseModel):
    id: str
    submission: Submission
    claims: list[Claim] = Field(default_factory=list)
