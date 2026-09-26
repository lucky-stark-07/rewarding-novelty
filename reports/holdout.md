# NoveltyLens held-out evaluation

15 labelled cases written after tuning finished and never used to choose thresholds or edit prompts (`tests/fixtures/holdout_cases.json`). Paraphrase cases rewrite real corpus entries. Pass bounds were fixed in `scripts/evaluate.py` before the first run. Config: low `0.35`, high `0.75`, top-3.

**Passed 12 / 15.** Separation margin (lowest novel+relevant minus highest other): **0.111**. ROC-AUC: **1.000**.

| Case | Category | Score | Expected | Result |
| --- | --- | ---: | --- | --- |
| h-nr1 | novel_relevant | 0.792 | ≥ 0.6 | PASS |
| h-nr2 | novel_relevant | 0.958 | ≥ 0.6 | PASS |
| h-nr3 | novel_relevant | 0.833 | ≥ 0.6 | PASS |
| h-nr4 | novel_relevant | 0.500 | ≥ 0.6 | **FAIL** |
| h-pp1 | paraphrase | 0.389 | ≤ 0.3 | **FAIL** |
| h-pp2 | paraphrase | 0.361 | ≤ 0.3 | **FAIL** |
| h-pp3 | paraphrase | 0.278 | ≤ 0.3 | PASS |
| h-ni1 | novel_irrelevant | 0.000 | ≤ 0.2 | PASS |
| h-ni2 | novel_irrelevant | 0.000 | ≤ 0.2 | PASS |
| h-ni3 | novel_irrelevant | 0.000 | ≤ 0.2 | PASS |
| h-gb1 | gibberish | 0.000 | ≤ 0.2 | PASS |
| h-vg1 | vague | 0.167 | ≤ 0.3 | PASS |
| h-vg2 | vague | 0.167 | ≤ 0.3 | PASS |
| h-in1 | adversarial | 0.000 | ≤ 0.3 | PASS |
| h-in2 | adversarial | 0.111 | ≤ 0.3 | PASS |

Model spend: $0.0000. Per-claim decisions and judge reasons: `reports/holdout.json`.
