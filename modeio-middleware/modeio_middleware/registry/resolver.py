#!/usr/bin/env python3

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from modeio_middleware.core.config_resolver import ResolvedPluginConfig
from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.protocol.manifest import PluginManifest, load_plugin_manifest
from modeio_middleware.protocol.messages import INTERNAL_TO_PROTOCOL_HOOK

RUNTIME_LEGACY = "legacy_inprocess"
RUNTIME_STDIO_JSONRPC = "stdio_jsonrpc"
SUPPORTED_RUNTIMES = {RUNTIME_LEGACY, RUNTIME_STDIO_JSONRPC}

MODE_OBSERVE = "observe"
MODE_ASSIST = "assist"
MODE_ENFORCE = "enforce"
VALID_MODES = {MODE_OBSERVE, MODE_ASSIST, MODE_ENFORCE}


@dataclass(frozen=True)
class PluginRuntimeSpec:
    name: str
    runtime: str
    mode: str
    module_path: Optional[str]
    command: List[str]
    manifest: Optional[PluginManifest]
    capabilities: Dict[str, bool]
    timeout_ms: Dict[str, int]
    pool_size: int
    hook_config: Dict[str, Any]
    supported_hooks: List[str]

    def runtime_cache_key(self) -> tuple[str, ...]:
        manifest_key: Dict[str, Any] = {}
        if self.manifest is not None:
            manifest_key = {
                "source_path": self.manifest.source_path,
                "name": self.manifest.name,
                "version": self.manifest.version,
                "protocol_version": self.manifest.protocol_version,
                "transport": self.manifest.transport,
                "hooks": list(self.manifest.hooks),
                "capabilities": dict(self.manifest.capabilities),
                "timeout_ms": dict(self.manifest.timeout_ms),
            }

        fingerprint = {
            "runtime": self.runtime,
            "name": self.name,
            "mode": self.mode,
            "module_path": self.module_path or "",
            "command": list(self.command),
            "manifest": manifest_key,
            "capabilities": dict(self.capabilities),
            "timeout_ms": dict(self.timeout_ms),
            "pool_size": self.pool_size,
            "hook_config": dict(self.hook_config),
            "supported_hooks": list(self.supported_hooks),
        }
        return (
            self.runtime,
            self.name,
            json.dumps(fingerprint, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        )


def _normalize_mode(raw: Any, *, runtime: str) -> str:
    if raw is None:
        if runtime == RUNTIME_STDIO_JSONRPC:
            return MODE_OBSERVE
        return MODE_ENFORCE

    value = str(raw).strip().lower()
    if value not in VALID_MODES:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"plugin mode must be one of: {', '.join(sorted(VALID_MODES))}",
            retryable=False,
        )
    return value


def _resolve_manifest(path_raw: Any, *, config_base_dir: Path) -> PluginManifest:
    if not isinstance(path_raw, str) or not path_raw.strip():
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            "stdio_jsonrpc plugin requires non-empty 'manifest' path",
            retryable=False,
        )

    path = Path(path_raw.strip())
    if not path.is_absolute():
        path = config_base_dir / path
    return load_plugin_manifest(path)


def _resolve_command(raw: Any, *, config_base_dir: Path) -> List[str]:
    if not isinstance(raw, list) or not raw:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            "stdio_jsonrpc plugin requires non-empty 'command' array",
            retryable=False,
        )

    command: List[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"stdio_jsonrpc plugin command[{index}] must be a non-empty string",
                retryable=False,
            )
        value = item.strip()
        candidate = Path(value)
        if not candidate.is_absolute():
            resolved_candidate = (config_base_dir / candidate).resolve()
            if resolved_candidate.exists():
                value = str(resolved_candidate)
        command.append(value)
    return command


def _resolve_pool_size(raw: Any, *, runtime: str) -> int:
    if raw is None:
        return 1
    if not isinstance(raw, int) or raw <= 0:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"{runtime} plugin pool_size must be a positive integer",
            retryable=False,
        )
    return int(raw)


def _resolve_capabilities(
    *,
    runtime: str,
    manifest: Optional[PluginManifest],
    grant_raw: Any,
) -> Dict[str, bool]:
    if runtime == RUNTIME_LEGACY:
        return {
            "can_patch": True,
            "can_block": True,
        }

    if not isinstance(grant_raw, dict):
        grant_raw = {}

    manifest_caps = manifest.capabilities if manifest is not None else {}
    capabilities = {
        "can_patch": bool(manifest_caps.get("can_patch", False)) and bool(grant_raw.get("can_patch", False)),
        "can_block": bool(manifest_caps.get("can_block", False)) and bool(grant_raw.get("can_block", False)),
    }
    return capabilities


def _sanitize_hook_config(raw: Dict[str, Any], runtime: str) -> Dict[str, Any]:
    reserved = {
        "mode",
        "capabilities_grant",
        "timeout_ms",
        "pool_size",
    }
    if runtime == RUNTIME_STDIO_JSONRPC:
        reserved.update({"command", "manifest"})
    return {
        key: value
        for key, value in raw.items()
        if key not in reserved
    }


def resolve_plugin_runtime_spec(
    *,
    resolved: ResolvedPluginConfig,
    config_base_dir: Path,
) -> PluginRuntimeSpec:
    runtime = resolved.runtime
    if runtime not in SUPPORTED_RUNTIMES:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"plugin '{resolved.name}' runtime '{runtime}' is not supported",
            retryable=False,
        )

    mode = _normalize_mode(resolved.config.get("mode"), runtime=runtime)
    timeout_ms_raw = resolved.config.get("timeout_ms", {})
    if timeout_ms_raw is None:
        timeout_ms_raw = {}
    if not isinstance(timeout_ms_raw, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"plugin '{resolved.name}' timeout_ms must be an object",
            retryable=False,
        )
    timeout_ms = {
        str(key): int(value)
        for key, value in timeout_ms_raw.items()
        if isinstance(key, str) and key.strip() and isinstance(value, int) and value > 0
    }
    pool_size = _resolve_pool_size(resolved.config.get("pool_size"), runtime=runtime)

    if runtime == RUNTIME_LEGACY:
        if not isinstance(resolved.module_path, str) or not resolved.module_path.strip():
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"plugin '{resolved.name}' runtime '{runtime}' requires module path",
                retryable=False,
            )
        return PluginRuntimeSpec(
            name=resolved.name,
            runtime=runtime,
            mode=mode,
            module_path=resolved.module_path.strip(),
            command=[],
            manifest=None,
            capabilities=_resolve_capabilities(
                runtime=runtime,
                manifest=None,
                grant_raw=resolved.config.get("capabilities_grant", {}),
            ),
            timeout_ms=timeout_ms,
            pool_size=pool_size,
            hook_config=_sanitize_hook_config(resolved.config, runtime),
            supported_hooks=list(INTERNAL_TO_PROTOCOL_HOOK.keys()),
        )

    manifest = _resolve_manifest(resolved.config.get("manifest"), config_base_dir=config_base_dir)
    command = _resolve_command(resolved.config.get("command"), config_base_dir=config_base_dir)

    supported_hooks = [
        internal
        for internal, protocol_hook in INTERNAL_TO_PROTOCOL_HOOK.items()
        if protocol_hook in set(manifest.hooks)
    ]

    return PluginRuntimeSpec(
        name=resolved.name,
        runtime=runtime,
        mode=mode,
        module_path=None,
        command=command,
        manifest=manifest,
        capabilities=_resolve_capabilities(
            runtime=runtime,
            manifest=manifest,
            grant_raw=resolved.config.get("capabilities_grant", {}),
        ),
        timeout_ms=timeout_ms,
        pool_size=pool_size,
        hook_config=_sanitize_hook_config(resolved.config, runtime),
        supported_hooks=supported_hooks,
    )
