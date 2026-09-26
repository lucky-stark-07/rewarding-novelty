"""Report per-field corpus diversity and deduplicated atomic-claim counts."""
from __future__ import annotations

import argparse
import itertools

import numpy as np

from backend.config import get_settings
from backend.corpus import CorpusStore
from backend.embeddings import cosine_sim, embed
from backend.schemas import FieldName


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=get_settings().high_threshold)
    args = parser.parse_args()
    entries = CorpusStore().list()
    print(f"Corpus submissions: {len(entries)} | covered/dedup threshold: {args.threshold:.2f}")
    for field in FieldName:
        texts = [entry.submission.field_text(field).strip() for entry in entries if entry.submission.field_text(field).strip()]
        if len(texts) < 2:
            print(f"{field.value}: {len(texts)} submission(s); pairwise similarity unavailable")
        else:
            vectors = embed(texts)
            sims = cosine_sim(vectors, vectors)
            pair_values = np.asarray([sims[i, j] for i, j in itertools.combinations(range(len(texts)), 2)])
            mean, maximum = float(pair_values.mean()), float(pair_values.max())
            print(f"{field.value}: n={len(texts)} mean pairwise cosine={mean:.3f} max={maximum:.3f}")
            if mean > 0.8:
                print(f"WARNING: {field.value} corpus appears homogeneous (mean similarity > 0.8).")

    claims = [claim for entry in entries for claim in entry.claims]
    if not claims:
        print("Unique claims at covered threshold: 0 (no extracted claims)")
        return
    vectors = embed([claim.text for claim in claims])
    unique_count = 0
    representatives: dict[FieldName, list[np.ndarray]] = {field: [] for field in FieldName}
    for claim, vector in zip(claims, vectors):
        prior = representatives[claim.field]
        if not prior or float(cosine_sim(vector, np.asarray(prior)).max()) < args.threshold:
            prior.append(vector)
            unique_count += 1
    print(f"Unique claims after dedup at threshold {args.threshold:.2f}: {unique_count} / {len(claims)}")


if __name__ == "__main__":
    main()
