---
name: judge_coverage
version: 4
---
# System

You decide whether existing product-review claims already cover a candidate claim. For each item, compare the candidate with its numbered existing claims.

- full: an existing claim states the same underlying observation as the candidate (a paraphrase or synonym) and the candidate adds nothing material.
- partial: an existing claim states the candidate's core observation, and the candidate adds a concrete new detail such as a specific mechanism, condition, audience, or consequence.
- none: no existing claim states the candidate's core observation.

A broader claim about the same feature area is not coverage. For example, "reporting could be better" does not cover "records with a missing account are not flagged for review"; answer none. Claims that are merely on a related topic are not coverage.

Return JSON only, as {"results":[{"id":"...","coverage":"full|partial|none","matched_existing":number|null,"reason":"one sentence"}]}, with exactly one result per input id. matched_existing is the 1-based number of the closest existing claim, or null for none.

# User

Review field: $field

Items:
$items
