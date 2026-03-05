#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

try:  # Python 3.14+
    from compression import zstd as _zstd_codec
except Exception:  # pragma: no cover
    _zstd_codec = None

from smoke_matrix.agents import build_agent_command as _build_agent_command
from smoke_matrix.common import (
    check_required_commands as _check_required_commands,
    default_artifacts_root,
    default_repo_root,
    free_port as _free_port,
    load_tap_events as _load_tap_events,
    parse_agents as _parse_agents,
    resolve_upstream_api_key as _resolve_upstream_api_key,
    run_command_capture as _run_command_capture,
    tap_token_metrics as _tap_token_metrics,
    tap_window_metrics as _tap_window_metrics,
    utc_stamp as _utc_stamp,
    wait_for_url as _wait_for_url,
    write_json as _write_json,
    write_text as _write_text,
)
from smoke_matrix.sandbox import (
    apply_openclaw_live_model_to_cache as _apply_openclaw_live_model_to_cache,
    apply_openclaw_live_model_to_config as _apply_openclaw_live_model_to_config,
    build_sandbox_env as _build_sandbox_env,
    build_sandbox_paths as _build_sandbox_paths,
    rewrite_openclaw_model_for_live as _rewrite_openclaw_model_for_live,
    seed_codex_credentials as _seed_codex_credentials,
    upsert_openclaw_provider_model as _upsert_openclaw_provider_model,
)


def _default_repo_root() -> Path:
    return default_repo_root(Path(__file__))


def _default_artifacts_root() -> Path:
    return default_artifacts_root(Path(__file__))


def _run_setup(
    *,
    repo_root: Path,
    env: Dict[str, str],
    gateway_base_url: str,
    opencode_config_path: Path,
    openclaw_config_path: Path,
    openclaw_models_cache_path: Path,
    timeout_seconds: int,
) -> Dict[str, object]:
    setup_script = repo_root / "modeio-middleware" / "scripts" / "setup_middleware_gateway.py"
    command = [
        sys.executable,
        str(setup_script),
        "--json",
        "--apply-opencode",
        "--create-opencode-config",
        "--opencode-config-path",
        str(opencode_config_path),
        "--apply-openclaw",
        "--create-openclaw-config",
        "--openclaw-config-path",
        str(openclaw_config_path),
        "--openclaw-models-cache-path",
        str(openclaw_models_cache_path),
        "--gateway-base-url",
        gateway_base_url,
    ]

    result = _run_command_capture(
        command=command,
        cwd=repo_root,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    stdout = str(result["stdout"])
    try:
        payload = json.loads(stdout)
    except ValueError as error:
        raise RuntimeError(f"setup script returned non-JSON output: {stdout[:400]}") from error

    if result["exitCode"] != 0 or not payload.get("success"):
        raise RuntimeError(f"setup script failed: exit={result['exitCode']} payload={payload}")
    return payload


def _start_logged_process(
    *,
    command: Sequence[str],
    cwd: Path,
    env: Dict[str, str],
    log_path: Path,
) -> Tuple[subprocess.Popen, object]:
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, handle


def _stop_process(process: Optional[subprocess.Popen]) -> None:
    if process is None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _close_handle(handle: Optional[object]) -> None:
    if handle is not None:
        handle.close()


def _run_agent_check(
    *,
    agent: str,
    index: int,
    run_id: str,
    model: str,
    repo_root: Path,
    run_dir: Path,
    env: Dict[str, str],
    timeout_seconds: int,
    tap_jsonl_path: Path,
) -> Dict[str, object]:
    token = f"SMOKE_{agent.upper()}_{index}_{run_id.upper()}"
    codex_message_path = run_dir / f"{agent}-last-message.txt"
    command = _build_agent_command(
        agent=agent,
        token=token,
        model=model,
        repo_root=repo_root,
        codex_output_path=codex_message_path,
        timeout_seconds=timeout_seconds,
    )

    before_count = len(_load_tap_events(tap_jsonl_path))
    result = _run_command_capture(
        command=command,
        cwd=repo_root,
        env=env,
        timeout_seconds=timeout_seconds,
    )

    stdout_path = run_dir / f"{agent}.stdout.log"
    stderr_path = run_dir / f"{agent}.stderr.log"
    _write_text(stdout_path, str(result["stdout"]))
    _write_text(stderr_path, str(result["stderr"]))

    output_text = str(result["stdout"])
    if agent == "codex" and codex_message_path.exists():
        output_text = codex_message_path.read_text(encoding="utf-8")

    after_events = _load_tap_events(tap_jsonl_path)
    new_events = after_events[before_count:]
    tap_window = _tap_window_metrics(new_events)
    tap_token = _tap_token_metrics(new_events, token)
    ok = (
        int(result["exitCode"]) == 0
        and int(tap_window["eventCount"]) >= 1
        and int(tap_window["successCount"]) >= 1
    )

    return {
        "name": agent,
        "token": token,
        "command": command,
        "exitCode": result["exitCode"],
        "timedOut": result["timedOut"],
        "durationMs": result["durationMs"],
        "stdoutPath": str(stdout_path),
        "stderrPath": str(stderr_path),
        "tokenInOutput": token in output_text,
        "tap": {
            "window": tap_window,
            "token": tap_token,
        },
        "ok": ok,
    }


def _request_with_bytes(
    *,
    method: str,
    url: str,
    body: Optional[bytes],
    headers: Dict[str, str],
    timeout_seconds: int,
) -> Dict[str, object]:
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            status = int(response.status)
            response_headers = dict(response.headers.items())
    except urllib.error.HTTPError as error:
        raw = error.read()
        status = int(error.code)
        response_headers = dict(error.headers.items()) if error.headers else {}

    body_text = raw.decode("utf-8", errors="replace")
    payload = None
    try:
        parsed = json.loads(body_text)
        if isinstance(parsed, dict):
            payload = parsed
    except ValueError:
        payload = None

    return {
        "status": status,
        "headers": response_headers,
        "bodyText": body_text,
        "payload": payload,
    }


def _run_gateway_smoke_checks(
    *,
    gateway_base_url: str,
    model: str,
    run_id: str,
    timeout_seconds: int,
    tap_jsonl_path: Path,
) -> Sequence[Dict[str, object]]:
    checks = []

    def _append(name: str, ok: bool, details: Dict[str, object]) -> None:
        checks.append({"name": name, "ok": ok, **details})

    gateway_root = gateway_base_url.rsplit("/v1", 1)[0]

    health_result = _request_with_bytes(
        method="GET",
        url=f"{gateway_root}/healthz",
        body=None,
        headers={},
        timeout_seconds=timeout_seconds,
    )
    health_payload = health_result.get("payload")
    health_ok = bool(
        health_result.get("status") == 200
        and isinstance(health_payload, dict)
        and health_payload.get("ok") is True
    )
    _append(
        "gateway-healthz",
        health_ok,
        {
            "status": health_result.get("status"),
        },
    )

    before_count = len(_load_tap_events(tap_jsonl_path))
    route_result = _request_with_bytes(
        method="POST",
        url=f"{gateway_base_url}/not-a-real-route",
        body=json.dumps({"probe": run_id}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout_seconds=timeout_seconds,
    )
    after_count = len(_load_tap_events(tap_jsonl_path))
    route_payload = route_result.get("payload")
    route_ok = bool(
        route_result.get("status") == 404
        and isinstance(route_payload, dict)
        and isinstance(route_payload.get("error"), dict)
        and route_payload["error"].get("code") == "MODEIO_ROUTE_NOT_FOUND"
        and after_count == before_count
    )
    _append(
        "route-not-found-no-upstream",
        route_ok,
        {
            "status": route_result.get("status"),
            "tapEventDelta": after_count - before_count,
        },
    )

    unsupported_raw = json.dumps(
        {
            "model": model,
            "input": f"SMOKE_UNSUPPORTED_ENCODING_{run_id}",
            "modeio": {"profile": "dev"},
        }
    ).encode("utf-8")
    before_count = len(_load_tap_events(tap_jsonl_path))
    unsupported_result = _request_with_bytes(
        method="POST",
        url=f"{gateway_base_url}/responses",
        body=unsupported_raw,
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "snappy",
        },
        timeout_seconds=timeout_seconds,
    )
    after_count = len(_load_tap_events(tap_jsonl_path))
    unsupported_payload = unsupported_result.get("payload")
    unsupported_ok = bool(
        unsupported_result.get("status") == 400
        and isinstance(unsupported_payload, dict)
        and isinstance(unsupported_payload.get("error"), dict)
        and unsupported_payload["error"].get("code") == "MODEIO_VALIDATION_ERROR"
        and after_count == before_count
    )
    _append(
        "unsupported-encoding-no-upstream",
        unsupported_ok,
        {
            "status": unsupported_result.get("status"),
            "tapEventDelta": after_count - before_count,
        },
    )

    gzip_raw = json.dumps(
        {
            "model": model,
            "input": f"SMOKE_GZIP_{run_id}",
            "modeio": {"profile": "dev"},
        }
    ).encode("utf-8")
    before_count = len(_load_tap_events(tap_jsonl_path))
    gzip_result = _request_with_bytes(
        method="POST",
        url=f"{gateway_base_url}/responses",
        body=gzip.compress(gzip_raw),
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
        timeout_seconds=timeout_seconds,
    )
    new_events = _load_tap_events(tap_jsonl_path)[before_count:]
    gzip_window = _tap_window_metrics(new_events)
    gzip_headers = {
        str(key).lower(): str(value)
        for key, value in dict(gzip_result.get("headers") or {}).items()
    }
    gzip_ok = bool(
        gzip_result.get("status") == 200
        and gzip_headers.get("x-modeio-contract-version")
        and gzip_headers.get("x-modeio-request-id")
        and gzip_headers.get("x-modeio-upstream-called") == "true"
        and int(gzip_window.get("eventCount", 0)) >= 1
        and int(gzip_window.get("successCount", 0)) >= 1
    )
    _append(
        "gzip-encoded-responses-request",
        gzip_ok,
        {
            "status": gzip_result.get("status"),
            "tapEvents": gzip_window.get("eventCount"),
            "tap2xx": gzip_window.get("successCount"),
            "paths": gzip_window.get("paths"),
        },
    )

    if _zstd_codec is None:
        _append(
            "zstd-encoded-responses-request",
            True,
            {
                "skipped": True,
                "reason": "compression.zstd unavailable",
            },
        )
        return checks

    zstd_raw = json.dumps(
        {
            "model": model,
            "input": f"SMOKE_ZSTD_{run_id}",
            "modeio": {"profile": "dev"},
        }
    ).encode("utf-8")
    before_count = len(_load_tap_events(tap_jsonl_path))
    zstd_result = _request_with_bytes(
        method="POST",
        url=f"{gateway_base_url}/responses",
        body=_zstd_codec.compress(zstd_raw),
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "zstd",
        },
        timeout_seconds=timeout_seconds,
    )
    zstd_events = _load_tap_events(tap_jsonl_path)[before_count:]
    zstd_window = _tap_window_metrics(zstd_events)
    zstd_headers = {
        str(key).lower(): str(value)
        for key, value in dict(zstd_result.get("headers") or {}).items()
    }
    zstd_ok = bool(
        zstd_result.get("status") == 200
        and zstd_headers.get("x-modeio-contract-version")
        and zstd_headers.get("x-modeio-request-id")
        and zstd_headers.get("x-modeio-upstream-called") == "true"
        and int(zstd_window.get("eventCount", 0)) >= 1
        and int(zstd_window.get("successCount", 0)) >= 1
    )
    _append(
        "zstd-encoded-responses-request",
        zstd_ok,
        {
            "status": zstd_result.get("status"),
            "tapEvents": zstd_window.get("eventCount"),
            "tap2xx": zstd_window.get("successCount"),
            "paths": zstd_window.get("paths"),
        },
    )
    return checks


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run isolated live smoke tests via codex/opencode/openclaw through modeio-middleware."
    )
    parser.add_argument(
        "--agents",
        default="codex,opencode,openclaw",
        help="Comma-separated agent list (codex,opencode,openclaw)",
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-5.3-codex",
        help="OpenAI-compatible model name used in all agent prompts",
    )
    parser.add_argument(
        "--upstream-base-url",
        default="https://zenmux.ai/api/v1",
        help="Real upstream OpenAI-compatible base URL",
    )
    parser.add_argument(
        "--upstream-api-key-env",
        default="MODEIO_GATEWAY_UPSTREAM_API_KEY",
        help="Primary env var to read upstream API key from",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=str(_default_artifacts_root()),
        help="Artifact root directory (run-specific child dir is created)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(_default_repo_root()),
        help="Repository root containing modeio-middleware/",
    )
    parser.add_argument("--gateway-host", default="127.0.0.1", help="Gateway listen host")
    parser.add_argument("--gateway-port", type=int, default=0, help="Gateway listen port (0 = auto)")
    parser.add_argument("--tap-port", type=int, default=0, help="Tap proxy listen port (0 = auto)")
    parser.add_argument(
        "--command-timeout-seconds",
        type=int,
        default=300,
        help="Per-command timeout for setup and each agent command",
    )
    parser.add_argument(
        "--startup-timeout-seconds",
        type=int,
        default=40,
        help="Startup timeout for tap proxy and middleware health checks",
    )
    parser.add_argument(
        "--keep-sandbox",
        action="store_true",
        help="Do not delete temporary sandbox directory after run",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    started_at = _utc_stamp()
    run_id = f"{started_at.lower()}-{os.getpid()}"

    repo_root = Path(args.repo_root).expanduser().resolve()
    artifacts_root = Path(args.artifacts_dir).expanduser().resolve()
    run_dir = artifacts_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / "summary.json"
    tap_jsonl_path = run_dir / "tap-exchanges.jsonl"
    tap_stdout_path = run_dir / "tap-proxy.log"
    gateway_log_path = run_dir / "gateway.log"
    setup_payload_path = run_dir / "setup-report.json"

    report: Dict[str, object] = {
        "success": False,
        "mode": "live-agents",
        "runId": run_id,
        "startedAt": started_at,
        "finishedAt": None,
        "upstream": {
            "baseUrl": args.upstream_base_url,
            "apiKeyEnv": None,
            "model": args.model,
        },
        "sandbox": {},
        "gateway": {},
        "tap": {
            "logPath": str(tap_jsonl_path),
            "stdoutPath": str(tap_stdout_path),
        },
        "setup": None,
        "gatewayChecks": [],
        "agents": [],
        "error": None,
    }

    sandbox_root = Path(tempfile.mkdtemp(prefix="modeio-middleware-smoke-"))
    paths = _build_sandbox_paths(sandbox_root)
    report["sandbox"] = {
        "root": str(paths["root"]),
        "home": str(paths["home"]),
        "opencodeConfig": str(paths["opencode_config"]),
        "openclawConfig": str(paths["openclaw_config"]),
        "openclawModelsCache": str(paths["openclaw_models_cache"]),
        "kept": bool(args.keep_sandbox),
    }

    tap_process: Optional[subprocess.Popen] = None
    tap_log_handle = None
    gateway_process: Optional[subprocess.Popen] = None
    gateway_log_handle = None

    try:
        agents = _parse_agents(args.agents)
        missing_commands = _check_required_commands(agents)
        if missing_commands:
            raise RuntimeError("missing required commands: " + ", ".join(missing_commands))

        upstream_api_key, upstream_api_key_env = _resolve_upstream_api_key(
            dict(os.environ),
            args.upstream_api_key_env,
        )
        report["upstream"]["apiKeyEnv"] = upstream_api_key_env

        for key in ("home", "xdg_config", "xdg_state", "xdg_cache", "openclaw_state"):
            paths[key].mkdir(parents=True, exist_ok=True)
        paths["opencode_config"].parent.mkdir(parents=True, exist_ok=True)
        paths["openclaw_models_cache"].parent.mkdir(parents=True, exist_ok=True)

        seeded_codex = _seed_codex_credentials(Path.home(), paths["home"])
        report["sandbox"]["seededCodexFiles"] = seeded_codex

        gateway_port = args.gateway_port if args.gateway_port > 0 else _free_port()
        tap_port = args.tap_port if args.tap_port > 0 else _free_port()
        gateway_base_url = f"http://{args.gateway_host}:{gateway_port}/v1"
        gateway_health_url = f"http://{args.gateway_host}:{gateway_port}/healthz"
        tap_base_url = f"http://{args.gateway_host}:{tap_port}"

        env = _build_sandbox_env(
            dict(os.environ),
            paths,
            gateway_base_url=gateway_base_url,
            upstream_api_key=upstream_api_key,
        )

        tap_command = [
            sys.executable,
            str(repo_root / "modeio-middleware" / "scripts" / "upstream_tap_proxy.py"),
            "--host",
            args.gateway_host,
            "--port",
            str(tap_port),
            "--target-base-url",
            args.upstream_base_url,
            "--log-jsonl",
            str(tap_jsonl_path),
            "--api-key-env",
            "MODEIO_TAP_UPSTREAM_API_KEY",
        ]
        tap_process, tap_log_handle = _start_logged_process(
            command=tap_command,
            cwd=repo_root,
            env=env,
            log_path=tap_stdout_path,
        )
        if not _wait_for_url(f"{tap_base_url}/healthz", timeout_seconds=args.startup_timeout_seconds):
            raise RuntimeError("tap proxy failed to become healthy")

        gateway_command = [
            sys.executable,
            str(repo_root / "modeio-middleware" / "scripts" / "middleware_gateway.py"),
            "--host",
            args.gateway_host,
            "--port",
            str(gateway_port),
            "--upstream-chat-url",
            f"{tap_base_url}/v1/chat/completions",
            "--upstream-responses-url",
            f"{tap_base_url}/v1/responses",
        ]
        gateway_process, gateway_log_handle = _start_logged_process(
            command=gateway_command,
            cwd=repo_root,
            env=env,
            log_path=gateway_log_path,
        )
        if not _wait_for_url(gateway_health_url, timeout_seconds=args.startup_timeout_seconds):
            raise RuntimeError("middleware gateway failed to become healthy")

        report["gateway"] = {
            "baseUrl": gateway_base_url,
            "healthUrl": gateway_health_url,
            "logPath": str(gateway_log_path),
            "host": args.gateway_host,
            "port": gateway_port,
        }
        report["tap"]["baseUrl"] = tap_base_url
        report["tap"]["port"] = tap_port

        setup_payload = _run_setup(
            repo_root=repo_root,
            env=env,
            gateway_base_url=gateway_base_url,
            opencode_config_path=paths["opencode_config"],
            openclaw_config_path=paths["openclaw_config"],
            openclaw_models_cache_path=paths["openclaw_models_cache"],
            timeout_seconds=args.command_timeout_seconds,
        )
        report["setup"] = setup_payload
        _write_json(setup_payload_path, setup_payload)

        report["openclawLiveModelPatch"] = _rewrite_openclaw_model_for_live(
            config_path=paths["openclaw_config"],
            models_cache_path=paths["openclaw_models_cache"],
            model_id=args.model,
        )

        report["gatewayChecks"] = list(
            _run_gateway_smoke_checks(
                gateway_base_url=gateway_base_url,
                model=args.model,
                run_id=run_id,
                timeout_seconds=args.command_timeout_seconds,
                tap_jsonl_path=tap_jsonl_path,
            )
        )

        for index, agent in enumerate(agents, start=1):
            report["agents"].append(
                _run_agent_check(
                    agent=agent,
                    index=index,
                    run_id=run_id,
                    model=args.model,
                    repo_root=repo_root,
                    run_dir=run_dir,
                    env=env,
                    timeout_seconds=args.command_timeout_seconds,
                    tap_jsonl_path=tap_jsonl_path,
                )
            )

        gateway_checks_ok = all(bool(item.get("ok")) for item in report.get("gatewayChecks", []))
        report["success"] = gateway_checks_ok and all(bool(agent.get("ok")) for agent in report["agents"])
    except Exception as error:
        report["success"] = False
        report["error"] = str(error)
    finally:
        _stop_process(gateway_process)
        _stop_process(tap_process)
        _close_handle(gateway_log_handle)
        _close_handle(tap_log_handle)

    report["finishedAt"] = _utc_stamp()
    _write_json(summary_path, report)

    if not args.keep_sandbox:
        shutil.rmtree(paths["root"], ignore_errors=True)

    print(f"[smoke-agent-matrix] summary: {summary_path}")
    for agent_report in report.get("agents", []):
        if not isinstance(agent_report, dict):
            continue
        tap = agent_report.get("tap")
        window = tap.get("window") if isinstance(tap, dict) else {}
        event_count = window.get("eventCount") if isinstance(window, dict) else None
        success_count = window.get("successCount") if isinstance(window, dict) else None
        print(
            "[smoke-agent-matrix] "
            f"{agent_report.get('name')}: ok={agent_report.get('ok')} "
            f"exit={agent_report.get('exitCode')} tapEvents={event_count} tap2xx={success_count}"
        )

    for check in report.get("gatewayChecks", []):
        if not isinstance(check, dict):
            continue
        print(
            "[smoke-agent-matrix] "
            f"check {check.get('name')}: ok={check.get('ok')} "
            f"status={check.get('status')}"
        )

    if report.get("error"):
        print(f"[smoke-agent-matrix] error: {report['error']}")

    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
