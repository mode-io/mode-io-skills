#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.core.profiles import normalize_profile_name

HOOK_ACTION_ALLOW = "allow"
HOOK_ACTION_MODIFY = "modify"
HOOK_ACTION_BLOCK = "block"
HOOK_ACTION_WARN = "warn"
VALID_HOOK_ACTIONS = {
    HOOK_ACTION_ALLOW,
    HOOK_ACTION_MODIFY,
    HOOK_ACTION_BLOCK,
    HOOK_ACTION_WARN,
}


@dataclass(frozen=True)
class ModeioOptions:
    profile: str
    on_plugin_error: Optional[str]
    plugin_overrides: Dict[str, Dict[str, Any]]


def validate_chat_payload(body: Dict[str, Any]) -> None:
    if not isinstance(body, dict):
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "request body must be a JSON object")

    model = body.get("model")
    if not isinstance(model, str) or not model.strip():
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "field 'model' must be a non-empty string")

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "field 'messages' must be a non-empty array")

    if body.get("stream") is True:
        raise MiddlewareError(
            400,
            "MODEIO_UNSUPPORTED_STREAMING",
            "stream=true is not supported by modeio-middleware v1",
        )


def normalize_modeio_options(
    body: Dict[str, Any],
    *,
    default_profile: str,
) -> ModeioOptions:
    raw = body.pop("modeio", None)
    if raw is None:
        return ModeioOptions(
            profile=default_profile,
            on_plugin_error=None,
            plugin_overrides={},
        )

    if not isinstance(raw, dict):
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "field 'modeio' must be an object")

    profile = normalize_profile_name(raw.get("profile"), default_profile=default_profile)

    on_plugin_error_raw = raw.get("on_plugin_error")
    on_plugin_error: Optional[str] = None
    if on_plugin_error_raw is not None:
        if not isinstance(on_plugin_error_raw, str) or not on_plugin_error_raw.strip():
            raise MiddlewareError(
                400,
                "MODEIO_VALIDATION_ERROR",
                "field 'modeio.on_plugin_error' must be a non-empty string",
            )
        on_plugin_error = on_plugin_error_raw.strip().lower()

    overrides_raw = raw.get("plugins", {})
    if not isinstance(overrides_raw, dict):
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "field 'modeio.plugins' must be an object")

    plugin_overrides: Dict[str, Dict[str, Any]] = {}
    for plugin_name, plugin_override in overrides_raw.items():
        if not isinstance(plugin_name, str) or not plugin_name.strip():
            raise MiddlewareError(
                400,
                "MODEIO_VALIDATION_ERROR",
                "modeio.plugins keys must be non-empty strings",
            )
        if not isinstance(plugin_override, dict):
            raise MiddlewareError(
                400,
                "MODEIO_VALIDATION_ERROR",
                f"modeio.plugins.{plugin_name} must be an object",
            )
        if "enabled" in plugin_override and not isinstance(plugin_override["enabled"], bool):
            raise MiddlewareError(
                400,
                "MODEIO_VALIDATION_ERROR",
                f"modeio.plugins.{plugin_name}.enabled must be boolean",
            )
        plugin_overrides[plugin_name.strip()] = dict(plugin_override)

    return ModeioOptions(
        profile=profile,
        on_plugin_error=on_plugin_error,
        plugin_overrides=plugin_overrides,
    )
