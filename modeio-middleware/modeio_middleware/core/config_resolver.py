#!/usr/bin/env python3

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from modeio_middleware.core.errors import MiddlewareError

PresetRegistry = Dict[str, Dict[str, Dict[str, Any]]]


@dataclass(frozen=True)
class ResolvedPluginConfig:
    name: str
    module_path: str
    enabled: bool
    config: Dict[str, Any]


def _validate_preset_name(raw: Any, *, source: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"{source} must be a non-empty string",
            retryable=False,
        )
    return raw.strip().lower()


def _normalize_plugin_preset_map(raw: Any, *, source: str) -> PresetRegistry:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"{source} must be an object",
            retryable=False,
        )

    registry: PresetRegistry = {}
    for plugin_name, presets in raw.items():
        if not isinstance(plugin_name, str) or not plugin_name.strip():
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"{source} plugin keys must be non-empty strings",
                retryable=False,
            )
        if not isinstance(presets, dict):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"{source}.{plugin_name} must be an object",
                retryable=False,
            )

        normalized_plugin_name = plugin_name.strip()
        plugin_presets = registry.setdefault(normalized_plugin_name, {})
        for preset_name, preset_config in presets.items():
            normalized_preset = _validate_preset_name(
                preset_name,
                source=f"{source}.{normalized_plugin_name}",
            )
            if not isinstance(preset_config, dict):
                raise MiddlewareError(
                    500,
                    "MODEIO_CONFIG_ERROR",
                    f"{source}.{normalized_plugin_name}.{normalized_preset} must be an object",
                    retryable=False,
                )
            plugin_presets[normalized_preset] = dict(preset_config)

    return registry


def _merge_registry(base: PresetRegistry, incoming: PresetRegistry) -> PresetRegistry:
    merged: PresetRegistry = {
        plugin_name: {
            preset_name: dict(preset_config)
            for preset_name, preset_config in presets.items()
        }
        for plugin_name, presets in base.items()
    }

    for plugin_name, presets in incoming.items():
        target = merged.setdefault(plugin_name, {})
        for preset_name, preset_config in presets.items():
            current = dict(target.get(preset_name, {}))
            current.update(preset_config)
            target[preset_name] = current

    return merged


def _load_preset_file(path: Path) -> PresetRegistry:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"failed to read preset file: {path}",
            retryable=False,
        ) from error

    try:
        payload = json.loads(raw)
    except ValueError as error:
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"invalid JSON preset file: {path}",
            retryable=False,
        ) from error

    if not isinstance(payload, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"preset file root must be object: {path}",
            retryable=False,
        )

    if "plugins" in payload:
        return _normalize_plugin_preset_map(payload.get("plugins"), source=f"preset file {path.name}.plugins")

    plugin_name = payload.get("plugin")
    presets = payload.get("presets")
    if isinstance(plugin_name, str) and plugin_name.strip() and isinstance(presets, dict):
        return _normalize_plugin_preset_map(
            {
                plugin_name.strip(): presets,
            },
            source=f"preset file {path.name}",
        )

    return _normalize_plugin_preset_map(payload, source=f"preset file {path.name}")


def load_preset_registry(config_payload: Dict[str, Any], *, config_file_path: Path) -> PresetRegistry:
    registry = _normalize_plugin_preset_map(config_payload.get("presets", {}), source="config.presets")

    raw_files = config_payload.get("preset_files", [])
    if raw_files is None:
        raw_files = []
    if not isinstance(raw_files, list):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            "config.preset_files must be an array",
            retryable=False,
        )

    for index, raw_item in enumerate(raw_files):
        if not isinstance(raw_item, str) or not raw_item.strip():
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"config.preset_files[{index}] must be a non-empty string",
                retryable=False,
            )
        path = Path(raw_item.strip())
        if not path.is_absolute():
            path = config_file_path.parent / path
        registry = _merge_registry(registry, _load_preset_file(path))

    return registry


def _normalize_preset_candidate(raw: Any, *, source: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"{source} must be a non-empty string",
            retryable=False,
        )
    return raw.strip().lower()


def resolve_plugin_runtime_config(
    *,
    plugin_name: str,
    plugin_config: Dict[str, Any],
    preset_registry: PresetRegistry,
    profile_override: Dict[str, Any],
    request_override: Dict[str, Any],
) -> ResolvedPluginConfig:
    if not isinstance(plugin_config, dict):
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"plugin '{plugin_name}' config is missing or invalid",
            retryable=False,
        )

    module_path = plugin_config.get("module")
    if not isinstance(module_path, str) or not module_path.strip():
        raise MiddlewareError(
            500,
            "MODEIO_CONFIG_ERROR",
            f"plugin '{plugin_name}' module path is missing",
            retryable=False,
        )

    enabled = bool(plugin_config.get("enabled", False))
    if "enabled" in profile_override:
        enabled = bool(profile_override.get("enabled"))
    if "enabled" in request_override:
        enabled = bool(request_override.get("enabled"))

    base_config: Dict[str, Any] = {
        key: value
        for key, value in plugin_config.items()
        if key not in {"enabled", "module"}
    }

    preset_name = _normalize_preset_candidate(base_config.get("preset"), source=f"plugins.{plugin_name}.preset")
    profile_preset = _normalize_preset_candidate(
        profile_override.get("preset"),
        source=f"profile.plugin_overrides.{plugin_name}.preset",
    )
    request_preset = _normalize_preset_candidate(
        request_override.get("preset"),
        source=f"modeio.plugins.{plugin_name}.preset",
    )

    if profile_preset is not None:
        preset_name = profile_preset
    if request_preset is not None:
        preset_name = request_preset

    merged_config: Dict[str, Any] = dict(base_config)
    if preset_name is not None:
        plugin_presets = preset_registry.get(plugin_name, {})
        preset_config = plugin_presets.get(preset_name)
        if preset_config is None:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"plugin '{plugin_name}' preset '{preset_name}' is not defined",
                retryable=False,
            )
        merged_config.update(dict(preset_config))
        merged_config["preset"] = preset_name

    merged_config.update(
        {
            key: value
            for key, value in profile_override.items()
            if key != "enabled"
        }
    )
    merged_config.update(
        {
            key: value
            for key, value in request_override.items()
            if key != "enabled"
        }
    )

    return ResolvedPluginConfig(
        name=plugin_name,
        module_path=module_path.strip(),
        enabled=enabled,
        config=merged_config,
    )
