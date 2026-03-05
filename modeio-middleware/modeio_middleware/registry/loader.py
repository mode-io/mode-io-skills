#!/usr/bin/env python3

from __future__ import annotations

from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.registry.resolver import (
    PluginRuntimeSpec,
    RUNTIME_LEGACY,
    RUNTIME_STDIO_JSONRPC,
)
from modeio_middleware.runtime.base import PluginRuntime
from modeio_middleware.runtime.legacy_inprocess import LegacyInprocessRuntime
from modeio_middleware.runtime.stdio_jsonrpc import StdioJsonRpcRuntime


def create_plugin_runtime(spec: PluginRuntimeSpec) -> PluginRuntime:
    if spec.runtime == RUNTIME_LEGACY:
        return LegacyInprocessRuntime(
            plugin_name=spec.name,
            module_path=spec.module_path or "",
        )

    if spec.runtime == RUNTIME_STDIO_JSONRPC:
        if spec.manifest is None:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"plugin '{spec.name}' stdio runtime requires manifest",
                retryable=False,
            )
        return StdioJsonRpcRuntime(
            plugin_name=spec.name,
            command=spec.command,
            manifest=spec.manifest,
            timeout_ms=spec.timeout_ms,
        )

    raise MiddlewareError(
        500,
        "MODEIO_CONFIG_ERROR",
        f"unsupported plugin runtime '{spec.runtime}'",
        retryable=False,
    )
