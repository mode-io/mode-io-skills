#!/usr/bin/env python3

from __future__ import annotations

import copy
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from modeio_middleware.cli.setup_lib.common import (
    SetupError,
    detect_os_name,
    ensure_object,
    normalize_gateway_base_url,
    read_json_file,
    utc_timestamp,
    write_json_file,
)


def default_opencode_config_path(
    *,
    os_name: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    home: Optional[Path] = None,
) -> Path:
    resolved_env = env or os.environ
    resolved_home = home or Path.home()
    system_name = detect_os_name(os_name)

    if system_name == "windows":
        app_data = resolved_env.get("APPDATA", "").strip()
        if app_data:
            return Path(app_data) / "opencode" / "opencode.json"
        return resolved_home / "AppData" / "Roaming" / "opencode" / "opencode.json"

    if system_name == "darwin":
        return resolved_home / ".config" / "opencode" / "opencode.json"

    xdg_home = resolved_env.get("XDG_CONFIG_HOME", "").strip()
    if xdg_home:
        return Path(xdg_home) / "opencode" / "opencode.json"
    return resolved_home / ".config" / "opencode" / "opencode.json"


def apply_opencode_base_url(config: Dict[str, Any], gateway_base_url: str) -> Tuple[Dict[str, Any], bool]:
    updated = copy.deepcopy(config)
    provider_obj = ensure_object(updated.get("provider"), "provider")
    openai_obj = ensure_object(provider_obj.get("openai"), "provider.openai")
    options_obj = ensure_object(openai_obj.get("options"), "provider.openai.options")

    normalized = normalize_gateway_base_url(gateway_base_url)
    current_base_url = options_obj.get("baseURL")
    changed = current_base_url != normalized

    options_obj["baseURL"] = normalized
    openai_obj["options"] = options_obj
    provider_obj["openai"] = openai_obj
    updated["provider"] = provider_obj
    return updated, changed


def remove_opencode_base_url(
    config: Dict[str, Any],
    gateway_base_url: str,
    *,
    force_remove: bool,
) -> Tuple[Dict[str, Any], bool, Optional[str], str]:
    updated = copy.deepcopy(config)

    provider_obj = updated.get("provider")
    if not isinstance(provider_obj, dict):
        return updated, False, None, "provider_missing"

    openai_obj = provider_obj.get("openai")
    if not isinstance(openai_obj, dict):
        return updated, False, None, "openai_provider_missing"

    options_obj = openai_obj.get("options")
    if not isinstance(options_obj, dict):
        return updated, False, None, "openai_options_missing"

    raw_base_url = options_obj.get("baseURL")
    if not isinstance(raw_base_url, str) or not raw_base_url.strip():
        return updated, False, None, "base_url_not_set"

    normalized_target = normalize_gateway_base_url(gateway_base_url)
    normalized_current = raw_base_url.rstrip("/")

    if not force_remove and normalized_current != normalized_target:
        return updated, False, raw_base_url, "base_url_mismatch"

    del options_obj["baseURL"]
    openai_obj["options"] = options_obj
    provider_obj["openai"] = openai_obj
    updated["provider"] = provider_obj
    return updated, True, raw_base_url, "removed"


def apply_opencode_config_file(
    *,
    config_path: Path,
    gateway_base_url: str,
    create_if_missing: bool,
) -> Dict[str, Any]:
    existed = config_path.exists()
    if not existed and not create_if_missing:
        raise SetupError(
            f"OpenCode config not found: {config_path}. Use --create-opencode-config to create it."
        )

    config_data: Dict[str, Any] = {}
    if existed:
        config_data = read_json_file(config_path)

    updated, changed = apply_opencode_base_url(config_data, gateway_base_url)
    backup_path = None
    if changed:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if existed:
            backup_path = config_path.with_name(f"{config_path.name}.bak.{utc_timestamp()}")
            shutil.copy2(config_path, backup_path)
        write_json_file(config_path, updated)

    return {
        "path": str(config_path),
        "changed": changed,
        "created": (not existed) and changed,
        "backupPath": str(backup_path) if backup_path else None,
    }


def uninstall_opencode_config_file(
    *,
    config_path: Path,
    gateway_base_url: str,
    force_remove: bool,
) -> Dict[str, Any]:
    if not config_path.exists():
        return {
            "path": str(config_path),
            "changed": False,
            "backupPath": None,
            "reason": "config_not_found",
            "removedBaseUrl": None,
        }

    config_data = read_json_file(config_path)
    updated, changed, removed_value, reason = remove_opencode_base_url(
        config_data,
        gateway_base_url,
        force_remove=force_remove,
    )

    backup_path = None
    if changed:
        backup_path = config_path.with_name(f"{config_path.name}.bak.{utc_timestamp()}")
        shutil.copy2(config_path, backup_path)
        write_json_file(config_path, updated)

    return {
        "path": str(config_path),
        "changed": changed,
        "backupPath": str(backup_path) if backup_path else None,
        "reason": reason,
        "removedBaseUrl": removed_value,
    }
