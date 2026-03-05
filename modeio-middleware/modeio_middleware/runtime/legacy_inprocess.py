#!/usr/bin/env python3

from __future__ import annotations

import importlib
from typing import Any, Dict

from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.plugins.base import MiddlewarePlugin
from modeio_middleware.runtime.base import PluginRuntime


class LegacyInprocessRuntime(PluginRuntime):
    runtime_name = "legacy_inprocess"

    def __init__(self, *, plugin_name: str, module_path: str):
        self.plugin_name = plugin_name
        self.module_path = module_path
        self._plugin = self._instantiate_plugin(plugin_name, module_path)

    def _instantiate_plugin(self, name: str, module_path: str) -> MiddlewarePlugin:
        try:
            module = importlib.import_module(module_path)
        except Exception as error:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"failed to import plugin '{name}' module '{module_path}'",
                details={"plugin": name, "module": module_path},
            ) from error

        plugin_cls = getattr(module, "Plugin", None)
        if plugin_cls is None:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"plugin '{name}' module '{module_path}' missing Plugin class",
                details={"plugin": name, "module": module_path},
            )

        plugin = plugin_cls()
        if not isinstance(plugin, MiddlewarePlugin):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"plugin '{name}' must inherit MiddlewarePlugin",
                details={"plugin": name, "module": module_path},
            )
        return plugin

    def invoke(self, hook_name: str, hook_input: Dict[str, Any]) -> Any:
        hook = getattr(self._plugin, hook_name, None)
        if not callable(hook):
            raise ValueError(f"plugin '{self.plugin_name}' missing hook '{hook_name}'")
        return hook(hook_input)
