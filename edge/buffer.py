from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import List


class DiskBuffer:
    def __init__(self, path: str = "buffer/offline_queue.jsonl") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def enqueue(self, payload: dict) -> None:
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")

    def drain(self) -> List[dict]:
        with self._lock:
            if not self._path.exists():
                return []
            lines = self._path.read_text(encoding="utf-8").splitlines()
            records: List[dict] = []
            for line in lines:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            self._path.write_text("", encoding="utf-8")
            return records

    def size(self) -> int:
        with self._lock:
            if not self._path.exists():
                return 0
            return sum(1 for _ in self._path.open("r"))

    def clear(self) -> None:
        with self._lock:
            self._path.write_text("", encoding="utf-8")
