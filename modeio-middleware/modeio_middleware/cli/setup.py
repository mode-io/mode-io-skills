#!/usr/bin/env python3
"""Setup/unsetup helper for modeio-middleware gateway routing."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from modeio_middleware.cli.setup_lib.claude import (
    apply_claude_settings_file,
    default_claude_settings_path,
    derive_claude_hook_url,
    uninstall_claude_settings_file,
)
from modeio_middleware.cli.setup_lib.common import (
    HealthCheckResult,
    SetupError,
    derive_health_url,
    normalize_gateway_base_url,
)
from modeio_middleware.cli.setup_lib.opencode import (
    apply_opencode_base_url,
    apply_opencode_config_file,
    uninstall_opencode_config_file,
)
from modeio_middleware.cli.setup_lib.openclaw import (
    OPENCLAW_MODEL_ID,
    OPENCLAW_MODEL_REF,
    OPENCLAW_PROVIDER_ID,
    apply_openclaw_config_file,
    apply_openclaw_models_cache_file,
    apply_openclaw_provider_route,
    default_openclaw_config_path,
    default_openclaw_models_cache_path,
    uninstall_openclaw_config_file,
    uninstall_openclaw_models_cache_file,
)

DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8787/v1"
DEFAULT_UPSTREAM_CHAT_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_UPSTREAM_RESPONSES_URL = "https://api.openai.com/v1/responses"

# Backward-compatible module-level aliases for tests and script wrappers.
_normalize_gateway_base_url = normalize_gateway_base_url
_derive_health_url = derive_health_url

_default_claude_settings_path = default_claude_settings_path
_derive_claude_hook_url = derive_claude_hook_url
_apply_claude_settings_file = apply_claude_settings_file
_uninstall_claude_settings_file = uninstall_claude_settings_file

_apply_opencode_base_url = apply_opencode_base_url
_apply_opencode_config_file = apply_opencode_config_file
_uninstall_opencode_config_file = uninstall_opencode_config_file

_default_openclaw_config_path = default_openclaw_config_path
_default_openclaw_models_cache_path = default_openclaw_models_cache_path
_apply_openclaw_provider_route = apply_openclaw_provider_route
_apply_openclaw_config_file = apply_openclaw_config_file
_uninstall_openclaw_config_file = uninstall_openclaw_config_file
_apply_openclaw_models_cache_file = apply_openclaw_models_cache_file
_uninstall_openclaw_models_cache_file = uninstall_openclaw_models_cache_file


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
        "openclaw": None,
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

    if args.apply_openclaw:
        config_path = (
            Path(args.openclaw_config_path).expanduser()
            if args.openclaw_config_path
            else _default_openclaw_config_path(os_name=os_name)
        )
        models_cache_path = (
            Path(args.openclaw_models_cache_path).expanduser()
            if args.openclaw_models_cache_path
            else _default_openclaw_models_cache_path(config_path=config_path)
        )
        if args.uninstall:
            openclaw_report = _uninstall_openclaw_config_file(
                config_path=config_path,
                gateway_base_url=gateway_base_url,
                force_remove=args.force_remove_openclaw_provider,
            )
            openclaw_report["modelsCache"] = _uninstall_openclaw_models_cache_file(
                models_cache_path=models_cache_path,
                gateway_base_url=gateway_base_url,
                force_remove=args.force_remove_openclaw_provider,
            )
            report["openclaw"] = openclaw_report
        else:
            openclaw_report = _apply_openclaw_config_file(
                config_path=config_path,
                gateway_base_url=gateway_base_url,
                create_if_missing=args.create_openclaw_config,
            )
            openclaw_report["modelsCache"] = _apply_openclaw_models_cache_file(
                models_cache_path=models_cache_path,
                gateway_base_url=gateway_base_url,
            )
            report["openclaw"] = openclaw_report

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

    openclaw = report.get("openclaw")
    if openclaw is not None:
        print("- OpenClaw config:")
        print(f"  path: {openclaw.get('path')}")
        print(f"  changed: {openclaw.get('changed')}")
        if openclaw.get("backupPath"):
            print(f"  backup: {openclaw.get('backupPath')}")
        if openclaw.get("reason"):
            print(f"  reason: {openclaw.get('reason')}")
        models_cache = openclaw.get("modelsCache")
        if isinstance(models_cache, dict):
            print("  models cache:")
            print(f"    path: {models_cache.get('path')}")
            print(f"    changed: {models_cache.get('changed')}")
            if models_cache.get("backupPath"):
                print(f"    backup: {models_cache.get('backupPath')}")
            if models_cache.get("reason"):
                print(f"    reason: {models_cache.get('reason')}")

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
            "Set up local middleware routing for Codex/OpenCode/OpenClaw/Claude hooks. "
            "Optional but recommended for request/response middleware control."
        )
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
    parser.add_argument("--health-check", action="store_true", help="Run gateway /healthz connectivity check")
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
        "--apply-openclaw",
        action="store_true",
        help="Apply OpenClaw config update (models.providers + default model routing)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Run uninstall mode (print unset guidance and optional client rollback)",
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
        "--create-openclaw-config",
        action="store_true",
        help="Create OpenClaw config if missing (requires --apply-openclaw)",
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
        "--force-remove-openclaw-provider",
        action="store_true",
        help=(
            "In uninstall mode, remove OpenClaw modeio-middleware provider even when baseUrl "
            "differs from --gateway-base-url"
        ),
    )
    parser.add_argument("--opencode-config-path", default="", help="OpenCode config path override")
    parser.add_argument("--openclaw-config-path", default="", help="OpenClaw config path override")
    parser.add_argument(
        "--openclaw-models-cache-path",
        default="",
        help="OpenClaw generated models cache path override (default: infer from OpenClaw state/config)",
    )
    parser.add_argument("--claude-settings-path", default="", help="Claude settings path override")
    parser.add_argument(
        "--shell",
        choices=("auto", "bash", "zsh", "fish", "powershell", "cmd"),
        default="auto",
        help="Shell used to print Codex OPENAI_BASE_URL command",
    )
    parser.add_argument("--os-name", default="", help="Override OS detection for testing/debugging")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON report")
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
    elif args.create_openclaw_config and not args.apply_openclaw:
        validation_message = "--create-openclaw-config requires --apply-openclaw"
    elif args.create_openclaw_config and args.uninstall:
        validation_message = "--create-openclaw-config cannot be used with --uninstall"
    elif args.force_remove_opencode_base_url and not args.uninstall:
        validation_message = "--force-remove-opencode-base-url requires --uninstall"
    elif args.force_remove_claude_hook_url and not args.uninstall:
        validation_message = "--force-remove-claude-hook-url requires --uninstall"
    elif args.force_remove_openclaw_provider and not args.uninstall:
        validation_message = "--force-remove-openclaw-provider requires --uninstall"

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
