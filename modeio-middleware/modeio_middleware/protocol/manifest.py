#!/usr/bin/env python3

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.protocol.messages import VALID_PROTOCOL_HOOKS
from modeio_middleware.protocol.versions import is_supported_protocol_version

TRANSPORT_STDIO_JSONRPC = "stdio-jsonrpc"
SUPPORTED_TRANSPORTS = {TRANSPORT_STDIO_JSONRPC}

CAPABILITY_KEYS = {
    "can_patch",
    "can_block",
    "needs_network",
    "needs_raw_body",
}


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    protocol_version: str
    transport: str
    hooks: List[str]
    capabilities: Dict[str, bool]
    timeout_ms: Dict[str, int]
    metadata: Dict[str, Any]
    source_path: str


def _require_non_empty_string(payload: Dict[str, Any], key: str, *, source: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"{source}.{key} must be a non-empty string",
            retryable=False,
        )
    return value.strip()


def _normalize_hooks(raw: Any, *, source: str) -> List[str]:
    if not isinstance(raw, list) or not raw:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"{source}.hooks must be a non-empty array",
            retryable=False,
        )

    hooks: List[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"{source}.hooks[{index}] must be a non-empty string",
                retryable=False,
            )
        hook = item.strip()
        if hook not in VALID_PROTOCOL_HOOKS:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"{source}.hooks[{index}] has unsupported hook '{hook}'",
                retryable=False,
            )
        hooks.append(hook)
    return hooks


def _normalize_capabilities(raw: Any, *, source: str) -> Dict[str, bool]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"{source}.capabilities must be an object",
            retryable=False,
        )

    capabilities = {
        "can_patch": False,
        "can_block": False,
        "needs_network": False,
        "needs_raw_body": False,
    }
    for key, value in raw.items():
        if key not in CAPABILITY_KEYS:
            continue
        if not isinstance(value, bool):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"{source}.capabilities.{key} must be boolean",
                retryable=False,
            )
        capabilities[key] = value
    return capabilities


def _normalize_timeout_ms(raw: Any, *, source: str) -> Dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"{source}.timeout_ms must be an object",
            retryable=False,
        )

    timeout_ms: Dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"{source}.timeout_ms keys must be non-empty strings",
                retryable=False,
            )
        if not isinstance(value, int) or value <= 0:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"{source}.timeout_ms.{key} must be a positive integer",
                retryable=False,
            )
        timeout_ms[key.strip()] = int(value)
    return timeout_ms


def load_plugin_manifest(path: Path) -> PluginManifest:
    source = str(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"failed to read plugin manifest: {source}",
            retryable=False,
        ) from error

    try:
        payload = json.loads(raw)
    except ValueError as error:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"invalid JSON plugin manifest: {source}",
            retryable=False,
        ) from error

    if not isinstance(payload, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"plugin manifest root must be an object: {source}",
            retryable=False,
        )

    name = _require_non_empty_string(payload, "name", source=source)
    version = _require_non_empty_string(payload, "version", source=source)
    protocol_version = _require_non_empty_string(payload, "protocol_version", source=source)
    if not is_supported_protocol_version(protocol_version):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"unsupported plugin protocol version '{protocol_version}' in {source}",
            retryable=False,
        )

    transport = _require_non_empty_string(payload, "transport", source=source)
    if transport not in SUPPORTED_TRANSPORTS:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"unsupported plugin transport '{transport}' in {source}",
            retryable=False,
        )

    hooks = _normalize_hooks(payload.get("hooks"), source=source)
    capabilities = _normalize_capabilities(payload.get("capabilities"), source=source)
    timeout_ms = _normalize_timeout_ms(payload.get("timeout_ms"), source=source)
    metadata = payload.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"{source}.metadata must be an object",
            retryable=False,
        )

    return PluginManifest(
        name=name,
        version=version,
        protocol_version=protocol_version,
        transport=transport,
        hooks=hooks,
        capabilities=capabilities,
        timeout_ms=timeout_ms,
        metadata=metadata,
        source_path=source,
    )
