# Theme 3 scoring evaluation

Cases: 25 human-labeled; origin counts: {'handwritten': 20, 'synthetic_corpus_exact_duplicate': 5}. Redundancy examples are exact corpus entries; paraphrase and other examples are hand-written. Current thresholds: low `0.35`, high `0.65`. Combination: multiplication.

## Per-category scores

| Category | n | Mean | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| novel_relevant | 5 | 0.733 | 0.667 | 1.000 |
| redundant | 5 | 0.000 | 0.000 | 0.000 |
| paraphrase | 5 | 0.272 | 0.000 | 0.750 |
| novel_irrelevant | 5 | 0.000 | 0.000 | 0.000 |
| gibberish | 5 | 0.000 | 0.000 | 0.000 |

Separation margin (lowest novel+relevant minus highest other): **-0.083**
ROC-AUC, novel+relevant vs rest: **0.960**

## Covered/novel threshold sweep

Sweep maximizes balanced accuracy for covered vs novel labels; ambiguous claims use judge outcomes.

Suggested low `0.35`, high `0.65` (balanced accuracy 0.898).

Estimated model spend for this run: $0.0004 (166 input and 146 output tokens; cache hits 158).

This small controlled dataset is evidence for iteration, not a claim of broad production calibration.
