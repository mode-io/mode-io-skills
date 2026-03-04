#!/usr/bin/env python3
"""
Cross-platform setup helper for modeio prompt gateway routing.

This script keeps setup optional and low-overhead:
- It never requires editing client config if you do not want that.
- It can apply OpenCode `baseURL` config updates when requested.
- It prints the exact Codex environment command for your shell.
- It supports one-command uninstall guidance and cleanup.
"""

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
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8787/v1"
DEFAULT_UPSTREAM_URL = "https://api.openai.com/v1/chat/completions"


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
    *, os_name: Optional[str] = None, env: Optional[Dict[str, str]] = None, home: Optional[Path] = None
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
    config: Dict[str, Any], gateway_base_url: str, *, force_remove: bool
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
            f"OpenCode config not found: {config_path}. "
            "Use --create-opencode-config to create it."
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
        with urllib.request.urlopen(request, timeout=max(1, timeout_seconds)) as response:
            status_code = int(response.status)
            if 200 <= status_code < 300:
                return HealthCheckResult(
                    checked=True,
                    ok=True,
                    status_code=status_code,
                    message="gateway is reachable",
                )
            return HealthCheckResult(
                checked=True,
                ok=False,
                status_code=status_code,
                message=f"gateway returned unexpected status {status_code}",
            )
    except urllib.error.HTTPError as error:
        try:
            return HealthCheckResult(
                checked=True,
                ok=False,
                status_code=error.code,
                message=f"gateway returned HTTP {error.code}",
            )
        finally:
            error.close()
    except urllib.error.URLError as error:
        return HealthCheckResult(
            checked=True,
            ok=False,
            status_code=None,
            message=f"gateway not reachable: {error.reason}",
        )


def _default_map_dir(env: Optional[Dict[str, str]] = None, home: Optional[Path] = None) -> Path:
    resolved_env = env or os.environ
    custom = resolved_env.get("MODEIO_REDACT_MAP_DIR", "").strip()
    if custom:
        return Path(custom).expanduser()
    base_home = home or Path.home()
    return base_home / ".modeio" / "redact" / "maps"


def _cleanup_gateway_local_maps(map_dir: Path) -> Dict[str, Any]:
    target = map_dir.expanduser()
    summary: Dict[str, Any] = {
        "mapDir": str(target),
        "scanned": 0,
        "matched": 0,
        "removed": 0,
        "failed": 0,
        "removedExamples": [],
    }

    if not target.exists():
        return summary

    candidates = sorted(target.glob("*.json"))
    summary["scanned"] = len(candidates)

    removed_examples: List[str] = []
    for path in candidates:
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(parsed, dict):
            continue
        if parsed.get("sourceMode") != "gateway-local":
            continue

        summary["matched"] += 1
        try:
            path.unlink()
            summary["removed"] += 1
            if len(removed_examples) < 5:
                removed_examples.append(str(path))
        except OSError:
            summary["failed"] += 1

    summary["removedExamples"] = removed_examples
    return summary


def _build_start_command(gateway_base_url: str) -> str:
    normalized = _normalize_gateway_base_url(gateway_base_url)
    prefix = normalized
    if prefix.endswith("/v1"):
        prefix = prefix[:-3]

    host_port = prefix.replace("http://", "").replace("https://", "")
    host, port = host_port.split(":", 1) if ":" in host_port else (host_port, "8787")

    return (
        "python modeio-redact/scripts/prompt_gateway.py "
        f"--host {host} --port {port} --upstream-url \"{DEFAULT_UPSTREAM_URL}\""
    )


def _build_report(args: argparse.Namespace) -> Dict[str, Any]:
    gateway_base_url = _normalize_gateway_base_url(args.gateway_base_url)
    health_url = args.health_url.strip() if args.health_url else _derive_health_url(gateway_base_url)
    os_name = _detect_os_name(args.os_name)
    shell = args.shell if args.shell != "auto" else _detect_shell(os_name)
    uninstall_mode = bool(args.uninstall)
    mode = "uninstall" if uninstall_mode else "setup"

    report: Dict[str, Any] = {
        "success": True,
        "tool": "modeio-redact-setup",
        "mode": mode,
        "os": os_name,
        "gatewayBaseUrl": gateway_base_url,
        "gatewayHealthUrl": health_url,
        "codex": {
            "selected": args.client in {"codex", "both"},
            "detected": bool(shutil.which("codex")),
            "shell": shell,
            "setEnvCommand": _codex_env_command(shell, gateway_base_url),
            "unsetEnvCommand": _codex_unset_env_command(shell),
        },
        "opencode": {
            "selected": args.client in {"opencode", "both"},
            "detected": bool(shutil.which("opencode")),
            "applyRequested": bool(args.apply_opencode),
        },
        "health": {
            "checked": False,
            "ok": False,
            "statusCode": None,
            "message": "skipped",
        },
        "commands": {
            "startGateway": _build_start_command(gateway_base_url),
        },
    }

    if uninstall_mode:
        report["cleanup"] = {
            "requested": bool(args.cleanup_maps),
            "mapDir": str(Path(args.map_dir).expanduser()) if args.map_dir else str(_default_map_dir()),
            "scanned": 0,
            "matched": 0,
            "removed": 0,
            "failed": 0,
            "removedExamples": [],
        }

    if not args.skip_health_check:
        health = _check_gateway_health(health_url, args.timeout_seconds)
        report["health"] = {
            "checked": health.checked,
            "ok": health.ok,
            "statusCode": health.status_code,
            "message": health.message,
        }

    if report["opencode"]["selected"]:
        config_path = Path(args.opencode_config).expanduser() if args.opencode_config else _default_opencode_config_path()
        report["opencode"]["configPath"] = str(config_path)

        if args.apply_opencode:
            if uninstall_mode:
                uninstall_result = _uninstall_opencode_config_file(
                    config_path=config_path,
                    gateway_base_url=gateway_base_url,
                    force_remove=args.force_opencode_remove_base_url,
                )
                report["opencode"].update(uninstall_result)
            else:
                apply_result = _apply_opencode_config_file(
                    config_path=config_path,
                    gateway_base_url=gateway_base_url,
                    create_if_missing=args.create_opencode_config,
                )
                report["opencode"].update(apply_result)

    if uninstall_mode and args.cleanup_maps:
        map_dir = Path(args.map_dir).expanduser() if args.map_dir else _default_map_dir()
        cleanup_result = _cleanup_gateway_local_maps(map_dir)
        report["cleanup"].update(cleanup_result)

    return report


def _print_human_report(report: Dict[str, Any]) -> None:
    mode = report.get("mode", "setup")
    heading = "Modeio Prompt Gateway Uninstall" if mode == "uninstall" else "Modeio Prompt Gateway Setup"
    print(heading)
    print(f"- OS: {report['os']}")
    print(f"- Gateway base URL: {report['gatewayBaseUrl']}")
    print(f"- Health URL: {report['gatewayHealthUrl']}")

    health = report["health"]
    if health["checked"]:
        status_label = "OK" if health["ok"] else "NOT READY"
        print(f"- Health check: {status_label} ({health['message']})")
    else:
        print("- Health check: skipped")

    codex = report["codex"]
    if codex["selected"]:
        print(f"- Codex detected: {'yes' if codex['detected'] else 'no'}")
        if mode == "uninstall":
            print(f"- Codex unset command ({codex['shell']}): {codex['unsetEnvCommand']}")
        else:
            print(f"- Codex env command ({codex['shell']}): {codex['setEnvCommand']}")

    opencode = report["opencode"]
    if opencode["selected"]:
        print(f"- OpenCode detected: {'yes' if opencode['detected'] else 'no'}")
        print(f"- OpenCode config: {opencode.get('configPath', 'n/a')}")
        if opencode.get("applyRequested"):
            changed = opencode.get("changed", False)
            if mode == "uninstall":
                if changed:
                    print("- OpenCode uninstall update: applied")
                    if opencode.get("removedBaseUrl"):
                        print(f"- Removed OpenCode baseURL: {opencode['removedBaseUrl']}")
                    if opencode.get("backupPath"):
                        print(f"- OpenCode backup: {opencode['backupPath']}")
                else:
                    print(f"- OpenCode uninstall update: no change ({opencode.get('reason', 'no_change')})")
            else:
                if changed:
                    print("- OpenCode config update: applied")
                    if opencode.get("backupPath"):
                        print(f"- OpenCode backup: {opencode['backupPath']}")
                else:
                    print("- OpenCode config update: no change needed")

    if mode == "uninstall":
        cleanup = report.get("cleanup", {})
        if cleanup.get("requested"):
            print(
                "- Map cleanup: "
                f"removed {cleanup.get('removed', 0)}/{cleanup.get('matched', 0)} "
                f"gateway-local maps (scanned {cleanup.get('scanned', 0)})"
            )
            examples = cleanup.get("removedExamples") or []
            for path in examples:
                print(f"  removed: {path}")
        return

    print("- Start gateway command:")
    print(f"  {report['commands']['startGateway']}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Set up local prompt gateway routing for Codex/OpenCode. "
            "Optional but recommended for automatic shield/unshield."
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
        "--skip-health-check",
        action="store_true",
        help="Skip gateway /healthz connectivity check",
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
        "--uninstall",
        action="store_true",
        help="Run uninstall mode (print unset guidance, optional OpenCode rollback, optional map cleanup)",
    )
    parser.add_argument(
        "--create-opencode-config",
        action="store_true",
        help="Create OpenCode config if missing (requires --apply-opencode)",
    )
    parser.add_argument(
        "--force-opencode-remove-base-url",
        action="store_true",
        help="In uninstall mode, remove OpenCode baseURL even if it differs from --gateway-base-url",
    )
    parser.add_argument(
        "--cleanup-maps",
        action="store_true",
        help="In uninstall mode, remove local gateway-local map files",
    )
    parser.add_argument(
        "--map-dir",
        default="",
        help="Map directory override for --cleanup-maps",
    )
    parser.add_argument(
        "--opencode-config",
        default="",
        help="OpenCode config path override",
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
    elif args.cleanup_maps and not args.uninstall:
        validation_message = "--cleanup-maps requires --uninstall"
    elif args.force_opencode_remove_base_url and not args.uninstall:
        validation_message = "--force-opencode-remove-base-url requires --uninstall"

    if validation_message:
        if args.json:
            payload = {
                "success": False,
                "tool": "modeio-redact-setup",
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
                "tool": "modeio-redact-setup",
                "error": {"type": "setup_error", "message": str(error)},
            }
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"Setup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
