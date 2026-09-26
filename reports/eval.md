# NoveltyLens scoring evaluation

Cases: 25 human-labeled; origin counts: {'handwritten': 20, 'synthetic_corpus_exact_duplicate': 5}. Redundancy examples are exact corpus entries; paraphrase and other examples are hand-written. Current thresholds: low `0.35`, high `0.75`; ambiguous claims judged against top-3 neighbours; partial coverage earns `0.50` novelty. Combination: mean(novelty × relevance) per claim.

## Per-category scores

| Category | n | Mean | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| novel_relevant | 5 | 0.925 | 0.875 | 1.000 |
| redundant | 5 | 0.000 | 0.000 | 0.000 |
| paraphrase | 5 | 0.229 | 0.056 | 0.424 |
| novel_irrelevant | 5 | 0.000 | 0.000 | 0.000 |
| gibberish | 5 | 0.000 | 0.000 | 0.000 |

Separation margin (lowest novel+relevant minus highest other): **0.451**
ROC-AUC, novel+relevant vs rest: **1.000**

## Covered/novel threshold sweep

Sweep maximizes balanced accuracy for covered vs novel labels; ambiguous claims use judge outcomes.

Claim-level sweep optimum: low `0.35`, high `0.65` (balanced accuracy 0.782). Advisory only: its labels mark every claim in a paraphrase case as covered and count judge `partial` as novel. Defaults are chosen by submission-level separation above.

Model spend for this run: $0.0274 (34 upstream calls, 21780 input and 8355 output tokens; cache hit rate 0.7554; served models {'google/gemini-2.5-flash': 34}).
Degraded cases: none.

This small controlled dataset is evidence for iteration, not a claim of broad production calibration.
