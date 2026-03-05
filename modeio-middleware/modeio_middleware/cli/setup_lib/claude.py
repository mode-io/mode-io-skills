#!/usr/bin/env python3

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from modeio_middleware.cli.setup_lib.common import (
    SetupError,
    ensure_object,
    normalize_gateway_base_url,
    read_json_file,
    utc_timestamp,
    write_json_file,
)
from modeio_middleware.connectors.claude_hooks import CLAUDE_HOOK_CONNECTOR_PATH

CLAUDE_HOOK_EVENTS = ("UserPromptSubmit", "Stop")


def default_claude_settings_path(
    *,
    home: Optional[Path] = None,
) -> Path:
    resolved_home = home or Path.home()
    return resolved_home / ".claude" / "settings.json"


def derive_claude_hook_url(gateway_base_url: str) -> str:
    normalized = normalize_gateway_base_url(gateway_base_url)
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized + CLAUDE_HOOK_CONNECTOR_PATH


def _is_claude_http_hook_entry(entry: Any, *, hook_url: str, force_remove: bool) -> bool:
    if not isinstance(entry, dict):
        return False
    hook_type = str(entry.get("type", "")).strip().lower()
    if hook_type != "http":
        return False

    raw_url = entry.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        return False
    normalized_url = raw_url.strip().rstrip("/")

    if force_remove:
        return normalized_url.endswith(CLAUDE_HOOK_CONNECTOR_PATH)
    return normalized_url == hook_url.rstrip("/")


def apply_claude_hook_config(config: Dict[str, Any], *, hook_url: str) -> Tuple[Dict[str, Any], bool]:
    updated = copy.deepcopy(config)
    hooks_obj = ensure_object(updated.get("hooks"), "hooks")
    changed = False

    for event_name in CLAUDE_HOOK_EVENTS:
        event_groups = hooks_obj.get(event_name)
        if event_groups is None:
            event_groups = []
        if not isinstance(event_groups, list):
            raise SetupError(f"hooks.{event_name} must be an array in Claude settings")

        has_modeio_hook = False
        normalized_groups = []
        for index, group in enumerate(event_groups):
            if not isinstance(group, dict):
                raise SetupError(f"hooks.{event_name}[{index}] must be an object in Claude settings")
            group_hooks = group.get("hooks")
            if not isinstance(group_hooks, list):
                raise SetupError(f"hooks.{event_name}[{index}].hooks must be an array in Claude settings")
            for hook in group_hooks:
                if _is_claude_http_hook_entry(hook, hook_url=hook_url, force_remove=False):
                    has_modeio_hook = True
            normalized_groups.append(group)

        if not has_modeio_hook:
            normalized_groups.append(
                {
                    "hooks": [
                        {
                            "type": "http",
                            "url": hook_url,
                            "timeout": 30,
                        }
                    ]
                }
            )
            changed = True

        hooks_obj[event_name] = normalized_groups

    updated["hooks"] = hooks_obj
    return updated, changed


def remove_claude_hook_config(
    config: Dict[str, Any],
    *,
    hook_url: str,
    force_remove: bool,
) -> Tuple[Dict[str, Any], bool, int, str]:
    updated = copy.deepcopy(config)
    hooks_obj = updated.get("hooks")
    if not isinstance(hooks_obj, dict):
        return updated, False, 0, "hooks_missing"

    removed_count = 0
    changed = False
    for event_name in CLAUDE_HOOK_EVENTS:
        event_groups = hooks_obj.get(event_name)
        if event_groups is None:
            continue
        if not isinstance(event_groups, list):
            raise SetupError(f"hooks.{event_name} must be an array in Claude settings")

        kept_groups = []
        for index, group in enumerate(event_groups):
            if not isinstance(group, dict):
                raise SetupError(f"hooks.{event_name}[{index}] must be an object in Claude settings")

            group_hooks = group.get("hooks")
            if not isinstance(group_hooks, list):
                raise SetupError(f"hooks.{event_name}[{index}].hooks must be an array in Claude settings")

            kept_hooks = []
            for hook in group_hooks:
                if _is_claude_http_hook_entry(hook, hook_url=hook_url, force_remove=force_remove):
                    removed_count += 1
                    changed = True
                    continue
                kept_hooks.append(hook)

            if kept_hooks:
                group_copy = dict(group)
                group_copy["hooks"] = kept_hooks
                kept_groups.append(group_copy)

        if kept_groups:
            hooks_obj[event_name] = kept_groups
        elif event_name in hooks_obj:
            del hooks_obj[event_name]
            changed = True

    if not hooks_obj:
        updated.pop("hooks", None)

    if removed_count > 0:
        return updated, changed, removed_count, "removed"
    if force_remove:
        return updated, changed, removed_count, "modeio_hook_not_found"
    return updated, changed, removed_count, "hook_url_not_found"


def apply_claude_settings_file(
    *,
    config_path: Path,
    gateway_base_url: str,
    create_if_missing: bool,
) -> Dict[str, Any]:
    existed = config_path.exists()
    if not existed and not create_if_missing:
        raise SetupError(
            f"Claude settings not found: {config_path}. Use --create-claude-settings to create it."
        )

    config_data: Dict[str, Any] = {}
    if existed:
        config_data = read_json_file(config_path)

    hook_url = derive_claude_hook_url(gateway_base_url)
    updated, changed = apply_claude_hook_config(config_data, hook_url=hook_url)

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
        "hookUrl": hook_url,
    }


def uninstall_claude_settings_file(
    *,
    config_path: Path,
    gateway_base_url: str,
    force_remove: bool,
) -> Dict[str, Any]:
    hook_url = derive_claude_hook_url(gateway_base_url)
    if not config_path.exists():
        return {
            "path": str(config_path),
            "changed": False,
            "backupPath": None,
            "reason": "config_not_found",
            "hookUrl": hook_url,
            "removedHooks": 0,
        }

    config_data = read_json_file(config_path)
    updated, changed, removed_count, reason = remove_claude_hook_config(
        config_data,
        hook_url=hook_url,
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
        "hookUrl": hook_url,
        "removedHooks": removed_count,
    }
