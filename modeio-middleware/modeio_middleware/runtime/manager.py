#!/usr/bin/env python3

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, Tuple

from modeio_middleware.registry.loader import create_plugin_runtime
from modeio_middleware.registry.resolver import PluginRuntimeSpec
from modeio_middleware.runtime.base import PluginRuntime


@dataclass(frozen=True)
class RuntimePoolEntry:
    key: Tuple[str, ...]
    runtime: PluginRuntime


class PluginRuntimeManager:
    """Pool and reuse plugin runtimes across requests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._runtimes: Dict[Tuple[str, ...], PluginRuntime] = {}

    def acquire(self, spec: PluginRuntimeSpec) -> PluginRuntime:
        key = spec.runtime_cache_key()
        with self._lock:
            runtime = self._runtimes.get(key)
            if runtime is not None and not runtime.is_healthy():
                try:
                    runtime.shutdown()
                finally:
                    self._runtimes.pop(key, None)
                runtime = None

            if runtime is None:
                runtime = create_plugin_runtime(spec)
                self._runtimes[key] = runtime

            return runtime

    def shutdown(self) -> None:
        with self._lock:
            items = list(self._runtimes.items())
            self._runtimes.clear()

        for _, runtime in reversed(items):
            try:
                runtime.shutdown()
            except Exception:
                continue
