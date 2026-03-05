#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict

from modeio_middleware.core.errors import MiddlewareError


def validate_plugin_overrides(
    raw: Any,
    *,
    path_prefix: str,
    object_error_message: str,
    error_status: int,
    error_code: str,
    allow_none: bool,
) -> Dict[str, Dict[str, Any]]:
    if raw is None:
        if allow_none:
            return {}
        raise MiddlewareError(error_status, error_code, object_error_message, retryable=False)

    if not isinstance(raw, dict):
        raise MiddlewareError(error_status, error_code, object_error_message, retryable=False)

    overrides: Dict[str, Dict[str, Any]] = {}
    for plugin_name, plugin_override in raw.items():
        if not isinstance(plugin_name, str) or not plugin_name.strip():
            raise MiddlewareError(
                error_status,
                error_code,
                f"{path_prefix} keys must be non-empty strings",
                retryable=False,
            )

        if not isinstance(plugin_override, dict):
            raise MiddlewareError(
                error_status,
                error_code,
                f"{path_prefix}.{plugin_name} must be an object",
                retryable=False,
            )

        if "enabled" in plugin_override and not isinstance(plugin_override["enabled"], bool):
            raise MiddlewareError(
                error_status,
                error_code,
                f"{path_prefix}.{plugin_name}.enabled must be boolean",
                retryable=False,
            )

        if "preset" in plugin_override and (
            not isinstance(plugin_override["preset"], str) or not plugin_override["preset"].strip()
        ):
            raise MiddlewareError(
                error_status,
                error_code,
                f"{path_prefix}.{plugin_name}.preset must be a non-empty string",
                retryable=False,
            )

        if "mode" in plugin_override and (
            not isinstance(plugin_override["mode"], str) or not plugin_override["mode"].strip()
        ):
            raise MiddlewareError(
                error_status,
                error_code,
                f"{path_prefix}.{plugin_name}.mode must be a non-empty string",
                retryable=False,
            )

        if "manifest" in plugin_override and (
            not isinstance(plugin_override["manifest"], str)
            or not plugin_override["manifest"].strip()
        ):
            raise MiddlewareError(
                error_status,
                error_code,
                f"{path_prefix}.{plugin_name}.manifest must be a non-empty string",
                retryable=False,
            )

        if "command" in plugin_override:
            command = plugin_override["command"]
            if not isinstance(command, list) or not command:
                raise MiddlewareError(
                    error_status,
                    error_code,
                    f"{path_prefix}.{plugin_name}.command must be a non-empty array",
                    retryable=False,
                )
            for index, item in enumerate(command):
                if not isinstance(item, str) or not item.strip():
                    raise MiddlewareError(
                        error_status,
                        error_code,
                        f"{path_prefix}.{plugin_name}.command[{index}] must be a non-empty string",
                        retryable=False,
                    )

        if "capabilities_grant" in plugin_override:
            grants = plugin_override["capabilities_grant"]
            if not isinstance(grants, dict):
                raise MiddlewareError(
                    error_status,
                    error_code,
                    f"{path_prefix}.{plugin_name}.capabilities_grant must be an object",
                    retryable=False,
                )
            for cap_key, cap_value in grants.items():
                if not isinstance(cap_key, str) or not cap_key.strip():
                    raise MiddlewareError(
                        error_status,
                        error_code,
                        f"{path_prefix}.{plugin_name}.capabilities_grant keys must be non-empty strings",
                        retryable=False,
                    )
                if not isinstance(cap_value, bool):
                    raise MiddlewareError(
                        error_status,
                        error_code,
                        f"{path_prefix}.{plugin_name}.capabilities_grant.{cap_key} must be boolean",
                        retryable=False,
                    )

        if "timeout_ms" in plugin_override:
            timeout_map = plugin_override["timeout_ms"]
            if not isinstance(timeout_map, dict):
                raise MiddlewareError(
                    error_status,
                    error_code,
                    f"{path_prefix}.{plugin_name}.timeout_ms must be an object",
                    retryable=False,
                )
            for hook_name, timeout_value in timeout_map.items():
                if not isinstance(hook_name, str) or not hook_name.strip():
                    raise MiddlewareError(
                        error_status,
                        error_code,
                        f"{path_prefix}.{plugin_name}.timeout_ms keys must be non-empty strings",
                        retryable=False,
                    )
                if not isinstance(timeout_value, int) or timeout_value <= 0:
                    raise MiddlewareError(
                        error_status,
                        error_code,
                        f"{path_prefix}.{plugin_name}.timeout_ms.{hook_name} must be a positive integer",
                        retryable=False,
                    )

        overrides[plugin_name.strip()] = dict(plugin_override)

    return overrides
