from __future__ import annotations

import asyncio
import fcntl
import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
import numpy as np
from .config import get_settings
from .embeddings import normalize_rows, run_embedder
from .schemas import Claim, CorpusEntry, FieldName, Submission


class CorpusStore:
    """JSON file store. Writes are atomic (temp file + rename) and read-modify-write
    operations hold an exclusive flock, so concurrent writers in any process cannot lose entries."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_settings().corpus_path

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(self.path.suffix + ".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def list(self) -> list[CorpusEntry]:
        if not self.path.exists():
            return []
        return [CorpusEntry.model_validate(item) for item in json.loads(self.path.read_text())]

    def _write(self, entries: list[CorpusEntry]) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name, suffix=".tmp")
        with os.fdopen(fd, "w") as handle:
            json.dump([entry.model_dump(mode="json") for entry in entries], handle, indent=2)
        os.replace(tmp, self.path)

    def replace(self, entries: list[CorpusEntry]) -> None:
        with self._locked():
            self._write(entries)

    def append(self, entry: CorpusEntry) -> list[CorpusEntry]:
        with self._locked():
            entries = [*self.list(), entry]
            self._write(entries)
            return entries


def submission_key(submission: Submission) -> tuple[str, ...]:
    return tuple(" ".join(submission.field_text(field).casefold().split()) for field in FieldName)


FIELD_ORDER = list(FieldName)


class CorpusIndex:
    """Every corpus claim embedded once at startup into one L2-normalised (N × d) matrix.

    Nearest-neighbour search for all of a submission's claims is a single matmul, with other
    fields masked out. Accepted submissions are appended incrementally."""

    def __init__(self, store: CorpusStore, embedder: Callable[[list[str]], np.ndarray], reference_text: str | None = None) -> None:
        self.store = store
        self.embedder = embedder
        self.reference_text = reference_text
        self.reference_vector: np.ndarray | None = None
        self.entries: list[CorpusEntry] = []
        self.claims: list[Claim] = []
        self.matrix: np.ndarray | None = None
        self.field_ids = np.empty(0, dtype=np.int8)
        self._keys: dict[tuple[str, ...], CorpusEntry] = {}
        self._write_lock = asyncio.Lock()

    @classmethod
    async def create(cls, store: CorpusStore, embedder: Callable[[list[str]], np.ndarray], reference_text: str | None = None) -> CorpusIndex:
        index = cls(store, embedder, reference_text)
        if reference_text:
            index.reference_vector = normalize_rows(await run_embedder(embedder, [reference_text]))[0]
        await index.reload()
        return index

    async def embed(self, texts: list[str]) -> np.ndarray:
        """One encode call for all texts, off the event loop; rows are L2-normalised."""
        return normalize_rows(await run_embedder(self.embedder, texts))

    async def reload(self) -> None:
        entries = await asyncio.to_thread(self.store.list)
        await self._rebuild(entries)

    async def _rebuild(self, entries: list[CorpusEntry]) -> None:
        claims = [claim for entry in entries for claim in entry.claims]
        matrix = await self.embed([claim.text for claim in claims]) if claims else None
        self.entries, self.claims, self.matrix = entries, claims, matrix
        self.field_ids = np.array([FIELD_ORDER.index(claim.field) for claim in claims], dtype=np.int8)
        self._keys = {submission_key(entry.submission): entry for entry in entries}

    def find_duplicate(self, submission: Submission) -> CorpusEntry | None:
        return self._keys.get(submission_key(submission))

    def search(self, vectors: np.ndarray, fields: list[FieldName], k: int) -> list[list[tuple[Claim, float]]]:
        """Top-k same-field neighbours for each row of `vectors` (already normalised)."""
        if self.matrix is None or not fields:
            return [[] for _ in fields]
        similarities = vectors @ self.matrix.T
        wanted = np.array([FIELD_ORDER.index(field) for field in fields], dtype=np.int8)
        similarities = np.where(self.field_ids[None, :] == wanted[:, None], similarities, -np.inf)
        results = []
        for row in similarities:
            top = [int(i) for i in np.argsort(-row)[:k] if np.isfinite(row[int(i)])]
            results.append([(self.claims[i], float(row[i])) for i in top])
        return results

    def neighbors(self, field: FieldName, vector: np.ndarray, k: int) -> list[tuple[Claim, float]]:
        return self.search(normalize_rows(vector), [field], k)[0]

    @property
    def claim_count(self) -> int:
        return len(self.claims)

    async def add(self, entry: CorpusEntry) -> None:
        async with self._write_lock:
            if self.find_duplicate(entry.submission):
                return
            await asyncio.to_thread(self.store.append, entry)
            if entry.claims:
                new_vectors = await self.embed([claim.text for claim in entry.claims])
                self.matrix = new_vectors if self.matrix is None else np.vstack([self.matrix, new_vectors])
                self.field_ids = np.concatenate([self.field_ids, np.array([FIELD_ORDER.index(claim.field) for claim in entry.claims], dtype=np.int8)])
                self.claims = [*self.claims, *entry.claims]
            self.entries = [*self.entries, entry]
            self._keys[submission_key(entry.submission)] = entry

    async def replace(self, entries: list[CorpusEntry]) -> None:
        async with self._write_lock:
            await asyncio.to_thread(self.store.replace, entries)
            await self._rebuild(entries)
