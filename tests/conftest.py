import asyncio
import json
from pathlib import Path
import pytest
from backend.config import Settings
from backend.corpus import CorpusIndex, CorpusStore
from backend.embeddings import embed
from backend.novelty import score_submission
from backend.reference import REFERENCE_PRODUCT_DESCRIPTION
from backend.schemas import Claim, CorpusEntry, FieldName, ScoreResult, Submission

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURES = json.loads((FIXTURE_DIR / "submissions.json").read_text())
LLM_FIXTURES = json.loads((FIXTURE_DIR / "llm_responses.json").read_text())


class FixtureLLM:
    """Only judge outputs are fixtures; embeddings, retrieval, batching and scoring math are production code."""

    def __init__(self, delay: float = 0.0) -> None:
        self.responses = LLM_FIXTURES
        self.delay = delay
        self.calls: list[tuple[str, dict]] = []

    async def complete_json(self, prompt, *, model: str, variables: dict, response_model: type, temperature: float = 0, check=None):
        prompt.render(**variables)  # fail loudly if a template variable is missing
        self.calls.append((prompt.name, variables))
        if self.delay:
            await asyncio.sleep(self.delay)
        if prompt.name == "extract_claims":
            fixture = self.responses["extraction"].get(f"{variables['field']}|{variables['text']}", [{"text": variables["text"]}])
            response = {"claims": [{"text": claim["text"]} for claim in fixture]}
        elif prompt.name == "moderate":
            review = variables["review"]
            response = next((verdict for marker, verdict in self.responses.get("moderation", {}).items() if marker in review), {"verdict": "allow", "categories": [], "reason": "Ordinary product feedback."})
        elif prompt.name == "judge_relevance":
            items = json.loads(variables["claims"])
            default = {"relevance_score": 0.85, "reason": "The claim concerns product team planning."}
            response = {"results": [{"id": item["id"], **self.responses["relevance"].get(item["claim"], default)} for item in items]}
        else:
            items = json.loads(variables["items"])
            results = []
            for item in items:
                judged = self.responses["entailment"].get(item["candidate"], {"covered": False, "reason": "The claims describe distinct product observations."})
                coverage = judged.get("coverage", "full" if judged.get("covered") else "none")
                results.append({"id": item["id"], "coverage": coverage, "matched_existing": 1 if coverage != "none" else None, "reason": judged["reason"]})
            response = {"results": results}
        parsed = response_model.model_validate(response)
        if check is not None:
            check(parsed)
        return parsed

    def snapshot(self) -> dict:
        return {"fixture": True, "calls": len(self.calls)}


def run_score(submission: Submission, store: CorpusStore, llm=None, settings: Settings | None = None, **kwargs) -> ScoreResult:
    async def run() -> ScoreResult:
        index = await CorpusIndex.create(store, embed, REFERENCE_PRODUCT_DESCRIPTION)
        return await score_submission(submission, index, llm or FixtureLLM(), settings=settings or Settings(high_threshold=0.65, low_threshold=0.35), **kwargs)
    return asyncio.run(run())


@pytest.fixture
def corpus(tmp_path: Path) -> CorpusStore:
    store = CorpusStore(tmp_path / "corpus.json")
    base = Submission(what_you_like="It centralizes product planning.", what_you_dislike="The interface has too many clicks.", problem_solved="It centralizes planning.")
    store.replace([CorpusEntry(id="base", submission=base, claims=[Claim(id="c1", field=FieldName.WHAT_YOU_LIKE, text=base.what_you_like, source_submission_id="base"), Claim(id="c2", field=FieldName.WHAT_YOU_DISLIKE, text=base.what_you_dislike, source_submission_id="base"), Claim(id="c3", field=FieldName.PROBLEM_SOLVED, text=base.problem_solved, source_submission_id="base")])])
    return store
