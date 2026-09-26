"""Run the labeled 25-case evaluation and save metrics plus a threshold sweep."""
from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from pathlib import Path

from sklearn.metrics import roc_auc_score

from backend.config import get_settings
from backend.corpus import CorpusIndex, CorpusStore
from backend.embeddings import embed
from backend.llm_client import LLMClient
from backend.novelty import SCORING_MODE, judge_coverage, score_submission
from backend.reference import REFERENCE_PRODUCT_DESCRIPTION
from backend.schemas import Coverage, FieldName, Submission

CASES_PATH = Path("tests/fixtures/eval_cases.json")
REPORT_JSON = Path("reports/eval.json")
REPORT_MD = Path("reports/eval.md")
SWEEP_MIN, SWEEP_MAX = 0.25, 0.95


async def main() -> None:
    cases = json.loads(CASES_PATH.read_text())
    settings = get_settings()
    client = LLMClient(settings)
    index = await CorpusIndex.create(CorpusStore(settings.corpus_path), embed, REFERENCE_PRODUCT_DESCRIPTION)
    redundant_slots = [case for case in cases if case["category"] == "redundant"]
    for case, entry in zip(redundant_slots, index.entries[: len(redundant_slots)]):
        case["origin"] = "synthetic_corpus_exact_duplicate"
        case.update(entry.submission.model_dump())
    results = []
    sweep_assessments = []
    degraded_cases: dict[str, str | None] = {}
    for case in cases:
        submission = Submission.model_validate({key: case[key] for key in ("what_you_like", "what_you_dislike", "problem_solved")})
        result = await score_submission(submission, index, client, settings=settings)
        if result.degraded:
            degraded_cases[case["id"]] = result.degraded_reason
        results.append({"id": case["id"], "category": case["category"], "origin": case["origin"], "submission": submission.model_dump(), "score": result.submission_score, "field_scores": {field.field.value: field.score for field in result.field_scores}, "claim_decisions": [{"field": item.claim.field.value, "claim": item.claim.text, "status": item.novelty_status, "similarity": item.nearest_similarity, "nearest_claim": item.nearest_claim.text if item.nearest_claim else None, "neighbors": [{"text": n.claim.text, "similarity": n.similarity} for n in item.neighbors], "relevance": item.relevance_score, "relevance_reason": item.relevance_reason, "entailment_judged": item.entailment_judged, "entailment_reason": item.entailment_reason} for field in result.field_scores for item in field.claims]})
        should_be_covered = int(case["category"] in {"redundant", "paraphrase"})
        for field in result.field_scores:
            for item in field.claims:
                if item.neighbors:
                    sweep_assessments.append((should_be_covered, item))

    # Judge every claim whose top similarity could fall in a swept ambiguous band, against its
    # top-k neighbours above the lowest swept threshold. Batched, cached, and never repeated.
    to_judge = [item for _label, item in sweep_assessments if SWEEP_MIN <= item.neighbors[0].similarity < SWEEP_MAX]
    groups = [[item for item in to_judge if item.claim.field == field][start:start + 15] for field in FieldName for start in range(0, sum(item.claim.field == field for item in to_judge), 15)]
    chunks = await asyncio.gather(*(judge_coverage(group[0].claim.field, [(item.claim, [(n.claim, n.similarity) for n in item.neighbors if n.similarity > SWEEP_MIN]) for item in group], client, settings) for group in groups))
    judge_outcomes = {id(item): int(judgment.coverage == Coverage.FULL) for group, chunk in zip(groups, chunks) for item, judgment in zip(group, chunk)}

    categories: dict[str, list[float]] = defaultdict(list)
    for case in results:
        categories[case["category"]].append(case["score"])
    positive = categories["novel_relevant"]
    negative = [score for category, scores in categories.items() if category != "novel_relevant" for score in scores]
    margin = min(positive) - max(negative) if positive and negative else None
    y_true = [int(case["category"] == "novel_relevant") for case in results]
    auc = float(roc_auc_score(y_true, [case["score"] for case in results]))

    sweep = []
    for low in (0.25, 0.30, 0.35, 0.40, 0.42, 0.45, 0.50, 0.55, 0.60):
        for high in (0.65, 0.70, 0.75, 0.80, 0.82, 0.85, 0.90, 0.95):
            if low >= high:
                continue
            correct = correct_covered = correct_novel = total_covered = total_novel = 0
            for label, item in sweep_assessments:
                similarity = item.neighbors[0].similarity
                if similarity >= high:
                    prediction = 1
                elif similarity <= low:
                    prediction = 0
                else:
                    prediction = judge_outcomes.get(id(item), int(item.novelty_status == "covered"))
                correct += prediction == label
                if label:
                    total_covered += 1
                    correct_covered += prediction == 1
                else:
                    total_novel += 1
                    correct_novel += prediction == 0
            accuracy = correct / len(sweep_assessments) if sweep_assessments else 0.0
            balanced = 0.5 * (correct_covered / total_covered + correct_novel / total_novel) if total_covered and total_novel else accuracy
            sweep.append({"low_threshold": low, "high_threshold": high, "accuracy": accuracy, "balanced_accuracy": balanced, "coverage": 1.0})
    chosen = max(sweep, key=lambda item: (item["balanced_accuracy"], item["accuracy"], -abs(item["low_threshold"] - settings.low_threshold), -abs(item["high_threshold"] - settings.high_threshold))) if sweep else None

    usage = client.snapshot()
    category_metrics = {category: {"count": len(scores), "mean": sum(scores) / len(scores), "min": min(scores), "max": max(scores)} for category, scores in categories.items()}
    origins = Counter(case["origin"] for case in cases)
    report = {
        "dataset": {"count": len(cases), "origins": dict(origins), "categories": {key: sum(item["category"] == key for item in cases) for key in sorted(categories)}},
        "scoring_config": {"high_threshold": settings.high_threshold, "low_threshold": settings.low_threshold, "entailment_top_k": settings.entailment_top_k, "partial_novelty_credit": settings.partial_novelty_credit, "combination": SCORING_MODE},
        "per_category": category_metrics,
        "separation_margin": margin,
        "roc_auc_rewarded_vs_rest": auc,
        "threshold_sweep": {"selection_rule": "maximize balanced accuracy for covered (redundant/paraphrase) vs novel labels; ambiguous claims use cached LLM judge outcomes", "judge_pairs": len(judge_outcomes), "chosen": chosen, "candidates": sweep},
        "cases": results,
        "llm_usage": usage,
        "degraded_cases": degraded_cases,
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True))
    lines = ["# NoveltyLens scoring evaluation", "", f"Cases: {len(cases)} human-labeled; origin counts: {dict(origins)}. Redundancy examples are exact corpus entries; paraphrase and other examples are hand-written. Current thresholds: low `{settings.low_threshold:.2f}`, high `{settings.high_threshold:.2f}`; ambiguous claims judged against top-{settings.entailment_top_k} neighbours; partial coverage earns `{settings.partial_novelty_credit:.2f}` novelty. Combination: {SCORING_MODE}.", "", "## Per-category scores", "", "| Category | n | Mean | Min | Max |", "| --- | ---: | ---: | ---: | ---: |"]
    for category, values in category_metrics.items():
        lines.append(f"| {category} | {values['count']} | {values['mean']:.3f} | {values['min']:.3f} | {values['max']:.3f} |")
    lines += ["", f"Separation margin (lowest novel+relevant minus highest other): **{margin:.3f}**" if margin is not None else "Separation margin: unavailable", f"ROC-AUC, novel+relevant vs rest: **{auc:.3f}**", "", "## Covered/novel threshold sweep", "", "Sweep maximizes balanced accuracy for covered vs novel labels; ambiguous claims use judge outcomes.", "", f"Claim-level sweep optimum: low `{chosen['low_threshold']:.2f}`, high `{chosen['high_threshold']:.2f}` (balanced accuracy {chosen['balanced_accuracy']:.3f}). Advisory only: its labels mark every claim in a paraphrase case as covered and count judge `partial` as novel. Defaults are chosen by submission-level separation above." if chosen else "No threshold candidates.", "", f"Model spend for this run: ${usage['cost_usd']:.4f} ({usage['calls']:.0f} upstream calls, {usage['prompt_tokens']:.0f} input and {usage['completion_tokens']:.0f} output tokens; cache hit rate {usage['cache_hit_rate']}; served models {usage['served_models']}).", f"Degraded cases: {degraded_cases or 'none'}.", "", "This small controlled dataset is evidence for iteration, not a claim of broad production calibration."]
    REPORT_MD.write_text("\n".join(lines) + "\n")
    print(REPORT_MD.read_text())
    print(f"Detailed case outputs: {REPORT_JSON}")


if __name__ == "__main__":
    asyncio.run(main())
