from pathlib import Path
import pytest
from backend.config import Settings
from backend.corpus import CorpusStore
from backend.embeddings import embed
from backend.schemas import Claim, CorpusEntry, FieldName, Submission
from tests.conftest import FIXTURES, FixtureLLM, run_score

BANDED = Settings(high_threshold=0.65, low_threshold=0.35)


@pytest.mark.parametrize("case, expectation", [("novel_relevant", "high"), ("redundant", "low"), ("irrelevant", "low"), ("paraphrase", "low"), ("gibberish", "low")])
def test_expected_scoring_cases(case: str, expectation: str, corpus: CorpusStore) -> None:
    result = run_score(Submission.model_validate(FIXTURES[case]), corpus, settings=BANDED)
    if expectation == "high": assert result.submission_score >= 0.6
    elif case == "gibberish": assert result.submission_score <= 0.2
    else: assert result.submission_score <= 0.3


def test_novel_relevant_beats_every_negative_case_by_margin(corpus: CorpusStore) -> None:
    scores = {case: run_score(Submission.model_validate(FIXTURES[case]), corpus, settings=BANDED).submission_score for case in FIXTURES}
    assert scores["novel_relevant"] - max(score for case, score in scores.items() if case != "novel_relevant") >= 0.3


def test_scoring_uses_real_sentence_transformer_embeddings() -> None:
    vectors = embed(["Product planning is centralized.", "Project plans are managed in one place."])
    assert vectors.shape[0] == 2
    assert float(vectors[0] @ vectors[1]) > 0.45


def test_embedding_cache_returns_identical_vectors() -> None:
    first = embed(["Cache me once.", "Cache me once."])
    second = embed(["Cache me once."])
    assert (first[0] == first[1]).all() and (first[0] == second[0]).all()


def test_no_extractable_claims_returns_typed_zero_result(tmp_path: Path) -> None:
    result = run_score(Submission(), CorpusStore(tmp_path / "empty.json"), settings=Settings())
    assert result.submission_score == 0
    assert result.reason == "no extractable claims"


class ExplodingLLM:
    async def complete_json(self, **_kwargs):
        raise AssertionError("exact duplicates must not call the LLM")


def test_exact_corpus_duplicate_scores_zero_without_llm(corpus: CorpusStore) -> None:
    result = run_score(corpus.list()[0].submission, corpus, llm=ExplodingLLM())
    assert result.submission_score == 0
    assert all(claim.novelty_status == "covered" for field in result.field_scores for claim in field.claims)


def test_empty_corpus_treats_extractable_claims_as_novel(tmp_path: Path) -> None:
    result = run_score(Submission.model_validate(FIXTURES["novel_relevant"]), CorpusStore(tmp_path / "empty.json"), settings=Settings())
    assert result.submission_score > 0.6
    assert all(claim.novelty_status == "novel" for field in result.field_scores for claim in field.claims)


def test_padding_redundant_claims_reduces_score(corpus: CorpusStore) -> None:
    padded = run_score(Submission(what_you_like="Padding review"), corpus, settings=BANDED)
    unpadded = run_score(Submission(what_you_like="Single novel review"), corpus, settings=BANDED)
    assert 0 < padded.submission_score < unpadded.submission_score


def test_keyword_stuffing_does_not_make_off_topic_claim_relevant(corpus: CorpusStore) -> None:
    result = run_score(Submission(what_you_like="Keyword stuffing review"), corpus, settings=Settings())
    assert result.submission_score <= 0.2
    assert result.field_scores[0].claims[0].relevance_score == 0.0


def test_near_duplicate_with_one_new_detail_gets_partial_credit(corpus: CorpusStore) -> None:
    result = run_score(Submission(what_you_like="Small new detail review"), corpus, settings=BANDED)
    assert 0 < result.submission_score < 0.85


def test_relevance_gates_each_claim_not_the_field_average(corpus: CorpusStore) -> None:
    """A covered on-topic claim must not lend relevance to a novel off-topic claim in the same field."""
    result = run_score(Submission(what_you_like="Mixed gating review"), corpus, settings=BANDED)
    statuses = sorted(claim.novelty_status for claim in result.field_scores[0].claims)
    assert statuses == ["covered", "novel"]
    assert result.submission_score == 0.0


@pytest.fixture
def roadmap_corpus(tmp_path: Path) -> CorpusStore:
    store = CorpusStore(tmp_path / "corpus.json")
    texts = ["It centralizes product planning.", "Roadmaps are shared with stakeholders.", "Customer feedback is linked to roadmap items."]
    entries = [CorpusEntry(id=f"e{i}", submission=Submission(what_you_like=text), claims=[Claim(id=f"c{i}", field=FieldName.WHAT_YOU_LIKE, text=text, source_submission_id=f"e{i}")]) for i, text in enumerate(texts)]
    store.replace(entries)
    return store


def test_partial_coverage_earns_partial_novelty_credit(roadmap_corpus: CorpusStore) -> None:
    result = run_score(Submission(what_you_like="Partial detail review"), roadmap_corpus, settings=Settings(low_threshold=0.30, high_threshold=0.70, partial_novelty_credit=0.5))
    claim = result.field_scores[0].claims[0]
    assert claim.novelty_status == "partial" and claim.novelty_score == 0.5 and claim.entailment_judged
    assert result.submission_score == pytest.approx(0.5 * claim.relevance_score)


def test_ambiguous_claim_is_judged_against_top_k_neighbours_in_one_batch(roadmap_corpus: CorpusStore) -> None:
    llm = FixtureLLM()
    result = run_score(Submission(what_you_like="Top k review"), roadmap_corpus, llm=llm, settings=Settings(low_threshold=0.30, high_threshold=0.70, entailment_top_k=3))
    claim = result.field_scores[0].claims[0]
    assert claim.novelty_status == "covered"
    assert len(claim.neighbors) == 3
    coverage_prompts = [prompt for name, prompt in llm.calls if name == "llm.judge_coverage"]
    assert len(coverage_prompts) == 1
    assert all(text in coverage_prompts[0] for text in ("Roadmaps are shared", "Customer feedback is linked", "It centralizes product planning"))


def test_judging_is_batched_regardless_of_claim_count(corpus: CorpusStore) -> None:
    llm = FixtureLLM()
    result = run_score(Submission.model_validate(FIXTURES["paraphrase"]), corpus, llm=llm, settings=BANDED)
    assert sum(len(field.claims) for field in result.field_scores) == 3
    assert sorted(name for name, _ in llm.calls) == ["llm.extract_claims", "llm.judge_coverage", "llm.judge_relevance"]


def test_result_meta_includes_trace_spans(corpus: CorpusStore) -> None:
    result = run_score(Submission.model_validate(FIXTURES["novel_relevant"]), corpus, settings=BANDED, request_id="trace-test")
    names = {span["name"] for span in result.meta["trace"]}
    assert {"corpus.duplicate_check", "embed.claims", "retrieval.knn", "judge.batch"} <= names
    assert result.meta["request_id"] == "trace-test"
    assert result.meta["stage_latency_seconds"]["total"] > 0


def test_opted_in_accepted_submission_is_added_to_corpus(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path / "corpus.json")
    result = run_score(Submission.model_validate(FIXTURES["novel_relevant"]), store, settings=Settings(corpus_acceptance_threshold=0.6), add_to_corpus=True)
    assert result.add_to_corpus_requested is True
    assert result.added_to_corpus is True
    assert len(store.list()) == 1


def test_opted_in_low_score_is_not_added_to_corpus(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path / "corpus.json")
    result = run_score(Submission.model_validate(FIXTURES["irrelevant"]), store, settings=Settings(corpus_acceptance_threshold=0.6), add_to_corpus=True)
    assert result.add_to_corpus_requested is True
    assert result.added_to_corpus is False
    assert store.list() == []
