#!/usr/bin/env python3
"""Setup/unsetup helper for modeio-middleware gateway routing."""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from modeio_middleware.connectors.claude_hooks import CLAUDE_HOOK_CONNECTOR_PATH

DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8787/v1"
DEFAULT_UPSTREAM_CHAT_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_UPSTREAM_RESPONSES_URL = "https://api.openai.com/v1/responses"
CLAUDE_HOOK_EVENTS = ("UserPromptSubmit", "Stop")


class SetupError(RuntimeError):
    pass


@dataclass(frozen=True)
class HealthCheckResult:
    checked: bool
    ok: bool
    status_code: Optional[int]
    message: str


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_gateway_base_url(raw: str) -> str:
    if not isinstance(raw, str):
        raise SetupError("gateway base URL must be a string")
    value = raw.strip()
    if not value:
        raise SetupError("gateway base URL cannot be empty")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise SetupError("gateway base URL must start with http:// or https://")
    return value.rstrip("/")


def _derive_health_url(gateway_base_url: str) -> str:
    normalized = _normalize_gateway_base_url(gateway_base_url)
    if normalized.endswith("/v1"):
        return normalized[:-3] + "/healthz"
    return normalized + "/healthz"


def _detect_os_name(os_name: Optional[str] = None) -> str:
    if os_name:
        return os_name.strip().lower()
    return platform.system().strip().lower()


def _default_opencode_config_path(
    *,
    os_name: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    home: Optional[Path] = None,
) -> Path:
    resolved_env = env or os.environ
    resolved_home = home or Path.home()
    system_name = _detect_os_name(os_name)

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


def _default_claude_settings_path(
    *,
    home: Optional[Path] = None,
) -> Path:
    resolved_home = home or Path.home()
    return resolved_home / ".claude" / "settings.json"


def _derive_claude_hook_url(gateway_base_url: str) -> str:
    normalized = _normalize_gateway_base_url(gateway_base_url)
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized + CLAUDE_HOOK_CONNECTOR_PATH


def _detect_shell(os_name: str, env: Optional[Dict[str, str]] = None) -> str:
    resolved_env = env or os.environ
    if os_name == "windows":
        return "powershell"

    shell_path = resolved_env.get("SHELL", "").lower()
    if shell_path.endswith("zsh"):
        return "zsh"
    if shell_path.endswith("fish"):
        return "fish"
    return "bash"


def _codex_env_command(shell: str, gateway_base_url: str) -> str:
    normalized = _normalize_gateway_base_url(gateway_base_url)
    if shell == "powershell":
        return f'$env:OPENAI_BASE_URL = "{normalized}"'
    if shell == "cmd":
        return f"set OPENAI_BASE_URL={normalized}"
    if shell == "fish":
        return f'set -x OPENAI_BASE_URL "{normalized}"'
    return f'export OPENAI_BASE_URL="{normalized}"'


def _codex_unset_env_command(shell: str) -> str:
    if shell == "powershell":
        return "Remove-Item Env:OPENAI_BASE_URL"
    if shell == "cmd":
        return "set OPENAI_BASE_URL="
    if shell == "fish":
        return "set -e OPENAI_BASE_URL"
    return "unset OPENAI_BASE_URL"


def _ensure_object(value: Any, label: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise SetupError(f"{label} must be an object in OpenCode config")


def _apply_opencode_base_url(config: Dict[str, Any], gateway_base_url: str) -> Tuple[Dict[str, Any], bool]:
    updated = copy.deepcopy(config)
    provider_obj = _ensure_object(updated.get("provider"), "provider")
    openai_obj = _ensure_object(provider_obj.get("openai"), "provider.openai")
    options_obj = _ensure_object(openai_obj.get("options"), "provider.openai.options")

    normalized = _normalize_gateway_base_url(gateway_base_url)
    current_base_url = options_obj.get("baseURL")
    changed = current_base_url != normalized

    options_obj["baseURL"] = normalized
    openai_obj["options"] = options_obj
    provider_obj["openai"] = openai_obj
    updated["provider"] = provider_obj
    return updated, changed


def _remove_opencode_base_url(
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

    normalized_target = _normalize_gateway_base_url(gateway_base_url)
    normalized_current = raw_base_url.rstrip("/")

    if not force_remove and normalized_current != normalized_target:
        return updated, False, raw_base_url, "base_url_mismatch"

    del options_obj["baseURL"]
    openai_obj["options"] = options_obj
    provider_obj["openai"] = openai_obj
    updated["provider"] = provider_obj
    return updated, True, raw_base_url, "removed"


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


def _apply_claude_hook_config(config: Dict[str, Any], *, hook_url: str) -> Tuple[Dict[str, Any], bool]:
    updated = copy.deepcopy(config)
    hooks_obj = _ensure_object(updated.get("hooks"), "hooks")
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


def _remove_claude_hook_config(
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


def _apply_claude_settings_file(
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
        config_data = _read_json_file(config_path)

    hook_url = _derive_claude_hook_url(gateway_base_url)
    updated, changed = _apply_claude_hook_config(config_data, hook_url=hook_url)

    backup_path = None
    if changed:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if existed:
            backup_path = config_path.with_name(f"{config_path.name}.bak.{_utc_timestamp()}")
            shutil.copy2(config_path, backup_path)
        _write_json_file(config_path, updated)

    return {
        "path": str(config_path),
        "changed": changed,
        "created": (not existed) and changed,
        "backupPath": str(backup_path) if backup_path else None,
        "hookUrl": hook_url,
    }


def _uninstall_claude_settings_file(
    *,
    config_path: Path,
    gateway_base_url: str,
    force_remove: bool,
) -> Dict[str, Any]:
    hook_url = _derive_claude_hook_url(gateway_base_url)
    if not config_path.exists():
        return {
            "path": str(config_path),
            "changed": False,
            "backupPath": None,
            "reason": "config_not_found",
            "hookUrl": hook_url,
            "removedHooks": 0,
        }

    config_data = _read_json_file(config_path)
    updated, changed, removed_count, reason = _remove_claude_hook_config(
        config_data,
        hook_url=hook_url,
        force_remove=force_remove,
    )

    backup_path = None
    if changed:
        backup_path = config_path.with_name(f"{config_path.name}.bak.{_utc_timestamp()}")
        shutil.copy2(config_path, backup_path)
        _write_json_file(config_path, updated)

    return {
        "path": str(config_path),
        "changed": changed,
        "backupPath": str(backup_path) if backup_path else None,
        "reason": reason,
        "hookUrl": hook_url,
        "removedHooks": removed_count,
    }


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SetupError(f"failed to read config file: {path}") from error

    try:
        parsed = json.loads(content)
    except ValueError as error:
        raise SetupError(f"invalid JSON in config file: {path}") from error

    if not isinstance(parsed, dict):
        raise SetupError(f"config root must be an object: {path}")
    return parsed


def _write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(body + "\n", encoding="utf-8")


def _apply_opencode_config_file(
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
        config_data = _read_json_file(config_path)

    updated, changed = _apply_opencode_base_url(config_data, gateway_base_url)
    backup_path = None
    if changed:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if existed:
            backup_path = config_path.with_name(f"{config_path.name}.bak.{_utc_timestamp()}")
            shutil.copy2(config_path, backup_path)
        _write_json_file(config_path, updated)

    return {
        "path": str(config_path),
        "changed": changed,
        "created": (not existed) and changed,
        "backupPath": str(backup_path) if backup_path else None,
    }


def _uninstall_opencode_config_file(
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

    config_data = _read_json_file(config_path)
    updated, changed, removed_value, reason = _remove_opencode_base_url(
        config_data,
        gateway_base_url,
        force_remove=force_remove,
    )

    backup_path = None
    if changed:
        backup_path = config_path.with_name(f"{config_path.name}.bak.{_utc_timestamp()}")
        shutil.copy2(config_path, backup_path)
        _write_json_file(config_path, updated)

    return {
        "path": str(config_path),
        "changed": changed,
        "backupPath": str(backup_path) if backup_path else None,
        "reason": reason,
        "removedBaseUrl": removed_value,
    }


def _check_gateway_health(health_url: str, timeout_seconds: int) -> HealthCheckResult:
    request = urllib.request.Request(health_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        try:
            message = f"http_error_{error.code}"
        finally:
            error.close()
        return HealthCheckResult(
            checked=True,
            ok=False,
            status_code=error.code,
            message=message,
        )
    except Exception as error:  # pragma: no cover - best effort path
        return HealthCheckResult(
            checked=True,
            ok=False,
            status_code=None,
            message=f"connection_failed:{type(error).__name__}",
        )

    if status_code != 200:
        return HealthCheckResult(
            checked=True,
            ok=False,
            status_code=status_code,
            message=f"unexpected_status:{status_code}",
        )

    try:
        payload = json.loads(body)
    except ValueError:
        return HealthCheckResult(
            checked=True,
            ok=False,
            status_code=status_code,
            message="invalid_json",
        )

    if isinstance(payload, dict) and payload.get("ok") is True:
        return HealthCheckResult(
            checked=True,
            ok=True,
            status_code=status_code,
            message="healthy",
        )

    return HealthCheckResult(
        checked=True,
        ok=False,
        status_code=status_code,
        message="unhealthy_payload",
    )


def _build_start_command(gateway_base_url: str) -> str:
    normalized = _normalize_gateway_base_url(gateway_base_url)
    host = "127.0.0.1"
    port = 8787
    if normalized.startswith("http://"):
        host_port = normalized[len("http://") :]
        if "/" in host_port:
            host_port = host_port.split("/", 1)[0]
        if ":" in host_port:
            host, raw_port = host_port.rsplit(":", 1)
            if raw_port.isdigit():
                port = int(raw_port)

    return (
        "python modeio-middleware/scripts/middleware_gateway.py "
        f"--host {host} --port {port} "
        f"--upstream-chat-url \"{DEFAULT_UPSTREAM_CHAT_URL}\" "
        f"--upstream-responses-url \"{DEFAULT_UPSTREAM_RESPONSES_URL}\""
    )


def _build_report(args: argparse.Namespace) -> Dict[str, Any]:
    gateway_base_url = _normalize_gateway_base_url(args.gateway_base_url)
    os_name = _detect_os_name(args.os_name)
    shell = args.shell if args.shell != "auto" else _detect_shell(os_name)
    health_url = args.health_url.strip() or _derive_health_url(gateway_base_url)

    report: Dict[str, Any] = {
        "success": True,
        "tool": "modeio-middleware-setup",
        "mode": "setup" if not args.uninstall else "uninstall",
        "gateway": {
            "baseUrl": gateway_base_url,
            "health": {
                "checked": False,
                "ok": False,
                "statusCode": None,
                "message": "skipped",
            },
        },
        "codex": {
            "shell": shell,
            "setCommand": _codex_env_command(shell, gateway_base_url),
            "unsetCommand": _codex_unset_env_command(shell),
        },
        "opencode": None,
        "claude": None,
        "commands": {
            "startGateway": _build_start_command(gateway_base_url),
            "claudeHookUrl": _derive_claude_hook_url(gateway_base_url),
        },
    }

    if args.health_check:
        health = _check_gateway_health(health_url, args.timeout_seconds)
        report["gateway"]["health"] = {
            "checked": health.checked,
            "ok": health.ok,
            "statusCode": health.status_code,
            "message": health.message,
        }

    if args.apply_opencode:
        config_path = (
            Path(args.opencode_config_path).expanduser()
            if args.opencode_config_path
            else _default_opencode_config_path(os_name=os_name)
        )
        if args.uninstall:
            report["opencode"] = _uninstall_opencode_config_file(
                config_path=config_path,
                gateway_base_url=gateway_base_url,
                force_remove=args.force_remove_opencode_base_url,
            )
        else:
            report["opencode"] = _apply_opencode_config_file(
                config_path=config_path,
                gateway_base_url=gateway_base_url,
                create_if_missing=args.create_opencode_config,
            )

    if args.apply_claude:
        claude_path = (
            Path(args.claude_settings_path).expanduser()
            if args.claude_settings_path
            else _default_claude_settings_path()
        )
        if args.uninstall:
            report["claude"] = _uninstall_claude_settings_file(
                config_path=claude_path,
                gateway_base_url=gateway_base_url,
                force_remove=args.force_remove_claude_hook_url,
            )
        else:
            report["claude"] = _apply_claude_settings_file(
                config_path=claude_path,
                gateway_base_url=gateway_base_url,
                create_if_missing=args.create_claude_settings,
            )

    return report


def _print_human_report(report: Dict[str, Any]) -> None:
    mode = report.get("mode")
    print("modeio-middleware setup report")
    print(f"- Mode: {mode}")
    print(f"- Gateway base URL: {report['gateway']['baseUrl']}")

    health = report["gateway"]["health"]
    if health.get("checked"):
        print(
            "- Health check: "
            f"ok={health.get('ok')} status={health.get('statusCode')} message={health.get('message')}"
        )
    else:
        print("- Health check: skipped")

    print("- Codex commands:")
    print(f"  set:   {report['codex']['setCommand']}")
    print(f"  unset: {report['codex']['unsetCommand']}")

    opencode = report.get("opencode")
    if opencode is not None:
        print("- OpenCode config:")
        print(f"  path: {opencode.get('path')}")
        print(f"  changed: {opencode.get('changed')}")
        if opencode.get("backupPath"):
            print(f"  backup: {opencode.get('backupPath')}")
        if opencode.get("reason"):
            print(f"  reason: {opencode.get('reason')}")

    claude = report.get("claude")
    if claude is not None:
        print("- Claude hooks config:")
        print(f"  path: {claude.get('path')}")
        print(f"  changed: {claude.get('changed')}")
        if claude.get("hookUrl"):
            print(f"  hookUrl: {claude.get('hookUrl')}")
        if claude.get("backupPath"):
            print(f"  backup: {claude.get('backupPath')}")
        if claude.get("reason"):
            print(f"  reason: {claude.get('reason')}")

    print("- Start gateway command:")
    print(f"  {report['commands']['startGateway']}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Set up local middleware routing for Codex/OpenCode/Claude hooks. "
            "Optional but recommended for request/response middleware control."
        )
    )
    parser.add_argument(
        "--client",
        choices=("codex", "opencode", "both"),
        default="both",
        help="Target client configuration scope (default: both)",
    )
    parser.add_argument(
        "--gateway-base-url",
        default=DEFAULT_GATEWAY_BASE_URL,
        help=f"Gateway base URL (default: {DEFAULT_GATEWAY_BASE_URL})",
    )
    parser.add_argument(
        "--health-url",
        default="",
        help="Gateway health URL override (default derived from --gateway-base-url)",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Run gateway /healthz connectivity check",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=3,
        help="Health check timeout seconds (default: 3)",
    )
    parser.add_argument(
        "--apply-opencode",
        action="store_true",
        help="Apply OpenCode config update (provider.openai.options.baseURL)",
    )
    parser.add_argument(
        "--apply-claude",
        action="store_true",
        help="Apply Claude hooks config update (~/.claude/settings.json by default)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Run uninstall mode (print unset guidance and optional OpenCode rollback)",
    )
    parser.add_argument(
        "--create-opencode-config",
        action="store_true",
        help="Create OpenCode config if missing (requires --apply-opencode)",
    )
    parser.add_argument(
        "--create-claude-settings",
        action="store_true",
        help="Create Claude settings file if missing (requires --apply-claude)",
    )
    parser.add_argument(
        "--force-remove-opencode-base-url",
        action="store_true",
        help="In uninstall mode, remove OpenCode baseURL even when it differs from --gateway-base-url",
    )
    parser.add_argument(
        "--force-remove-claude-hook-url",
        action="store_true",
        help=(
            "In uninstall mode, remove Claude ModeIO hook endpoints even when URL host/port differs "
            "from --gateway-base-url"
        ),
    )
    parser.add_argument(
        "--opencode-config-path",
        default="",
        help="OpenCode config path override",
    )
    parser.add_argument(
        "--claude-settings-path",
        default="",
        help="Claude settings path override",
    )
    parser.add_argument(
        "--shell",
        choices=("auto", "bash", "zsh", "fish", "powershell", "cmd"),
        default="auto",
        help="Shell used to print Codex OPENAI_BASE_URL command",
    )
    parser.add_argument(
        "--os-name",
        default="",
        help="Override OS detection for testing/debugging",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON report",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    validation_message = ""
    if args.create_opencode_config and not args.apply_opencode:
        validation_message = "--create-opencode-config requires --apply-opencode"
    elif args.create_opencode_config and args.uninstall:
        validation_message = "--create-opencode-config cannot be used with --uninstall"
    elif args.create_claude_settings and not args.apply_claude:
        validation_message = "--create-claude-settings requires --apply-claude"
    elif args.create_claude_settings and args.uninstall:
        validation_message = "--create-claude-settings cannot be used with --uninstall"
    elif args.force_remove_opencode_base_url and not args.uninstall:
        validation_message = "--force-remove-opencode-base-url requires --uninstall"
    elif args.force_remove_claude_hook_url and not args.uninstall:
        validation_message = "--force-remove-claude-hook-url requires --uninstall"

    if validation_message:
        if args.json:
            payload = {
                "success": False,
                "tool": "modeio-middleware-setup",
                "error": {"type": "validation_error", "message": validation_message},
            }
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"Error: {validation_message}", file=sys.stderr)
        return 2

    try:
        report = _build_report(args)
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            _print_human_report(report)
        return 0
    except SetupError as error:
        if args.json:
            payload = {
                "success": False,
                "tool": "modeio-middleware-setup",
                "error": {"type": "setup_error", "message": str(error)},
            }
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"Setup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
