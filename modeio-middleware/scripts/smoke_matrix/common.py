from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

SUPPORTED_AGENTS = ("codex", "opencode", "openclaw", "claude")
UPSTREAM_KEY_FALLBACK_ENVS = ("ZENMUX_API_KEY", "OPENAI_API_KEY")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_repo_root(script_path: Path) -> Path:
    return script_path.resolve().parents[2]


def default_artifacts_root(script_path: Path) -> Path:
    return default_repo_root(script_path) / ".artifacts" / "middleware-smoke"


def parse_agents(raw: str) -> Tuple[str, ...]:
    parts = [part.strip().lower() for part in raw.split(",") if part.strip()]
    if not parts:
        raise ValueError("--agents must include at least one agent")

    invalid = [part for part in parts if part not in SUPPORTED_AGENTS]
    if invalid:
        raise ValueError(f"unsupported agents in --agents: {', '.join(invalid)}")

    deduped: List[str] = []
    for part in parts:
        if part not in deduped:
            deduped.append(part)
    return tuple(deduped)


def resolve_upstream_api_key(env: Dict[str, str], preferred_env: str) -> Tuple[str, str]:
    preferred_value = env.get(preferred_env, "").strip()
    if preferred_value:
        return preferred_value, preferred_env

    for candidate in UPSTREAM_KEY_FALLBACK_ENVS:
        value = env.get(candidate, "").strip()
        if value:
            return value, candidate

    searched = [preferred_env, *UPSTREAM_KEY_FALLBACK_ENVS]
    raise RuntimeError("missing upstream API key. Set one of: " + ", ".join(searched))


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def check_required_commands(agents: Sequence[str]) -> List[str]:
    required = set(agents)
    required.add("python3")
    return [name for name in sorted(required) if shutil.which(name) is None]


def run_command_capture(
    *,
    command: Sequence[str],
    cwd: Path,
    env: Dict[str, str],
    timeout_seconds: int,
) -> Dict[str, object]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "exitCode": int(completed.returncode),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "durationMs": duration_ms,
            "timedOut": False,
        }
    except subprocess.TimeoutExpired as error:
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "exitCode": 124,
            "stdout": error.stdout or "",
            "stderr": error.stderr or f"command timed out after {timeout_seconds}s",
            "durationMs": duration_ms,
            "timedOut": True,
        }


def wait_for_url(url: str, *, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as response:
                if 200 <= response.status < 300:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def load_tap_events(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return []

    rows: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def tap_token_metrics(events: Iterable[Dict[str, object]], token: str) -> Dict[str, object]:
    request_matches = 0
    success_matches = 0
    response_token_matches = 0
    paths: List[str] = []

    for event in events:
        request = event.get("request")
        response = event.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            continue

        body_preview = str(request.get("bodyPreview", ""))
        if token not in body_preview:
            continue

        request_matches += 1
        path = request.get("path")
        if isinstance(path, str):
            paths.append(path)

        status = response.get("status")
        try:
            status_code = int(status)
        except Exception:
            status_code = 0
        if 200 <= status_code < 300:
            success_matches += 1

        response_preview = str(response.get("bodyPreview", ""))
        if token in response_preview:
            response_token_matches += 1

    return {
        "requestMatches": request_matches,
        "successMatches": success_matches,
        "responseTokenMatches": response_token_matches,
        "paths": paths,
    }


def tap_window_metrics(events: Iterable[Dict[str, object]]) -> Dict[str, object]:
    event_count = 0
    success_count = 0
    paths: List[str] = []

    for event in events:
        request = event.get("request")
        response = event.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            continue

        event_count += 1
        path = request.get("path")
        if isinstance(path, str):
            paths.append(path)

        status = response.get("status")
        try:
            status_code = int(status)
        except Exception:
            status_code = 0
        if 200 <= status_code < 300:
            success_count += 1

    return {
        "eventCount": event_count,
        "successCount": success_count,
        "paths": paths,
    }


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
