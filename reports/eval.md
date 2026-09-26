# NoveltyLens scoring evaluation (tuning set)

**In-sample.** The high threshold (0.75) and the coverage and relevance prompts were tuned while looking at these 25 cases, so these numbers overstate real-world accuracy. The untouched held-out result is in `reports/holdout.md`.

Cases: 25 human-labeled; origin counts: {'handwritten': 20, 'synthetic_corpus_exact_duplicate': 5}. The 5 redundancy examples are exact corpus entries, which score 0 through the duplicate check without any LLM call (trivially easy); paraphrase and other examples are hand-written. Current thresholds: low `0.35`, high `0.75`; ambiguous claims judged against top-3 neighbours; partial coverage earns `0.50` novelty. Combination: mean(novelty × relevance) per claim.

## Per-category scores

| Category | n | Mean | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| novel_relevant | 5 | 0.892 | 0.833 | 1.000 |
| redundant | 5 | 0.000 | 0.000 | 0.000 |
| paraphrase | 5 | 0.233 | 0.056 | 0.444 |
| novel_irrelevant | 5 | 0.000 | 0.000 | 0.000 |
| gibberish | 5 | 0.000 | 0.000 | 0.000 |

Separation margin (lowest novel+relevant minus highest other): **0.389**
ROC-AUC, novel+relevant vs rest: **1.000** (excluding the 5 exact duplicates: 1.000)

## Covered/novel threshold sweep

Sweep maximizes balanced accuracy for covered vs novel labels; ambiguous claims use judge outcomes.

Claim-level sweep optimum: low `0.35`, high `0.65` (balanced accuracy 0.782). Advisory only: its labels mark every claim in a paraphrase case as covered and count judge `partial` as novel. Defaults are chosen by submission-level separation above.

Model spend for this run: $0.0181 (45 upstream calls, 18384 input and 5040 output tokens; cache hit rate 0.6763; served models {'google/gemini-2.5-flash': 45}).
Degraded cases: none.

This small controlled dataset is evidence for iteration, not a claim of broad production calibration.
