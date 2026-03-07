#!/usr/bin/env python3

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Tuple

from modeio_middleware.registry.loader import create_plugin_runtime
from modeio_middleware.registry.resolver import PluginRuntimeSpec
from modeio_middleware.runtime.base import PluginRuntime


@dataclass
class RuntimePoolEntry:
    key: Tuple[str, ...]
    runtime: PluginRuntime
    in_use: int = 0


class PluginRuntimeLease:
    def __init__(self, *, manager: "PluginRuntimeManager", key: Tuple[str, ...], entry: RuntimePoolEntry):
        self._manager = manager
        self._key = key
        self._entry = entry
        self._released = False

    @property
    def runtime(self) -> PluginRuntime:
        return self._entry.runtime

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._manager.release(self._key, self._entry)


class PluginRuntimeManager:
    """Pool and reuse plugin runtimes across requests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._runtimes: Dict[Tuple[str, ...], List[RuntimePoolEntry]] = {}
        self._next_index: Dict[Tuple[str, ...], int] = {}

    def acquire(self, spec: PluginRuntimeSpec) -> PluginRuntimeLease:
        key = spec.runtime_cache_key()
        with self._lock:
            entries = self._runtimes.setdefault(key, [])

            healthy_entries: List[RuntimePoolEntry] = []
            for entry in entries:
                if entry.runtime.is_healthy():
                    healthy_entries.append(entry)
                    continue
                try:
                    entry.runtime.shutdown()
                except Exception:
                    pass
            if len(healthy_entries) != len(entries):
                self._runtimes[key] = healthy_entries
                entries = healthy_entries

            idle_entry = next((entry for entry in entries if entry.in_use == 0), None)
            if idle_entry is None and len(entries) < spec.pool_size:
                idle_entry = RuntimePoolEntry(
                    key=key,
                    runtime=create_plugin_runtime(spec),
                )
                entries.append(idle_entry)

            if idle_entry is None:
                if not entries:
                    idle_entry = RuntimePoolEntry(
                        key=key,
                        runtime=create_plugin_runtime(spec),
                    )
                    entries.append(idle_entry)
                else:
                    index = self._next_index.get(key, 0) % len(entries)
                    idle_entry = entries[index]
                    self._next_index[key] = index + 1

            idle_entry.in_use += 1
            return PluginRuntimeLease(manager=self, key=key, entry=idle_entry)

    def release(self, key: Tuple[str, ...], entry: RuntimePoolEntry) -> None:
        with self._lock:
            entries = self._runtimes.get(key)
            if not entries:
                return
            for current in entries:
                if current is entry and current.in_use > 0:
                    current.in_use -= 1
                    break

    def shutdown(self) -> None:
        with self._lock:
            items = [
                entry.runtime
                for entries in self._runtimes.values()
                for entry in entries
            ]
            self._runtimes.clear()
            self._next_index.clear()

        for runtime in reversed(items):
            try:
                runtime.shutdown()
            except Exception:
                continue
