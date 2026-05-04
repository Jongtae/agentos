from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class CheckpointSaver(Protocol):
    def save_checkpoint(self, payload: dict) -> None:
        ...

    def load_checkpoint(self) -> dict | None:
        ...


class JsonCheckpointSaver:
    def __init__(self, file_path: Path):
        self._path = Path(file_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, payload: dict) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def load_checkpoint(self) -> dict | None:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
