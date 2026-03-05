#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict, List, Optional

from modeio_middleware.core.errors import MiddlewareError

DEFAULT_PROFILE = "dev"
ALLOWED_PLUGIN_ERROR_POLICIES = {"fail_open", "warn", "fail_safe"}


def normalize_profile_name(raw: Optional[str], *, default_profile: str = DEFAULT_PROFILE) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return default_profile
    return value


def resolve_profile(profiles: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    if not isinstance(profiles, dict) or not profiles:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            "middleware profiles config is missing or invalid",
            retryable=False,
        )
    if profile_name not in profiles:
        raise MiddlewareError(
            400,
            "MODEIO_VALIDATION_ERROR",
            f"unknown modeio.profile '{profile_name}'",
            retryable=False,
            details={"field": "modeio.profile", "profile": profile_name},
        )
    profile = profiles[profile_name]
    if not isinstance(profile, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"profile '{profile_name}' must be an object",
            retryable=False,
        )
    return profile


def resolve_plugin_error_policy(profile_config: Dict[str, Any], override: Optional[str]) -> str:
    if override is not None:
        candidate = str(override).strip().lower()
    else:
        candidate = str(profile_config.get("on_plugin_error", "warn")).strip().lower()

    if candidate not in ALLOWED_PLUGIN_ERROR_POLICIES:
        raise MiddlewareError(
            400,
            "MODEIO_VALIDATION_ERROR",
            f"unsupported on_plugin_error policy '{candidate}'",
            retryable=False,
            details={"field": "modeio.on_plugin_error"},
        )
    return candidate


def resolve_profile_plugins(profile_config: Dict[str, Any]) -> List[str]:
    plugins = profile_config.get("plugins", [])
    if not isinstance(plugins, list):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            "profile.plugins must be an array",
            retryable=False,
        )

    resolved: List[str] = []
    for index, plugin_name in enumerate(plugins):
        if not isinstance(plugin_name, str) or not plugin_name.strip():
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"profile.plugins[{index}] must be a non-empty string",
                retryable=False,
            )
        resolved.append(plugin_name.strip())
    return resolved


def resolve_profile_plugin_overrides(profile_config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = profile_config.get("plugin_overrides", {})
    if raw is None:
        return {}

    if not isinstance(raw, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            "profile.plugin_overrides must be an object",
            retryable=False,
        )

    overrides: Dict[str, Dict[str, Any]] = {}
    for plugin_name, plugin_override in raw.items():
        if not isinstance(plugin_name, str) or not plugin_name.strip():
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                "profile.plugin_overrides keys must be non-empty strings",
                retryable=False,
            )
        if not isinstance(plugin_override, dict):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"profile.plugin_overrides.{plugin_name} must be an object",
                retryable=False,
            )
        if "enabled" in plugin_override and not isinstance(plugin_override["enabled"], bool):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"profile.plugin_overrides.{plugin_name}.enabled must be boolean",
                retryable=False,
            )
        if "preset" in plugin_override and (
            not isinstance(plugin_override["preset"], str)
            or not plugin_override["preset"].strip()
        ):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"profile.plugin_overrides.{plugin_name}.preset must be a non-empty string",
                retryable=False,
            )
        if "mode" in plugin_override and (
            not isinstance(plugin_override["mode"], str)
            or not plugin_override["mode"].strip()
        ):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"profile.plugin_overrides.{plugin_name}.mode must be a non-empty string",
                retryable=False,
            )
        if "manifest" in plugin_override and (
            not isinstance(plugin_override["manifest"], str)
            or not plugin_override["manifest"].strip()
        ):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"profile.plugin_overrides.{plugin_name}.manifest must be a non-empty string",
                retryable=False,
            )
        if "command" in plugin_override:
            command = plugin_override["command"]
            if not isinstance(command, list) or not command:
                raise MiddlewareError(
                    500,
                    "MODEIO_CONFIG_ERROR",
                    f"profile.plugin_overrides.{plugin_name}.command must be a non-empty array",
                    retryable=False,
                )
            for index, item in enumerate(command):
                if not isinstance(item, str) or not item.strip():
                    raise MiddlewareError(
                        500,
                        "MODEIO_CONFIG_ERROR",
                        f"profile.plugin_overrides.{plugin_name}.command[{index}] must be a non-empty string",
                        retryable=False,
                    )
        if "capabilities_grant" in plugin_override:
            grants = plugin_override["capabilities_grant"]
            if not isinstance(grants, dict):
                raise MiddlewareError(
                    500,
                    "MODEIO_CONFIG_ERROR",
                    f"profile.plugin_overrides.{plugin_name}.capabilities_grant must be an object",
                    retryable=False,
                )
            for cap_key, cap_value in grants.items():
                if not isinstance(cap_key, str) or not cap_key.strip():
                    raise MiddlewareError(
                        500,
                        "MODEIO_CONFIG_ERROR",
                        f"profile.plugin_overrides.{plugin_name}.capabilities_grant keys must be non-empty strings",
                        retryable=False,
                    )
                if not isinstance(cap_value, bool):
                    raise MiddlewareError(
                        500,
                        "MODEIO_CONFIG_ERROR",
                        f"profile.plugin_overrides.{plugin_name}.capabilities_grant.{cap_key} must be boolean",
                        retryable=False,
                    )
        if "timeout_ms" in plugin_override:
            timeout_map = plugin_override["timeout_ms"]
            if not isinstance(timeout_map, dict):
                raise MiddlewareError(
                    500,
                    "MODEIO_CONFIG_ERROR",
                    f"profile.plugin_overrides.{plugin_name}.timeout_ms must be an object",
                    retryable=False,
                )
            for hook_name, timeout_value in timeout_map.items():
                if not isinstance(hook_name, str) or not hook_name.strip():
                    raise MiddlewareError(
                        500,
                        "MODEIO_CONFIG_ERROR",
                        f"profile.plugin_overrides.{plugin_name}.timeout_ms keys must be non-empty strings",
                        retryable=False,
                    )
                if not isinstance(timeout_value, int) or timeout_value <= 0:
                    raise MiddlewareError(
                        500,
                        "MODEIO_CONFIG_ERROR",
                        f"profile.plugin_overrides.{plugin_name}.timeout_ms.{hook_name} must be a positive integer",
                        retryable=False,
                    )
        overrides[plugin_name.strip()] = dict(plugin_override)

    return overrides
