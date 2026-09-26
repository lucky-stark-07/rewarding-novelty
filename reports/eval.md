# Theme 3 scoring evaluation

Cases: 25 human-labeled; origin counts: {'handwritten': 20, 'synthetic_corpus_exact_duplicate': 5}. Redundancy examples are exact corpus entries; paraphrase and other examples are hand-written. Current thresholds: low `0.35`, high `0.75`; ambiguous claims judged against top-3 neighbours; partial coverage earns `0.50` novelty. Combination: mean(novelty × relevance) per claim.

## Per-category scores

| Category | n | Mean | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| novel_relevant | 5 | 0.867 | 0.667 | 1.000 |
| redundant | 5 | 0.000 | 0.000 | 0.000 |
| paraphrase | 5 | 0.214 | 0.000 | 0.417 |
| novel_irrelevant | 5 | 0.000 | 0.000 | 0.000 |
| gibberish | 5 | 0.000 | 0.000 | 0.000 |

Separation margin (lowest novel+relevant minus highest other): **0.250**
ROC-AUC, novel+relevant vs rest: **1.000**

## Covered/novel threshold sweep

Sweep maximizes balanced accuracy for covered vs novel labels; ambiguous claims use judge outcomes.

Claim-level sweep optimum: low `0.35`, high `0.65` (balanced accuracy 0.838). Advisory only: its labels mark every claim in a paraphrase case as covered and count judge `partial` as novel. Defaults are chosen by submission-level separation above.

Estimated model spend for this run: $0.0000 (0 input and 0 output tokens; cache hits 54).

This small controlled dataset is evidence for iteration, not a claim of broad production calibration.
