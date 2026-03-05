#!/usr/bin/env python3

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class DeferredActionQueue:
    def __init__(self, path: Optional[str] = None):
        self._path = Path(path).expanduser() if isinstance(path, str) and path.strip() else None
        self._lock = threading.Lock()
        self._items: List[Dict[str, Any]] = []

    def add(self, item: Dict[str, Any]) -> None:
        if not isinstance(item, dict):
            raise ValueError("deferred item must be an object")

        payload = dict(item)
        with self._lock:
            self._items.append(payload)
            if self._path is not None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def list_items(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._items]
