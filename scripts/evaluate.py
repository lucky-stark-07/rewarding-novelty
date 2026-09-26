"""Run the labeled 25-case evaluation and save metrics plus a threshold sweep."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from sklearn.metrics import roc_auc_score

from backend.config import get_settings
from backend.corpus import CorpusStore
from backend.llm_client import LLMClient
from backend.novelty import _entailment, score_submission
from backend.schemas import Submission

CASES_PATH = Path("tests/fixtures/eval_cases.json")
REPORT_JSON = Path("reports/eval.json")
REPORT_MD = Path("reports/eval.md")


def main() -> None:
    cases = json.loads(CASES_PATH.read_text())
    settings = get_settings()
    client = LLMClient(settings)
    corpus = CorpusStore(settings.corpus_path)
    corpus_entries = corpus.list()
    redundant_slots = [case for case in cases if case["category"] == "redundant"]
    for case, entry in zip(redundant_slots, corpus_entries[: len(redundant_slots)]):
        case["origin"] = "synthetic_corpus_exact_duplicate"
        case.update(entry.submission.model_dump())
    results = []
    sweep_assessments = []
    for case in cases:
        submission = Submission.model_validate({key: case[key] for key in ("what_you_like", "what_you_dislike", "problem_solved")})
        result = score_submission(submission, corpus, llm=client, settings=settings)
        results.append({"id": case["id"], "category": case["category"], "origin": case["origin"], "submission": submission.model_dump(), "score": result.submission_score, "field_scores": {field.field.value: field.score for field in result.field_scores}, "claim_decisions": [{"field": item.claim.field.value, "claim": item.claim.text, "status": item.novelty_status, "similarity": item.nearest_similarity, "nearest_claim": item.nearest_claim.text if item.nearest_claim else None, "relevance": item.relevance_score, "relevance_reason": item.relevance_reason, "entailment_judged": item.entailment_judged, "entailment_reason": item.entailment_reason} for field in result.field_scores for item in field.claims]})
        should_be_covered = int(case["category"] in {"redundant", "paraphrase"})
        for field in result.field_scores:
            for item in field.claims:
                if item.nearest_similarity is not None:
                    sweep_assessments.append((should_be_covered, item))

    # Precompute judge outcomes for candidate-neighbor pairs that could fall in a
    # swept ambiguous band; the calls share the regular cache and never repeat.
    judge_outcomes = {}
    for _label, item in sweep_assessments:
        similarity = item.nearest_similarity
        if similarity is None or similarity < 0.25 or similarity >= 0.95 or item.nearest_claim is None:
            continue
        key = (item.nearest_claim.text, item.claim.text)
        if key not in judge_outcomes:
            judge_outcomes[key] = int(_entailment(item.nearest_claim, item.claim, client, settings).covered)

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
                similarity = item.nearest_similarity
                if similarity is None:
                    continue
                if similarity >= high:
                    prediction = 1
                elif similarity <= low:
                    prediction = 0
                else:
                    prediction = judge_outcomes.get((item.nearest_claim.text, item.claim.text), int(item.novelty_status == "covered"))
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

    category_metrics = {category: {"count": len(scores), "mean": sum(scores) / len(scores), "min": min(scores), "max": max(scores)} for category, scores in categories.items()}
    origins = Counter(case["origin"] for case in cases)
    report = {
        "dataset": {"count": len(cases), "origins": dict(origins), "categories": {key: sum(item["category"] == key for item in cases) for key in sorted(categories)}},
        "scoring_config": {"high_threshold": settings.high_threshold, "low_threshold": settings.low_threshold, "combination": "multiplication"},
        "per_category": category_metrics,
        "separation_margin": margin,
        "roc_auc_rewarded_vs_rest": auc,
        "threshold_sweep": {"selection_rule": "maximize balanced accuracy for covered (redundant/paraphrase) vs novel labels; ambiguous claims use cached LLM judge outcomes", "judge_pairs": len(judge_outcomes), "chosen": chosen, "candidates": sweep},
        "cases": results,
        "llm_usage": dict(client.metrics),
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True))
    lines = ["# Theme 3 scoring evaluation", "", f"Cases: {len(cases)} human-labeled; origin counts: {dict(origins)}. Redundancy examples are exact corpus entries; paraphrase and other examples are hand-written. Current thresholds: low `{settings.low_threshold:.2f}`, high `{settings.high_threshold:.2f}`. Combination: multiplication.", "", "## Per-category scores", "", "| Category | n | Mean | Min | Max |", "| --- | ---: | ---: | ---: | ---: |"]
    for category, values in category_metrics.items():
        lines.append(f"| {category} | {values['count']} | {values['mean']:.3f} | {values['min']:.3f} | {values['max']:.3f} |")
    lines += ["", f"Separation margin (lowest novel+relevant minus highest other): **{margin:.3f}**" if margin is not None else "Separation margin: unavailable", f"ROC-AUC, novel+relevant vs rest: **{auc:.3f}**", "", "## Covered/novel threshold sweep", "", "Sweep maximizes balanced accuracy for covered vs novel labels; ambiguous claims use judge outcomes.", "", f"Suggested low `{chosen['low_threshold']:.2f}`, high `{chosen['high_threshold']:.2f}` (balanced accuracy {chosen['balanced_accuracy']:.3f})." if chosen else "No threshold candidates.", "", f"Estimated model spend for this run: ${client.metrics['estimated_cost_usd']:.4f} ({client.metrics['prompt_tokens']} input and {client.metrics['completion_tokens']} output tokens; cache hits {client.metrics['cache_hits']}).", "", "This small controlled dataset is evidence for iteration, not a claim of broad production calibration."]
    REPORT_MD.write_text("\n".join(lines) + "\n")
    print(REPORT_MD.read_text())
    print(f"Detailed case outputs: {REPORT_JSON}")


if __name__ == "__main__":
    main()
