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
from .embeddings import cosine_sim
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


class CorpusIndex:
    """Corpus claims with their embeddings, held in memory per field and built once at startup.

    Scoring only embeds the new claims; corpus vectors are reused across requests and updated
    incrementally when an accepted submission is appended."""

    def __init__(self, store: CorpusStore, embedder: Callable[[list[str]], np.ndarray]) -> None:
        self.store = store
        self.embedder = embedder
        self.entries: list[CorpusEntry] = []
        self.claims: dict[FieldName, list[Claim]] = {field: [] for field in FieldName}
        self.vectors: dict[FieldName, np.ndarray | None] = {field: None for field in FieldName}
        self._keys: dict[tuple[str, ...], CorpusEntry] = {}
        self._write_lock = asyncio.Lock()

    @classmethod
    async def create(cls, store: CorpusStore, embedder: Callable[[list[str]], np.ndarray]) -> CorpusIndex:
        index = cls(store, embedder)
        await index.reload()
        return index

    async def reload(self) -> None:
        entries = await asyncio.to_thread(self.store.list)
        await self._rebuild(entries)

    async def _rebuild(self, entries: list[CorpusEntry]) -> None:
        claims = {field: [claim for entry in entries for claim in entry.claims if claim.field == field] for field in FieldName}
        texts = [claim.text for field in FieldName for claim in claims[field]]
        matrix = await asyncio.to_thread(self.embedder, texts) if texts else None
        vectors: dict[FieldName, np.ndarray | None] = {}
        offset = 0
        for field in FieldName:
            count = len(claims[field])
            vectors[field] = matrix[offset:offset + count] if matrix is not None and count else None
            offset += count
        self.entries, self.claims, self.vectors = entries, claims, vectors
        self._keys = {submission_key(entry.submission): entry for entry in entries}

    def find_duplicate(self, submission: Submission) -> CorpusEntry | None:
        return self._keys.get(submission_key(submission))

    def neighbors(self, field: FieldName, vector: np.ndarray, k: int) -> list[tuple[Claim, float]]:
        matrix = self.vectors[field]
        if matrix is None:
            return []
        similarities = cosine_sim(vector, matrix)[0]
        top = np.argsort(-similarities)[:k]
        return [(self.claims[field][int(i)], float(similarities[int(i)])) for i in top]

    @property
    def claim_count(self) -> int:
        return sum(len(items) for items in self.claims.values())

    async def add(self, entry: CorpusEntry) -> None:
        async with self._write_lock:
            if self.find_duplicate(entry.submission):
                return
            await asyncio.to_thread(self.store.append, entry)
            new_vectors = await asyncio.to_thread(self.embedder, [claim.text for claim in entry.claims]) if entry.claims else None
            for field in FieldName:
                rows = [i for i, claim in enumerate(entry.claims) if claim.field == field]
                if not rows or new_vectors is None:
                    continue
                current = self.vectors[field]
                self.vectors[field] = new_vectors[rows] if current is None else np.vstack([current, new_vectors[rows]])
                self.claims[field] = [*self.claims[field], *(entry.claims[i] for i in rows)]
            self.entries = [*self.entries, entry]
            self._keys[submission_key(entry.submission)] = entry

    async def replace(self, entries: list[CorpusEntry]) -> None:
        async with self._write_lock:
            await asyncio.to_thread(self.store.replace, entries)
            await self._rebuild(entries)
