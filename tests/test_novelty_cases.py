import ast
import json
from pathlib import Path
import pytest
from backend.config import Settings
from backend.corpus import CorpusStore
from backend.embeddings import embed
from backend.novelty import score_submission
from backend.schemas import Claim, ClaimExtractionResponse, CorpusEntry, EntailmentResponse, FieldName, RelevanceResponse, Submission
FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURES = json.loads((FIXTURE_DIR / "submissions.json").read_text())
LLM_FIXTURES = json.loads((FIXTURE_DIR / "llm_responses.json").read_text())

class FixtureLLM:
    """Only judge outputs are fixtures; embeddings and scoring math are production code."""
    def __init__(self) -> None:
        self.responses = LLM_FIXTURES
    def complete_json(self, *, model: str, system: str, prompt: str, response_model: type, temperature: float = 0):
        if "You extract atomic claims" in system:
            incoming = ast.literal_eval(prompt.removeprefix("Review fields:\n"))
            response = {"claims": [claim for field in incoming for claim in self.responses["extraction"][f"{field}|{incoming[field]}"]]}
        elif "strict relevance judge" in system:
            claim = prompt.split("Claim: ", 1)[1]
            response = self.responses["relevance"].get(claim, {"relevance_score": 0.85, "reason": "The claim concerns product team planning."})
        else:
            candidate = prompt.split("Candidate claim: ", 1)[1]
            response = self.responses["entailment"].get(candidate, {"covered": False, "reason": "The claims describe distinct product observations."})
        return response_model.model_validate(response)

@pytest.fixture
def corpus(tmp_path: Path) -> CorpusStore:
    store = CorpusStore(tmp_path / "corpus.json")
    base = Submission(what_you_like="It centralizes product planning.", what_you_dislike="The interface has too many clicks.", problem_solved="It centralizes planning.")
    store.replace([CorpusEntry(id="base", submission=base, claims=[Claim(id="c1", field=FieldName.WHAT_YOU_LIKE, text=base.what_you_like, source_submission_id="base"), Claim(id="c2", field=FieldName.WHAT_YOU_DISLIKE, text=base.what_you_dislike, source_submission_id="base"), Claim(id="c3", field=FieldName.PROBLEM_SOLVED, text=base.problem_solved, source_submission_id="base")])])
    return store

@pytest.mark.parametrize("case, expectation", [("novel_relevant", "high"), ("redundant", "low"), ("irrelevant", "low"), ("paraphrase", "low"), ("gibberish", "low")])
def test_expected_scoring_cases(case: str, expectation: str, corpus: CorpusStore) -> None:
    settings = Settings(high_threshold=0.65, low_threshold=0.35)
    result = score_submission(Submission.model_validate(FIXTURES[case]), corpus, llm=FixtureLLM(), settings=settings)
    if expectation == "high": assert result.submission_score >= 0.6
    elif case == "gibberish": assert result.submission_score <= 0.2
    else: assert result.submission_score <= 0.3

def test_novel_relevant_beats_every_negative_case_by_margin(corpus: CorpusStore) -> None:
    settings = Settings(high_threshold=0.65, low_threshold=0.35)
    scores = {case: score_submission(Submission.model_validate(FIXTURES[case]), corpus, llm=FixtureLLM(), settings=settings).submission_score for case in FIXTURES}
    assert scores["novel_relevant"] - max(score for case, score in scores.items() if case != "novel_relevant") >= 0.3

def test_scoring_uses_real_sentence_transformer_embeddings() -> None:
    vectors = embed(["Product planning is centralized.", "Project plans are managed in one place."])
    assert vectors.shape[0] == 2
    assert float(vectors[0] @ vectors[1]) > 0.45

def test_no_extractable_claims_returns_typed_zero_result(tmp_path: Path) -> None:
    empty = Submission()
    result = score_submission(empty, CorpusStore(tmp_path / "empty.json"), llm=FixtureLLM(), settings=Settings())
    assert result.submission_score == 0
    assert result.reason == "no extractable claims"

def test_exact_corpus_duplicate_scores_zero_without_llm(corpus: CorpusStore) -> None:
    submission = corpus.list()[0].submission
    result = score_submission(submission, corpus)
    assert result.submission_score == 0
    assert all(claim.novelty_status == "covered" for field in result.field_scores for claim in field.claims)

def test_empty_corpus_treats_extractable_claims_as_novel(tmp_path: Path) -> None:
    result = score_submission(Submission.model_validate(FIXTURES["novel_relevant"]), CorpusStore(tmp_path / "empty.json"), llm=FixtureLLM(), settings=Settings())
    assert result.submission_score > 0.6
    assert all(claim.novelty_status == "novel" for field in result.field_scores for claim in field.claims)

def test_padding_redundant_claims_reduces_score(corpus: CorpusStore) -> None:
    settings = Settings(high_threshold=0.65, low_threshold=0.35)
    padded = score_submission(Submission(what_you_like="Padding review"), corpus, llm=FixtureLLM(), settings=settings)
    unpadded = score_submission(Submission(what_you_like="Single novel review"), corpus, llm=FixtureLLM(), settings=settings)
    assert 0 < padded.submission_score < unpadded.submission_score

def test_keyword_stuffing_does_not_make_off_topic_claim_relevant(corpus: CorpusStore) -> None:
    result = score_submission(Submission(what_you_like="Keyword stuffing review"), corpus, llm=FixtureLLM(), settings=Settings())
    assert result.submission_score <= 0.2
    assert result.field_scores[0].claims[0].relevance_score == 0.0

def test_near_duplicate_with_one_new_detail_gets_partial_credit(corpus: CorpusStore) -> None:
    result = score_submission(Submission(what_you_like="Small new detail review"), corpus, llm=FixtureLLM(), settings=Settings(high_threshold=0.65, low_threshold=0.35))
    assert 0 < result.submission_score < 0.85

def test_opted_in_accepted_submission_is_added_to_corpus(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path / "corpus.json")
    result = score_submission(Submission.model_validate(FIXTURES["novel_relevant"]), store, llm=FixtureLLM(), settings=Settings(corpus_acceptance_threshold=0.6), add_to_corpus=True)
    assert result.add_to_corpus_requested is True
    assert result.added_to_corpus is True
    assert len(store.list()) == 1

def test_opted_in_low_score_is_not_added_to_corpus(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path / "corpus.json")
    result = score_submission(Submission.model_validate(FIXTURES["irrelevant"]), store, llm=FixtureLLM(), settings=Settings(corpus_acceptance_threshold=0.6), add_to_corpus=True)
    assert result.add_to_corpus_requested is True
    assert result.added_to_corpus is False
    assert store.list() == []
