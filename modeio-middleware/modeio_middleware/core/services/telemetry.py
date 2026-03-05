#!/usr/bin/env python3

from __future__ import annotations

import threading
from typing import Any, Dict


class PluginTelemetry:
    def __init__(self):
        self._lock = threading.Lock()
        self._stats: Dict[str, Dict[str, Any]] = {}

    def record(
        self,
        *,
        plugin_name: str,
        hook_name: str,
        action: str,
        duration_ms: float,
        errored: bool,
    ) -> None:
        with self._lock:
            plugin_stats = self._stats.setdefault(
                plugin_name,
                {
                    "calls": 0,
                    "errors": 0,
                    "total_duration_ms": 0.0,
                    "actions": {},
                    "hooks": {},
                },
            )
            plugin_stats["calls"] += 1
            if errored:
                plugin_stats["errors"] += 1
            plugin_stats["total_duration_ms"] += float(duration_ms)

            actions = plugin_stats["actions"]
            actions[action] = actions.get(action, 0) + 1

            hooks = plugin_stats["hooks"]
            hooks[hook_name] = hooks.get(hook_name, 0) + 1

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            snapshot: Dict[str, Dict[str, Any]] = {}
            for plugin_name, raw in self._stats.items():
                snapshot[plugin_name] = {
                    "calls": int(raw.get("calls", 0)),
                    "errors": int(raw.get("errors", 0)),
                    "total_duration_ms": float(raw.get("total_duration_ms", 0.0)),
                    "actions": dict(raw.get("actions", {})),
                    "hooks": dict(raw.get("hooks", {})),
                }
            return snapshot
