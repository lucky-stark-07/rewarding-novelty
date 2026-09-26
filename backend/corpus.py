from __future__ import annotations

import json
from pathlib import Path
from .config import get_settings
from .schemas import CorpusEntry

class CorpusStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_settings().corpus_path
    def list(self) -> list[CorpusEntry]:
        if not self.path.exists(): return []
        return [CorpusEntry.model_validate(item) for item in json.loads(self.path.read_text())]
    def replace(self, entries: list[CorpusEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([entry.model_dump(mode="json") for entry in entries], indent=2))
