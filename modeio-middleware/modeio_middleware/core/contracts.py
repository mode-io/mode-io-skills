#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.core.plugin_overrides import validate_plugin_overrides
from modeio_middleware.core.profiles import normalize_profile_name

ENDPOINT_CHAT_COMPLETIONS = "chat_completions"
ENDPOINT_RESPONSES = "responses"

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


def _require_non_empty_string(body: Dict[str, Any], field_name: str) -> str:
    value = body.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise MiddlewareError(
            400,
            "MODEIO_VALIDATION_ERROR",
            f"field '{field_name}' must be a non-empty string",
        )
    return value


def _normalize_stream_flag(body: Dict[str, Any]) -> bool:
    if "stream" not in body:
        return False
    stream_value = body.get("stream")
    if not isinstance(stream_value, bool):
        raise MiddlewareError(
            400,
            "MODEIO_VALIDATION_ERROR",
            "field 'stream' must be boolean",
        )
    return stream_value


def validate_chat_payload(body: Dict[str, Any]) -> bool:
    if not isinstance(body, dict):
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "request body must be a JSON object")

    _require_non_empty_string(body, "model")

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "field 'messages' must be a non-empty array")

    return _normalize_stream_flag(body)


def validate_responses_payload(body: Dict[str, Any]) -> bool:
    if not isinstance(body, dict):
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "request body must be a JSON object")

    _require_non_empty_string(body, "model")

    if "input" not in body:
        raise MiddlewareError(
            400,
            "MODEIO_VALIDATION_ERROR",
            "field 'input' is required for /v1/responses",
        )

    input_value = body.get("input")
    if not isinstance(input_value, (str, list, dict)):
        raise MiddlewareError(
            400,
            "MODEIO_VALIDATION_ERROR",
            "field 'input' must be a string, array, or object",
        )

    return _normalize_stream_flag(body)


def validate_endpoint_payload(endpoint_kind: str, body: Dict[str, Any]) -> bool:
    if endpoint_kind == ENDPOINT_CHAT_COMPLETIONS:
        return validate_chat_payload(body)
    if endpoint_kind == ENDPOINT_RESPONSES:
        return validate_responses_payload(body)
    raise MiddlewareError(
        500,
        "MODEIO_INTERNAL_ERROR",
        f"unsupported endpoint kind '{endpoint_kind}'",
        retryable=False,
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

    plugin_overrides = validate_plugin_overrides(
        raw.get("plugins", {}),
        path_prefix="modeio.plugins",
        object_error_message="field 'modeio.plugins' must be an object",
        error_status=400,
        error_code="MODEIO_VALIDATION_ERROR",
        allow_none=False,
    )

    return ModeioOptions(
        profile=profile,
        on_plugin_error=on_plugin_error,
        plugin_overrides=plugin_overrides,
    )
