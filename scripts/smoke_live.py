"""Live, cached OpenRouter smoke run across the five acceptance fixtures."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.config import get_settings
from backend.corpus import CorpusIndex, CorpusStore
from backend.embeddings import embed
from backend.llm_client import LLMClient
from backend.novelty import score_submission
from backend.reference import REFERENCE_PRODUCT_DESCRIPTION
from backend.schemas import Submission

FIXTURES = json.loads((Path("tests/fixtures/submissions.json")).read_text())
CASES = [
    ("novel_relevant", "high"),
    ("redundant", "low"),
    ("irrelevant", "low"),
    ("paraphrase", "low"),
    ("gibberish", "low"),
]


async def main() -> None:
    settings = get_settings()
    llm = LLMClient(settings)
    index = await CorpusIndex.create(CorpusStore(settings.corpus_path), embed, REFERENCE_PRODUCT_DESCRIPTION)
    entries = index.entries
    # Ground repetition and paraphrase checks in actual generated claims. A generic
    # "central planning" review is not redundant unless this corpus contains that idea.
    repeat_entry = entries[0]
    search_entry = next((entry for entry in entries if "search" in entry.submission.what_you_dislike.lower()), entries[1])
    live_inputs = dict(FIXTURES)
    live_inputs["redundant"] = repeat_entry.submission.model_dump()
    live_inputs["paraphrase"] = {
        "what_you_like": "The platform improves collaboration across functions by letting departments contribute openly to product strategy.",
        "what_you_dislike": "Search could be more robust.",
        "problem_solved": "It helps break down silos between departments.",
    }
    rows = []
    details = {}
    for name, band in CASES:
        result = details[name] = await score_submission(Submission.model_validate(live_inputs[name]), index, llm, settings=settings)
        passed = result.submission_score >= 0.6 if band == "high" else result.submission_score <= (0.2 if name == "gibberish" else 0.3)
        fields = ", ".join(f"{item.score:.2f}" for item in result.field_scores)
        rows.append((name, result.submission_score, fields, band, "PASS" if passed else "FAIL"))
    print("case | score | field scores (like, dislike, solved) | expected | result")
    print("--- | ---: | --- | --- | ---")
    for name, score, fields, band, result in rows:
        print(f"{name} | {score:.3f} | {fields} | {band} | {result}")
    for name, _score, _fields, _band, outcome in rows:
        if outcome == "FAIL":
            print(f"\n{name} claim decisions:")
            for field in details[name].field_scores:
                for assessment in field.claims:
                    nearest = assessment.nearest_claim.text if assessment.nearest_claim else "(none)"
                    print(f"{field.field.value}: {assessment.novelty_status} sim={assessment.nearest_similarity} relevance={assessment.relevance_score:.2f}; {assessment.claim.text!r} vs {nearest!r}; judge={assessment.entailment_reason}")
    print("\nLLM usage (this run only):")
    snapshot = llm.snapshot()
    print(f"calls={snapshot['calls']} cache_hit_rate={snapshot['cache_hit_rate']} prompt_tokens={snapshot['prompt_tokens']} completion_tokens={snapshot['completion_tokens']} cost_usd=${snapshot['cost_usd']:.4f} served_models={snapshot['served_models']}")
    if any(result.degraded for result in details.values()):
        print("WARNING: at least one case was scored in degraded mode:", {name: result.degraded_reason for name, result in details.items() if result.degraded})
    if any(row[-1] == "FAIL" for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
