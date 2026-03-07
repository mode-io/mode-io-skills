#!/usr/bin/env python3
"""Report repo-local setup readiness for mode-io-skills."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence

TOOL_NAME = "modeio-skills-doctor"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _format_command(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _module_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _run(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _dependency_status() -> List[Dict[str, Any]]:
    return [
        {
            "package": "requests",
            "module": "requests",
            "requiredFor": "modeio-guardrail and api-backed modeio-redact",
            "optional": False,
            "installed": _module_installed("requests"),
        },
        {
            "package": "httpx",
            "module": "httpx",
            "requiredFor": "modeio-middleware upstream routing",
            "optional": False,
            "installed": _module_installed("httpx"),
        },
        {
            "package": "starlette",
            "module": "starlette",
            "requiredFor": "modeio-middleware ASGI transport",
            "optional": False,
            "installed": _module_installed("starlette"),
        },
        {
            "package": "uvicorn",
            "module": "uvicorn",
            "requiredFor": "modeio-middleware gateway server runtime",
            "optional": False,
            "installed": _module_installed("uvicorn"),
        },
        {
            "package": "python-docx",
            "module": "docx",
            "requiredFor": "modeio-redact .docx file workflows",
            "optional": True,
            "installed": _module_installed("docx"),
        },
        {
            "package": "PyMuPDF",
            "module": "fitz",
            "requiredFor": "modeio-redact .pdf file workflows",
            "optional": True,
            "installed": _module_installed("fitz"),
        },
    ]


def _env_status() -> List[Dict[str, Any]]:
    return [
        {
            "name": "ANONYMIZE_API_URL",
            "requiredFor": "optional anonymize endpoint override",
            "optional": True,
            "set": bool(os.environ.get("ANONYMIZE_API_URL")),
        },
        {
            "name": "SAFETY_API_URL",
            "requiredFor": "optional safety endpoint override",
            "optional": True,
            "set": bool(os.environ.get("SAFETY_API_URL")),
        },
        {
            "name": "MODEIO_GATEWAY_UPSTREAM_API_KEY",
            "requiredFor": "live modeio-middleware routing",
            "optional": True,
            "set": bool(os.environ.get("MODEIO_GATEWAY_UPSTREAM_API_KEY")),
        },
    ]


def _smoke_status(python_executable: str) -> List[Dict[str, Any]]:
    root = repo_root()
    checks: List[Dict[str, Any]] = []

    redact_command = [
        python_executable,
        "modeio-redact/scripts/anonymize.py",
        "--input",
        "Email: alice@example.com",
        "--level",
        "lite",
        "--json",
    ]
    redact_result = _run(redact_command, cwd=root)
    redact_ok = False
    redact_message = redact_result.stderr.strip()
    if redact_result.returncode == 0:
        try:
            payload = json.loads(redact_result.stdout)
            redact_ok = bool(payload.get("success"))
            redact_message = "lite anonymize ok" if redact_ok else "unexpected JSON payload"
        except ValueError:
            redact_message = "invalid JSON output"
    checks.append(
        {
            "name": "modeio-redact lite smoke",
            "ok": redact_ok,
            "command": _format_command(redact_command),
            "message": redact_message,
        }
    )

    guardrail_command = [python_executable, "modeio-guardrail/scripts/safety.py", "--help"]
    guardrail_result = _run(guardrail_command, cwd=root)
    checks.append(
        {
            "name": "modeio-guardrail CLI load",
            "ok": guardrail_result.returncode == 0,
            "command": _format_command(guardrail_command),
            "message": "help output ok" if guardrail_result.returncode == 0 else (guardrail_result.stderr.strip() or "command failed"),
        }
    )

    middleware_command = [
        python_executable,
        "modeio-middleware/scripts/setup_middleware_gateway.py",
        "--health-check",
        "--json",
    ]
    middleware_result = _run(middleware_command, cwd=root)
    middleware_ok = False
    middleware_message = middleware_result.stderr.strip()
    if middleware_result.returncode == 0:
        try:
            payload = json.loads(middleware_result.stdout)
            health = payload.get("gateway", {}).get("health", {})
            middleware_ok = True
            middleware_message = health.get("message", "setup helper ok")
        except ValueError:
            middleware_message = "invalid JSON output"
    checks.append(
        {
            "name": "modeio-middleware setup helper",
            "ok": middleware_ok,
            "command": _format_command(middleware_command),
            "message": middleware_message,
        }
    )

    return checks


def _summary(
    *,
    dependencies: List[Dict[str, Any]],
    smoke: List[Dict[str, Any]],
    env_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    blockers: List[str] = []
    warnings: List[str] = []

    for row in dependencies:
        if row["installed"]:
            continue
        if row["optional"]:
            warnings.append(f"Install {row['package']} for {row['requiredFor']}.")
        else:
            blockers.append(f"Install {row['package']} from requirements.txt for {row['requiredFor']}.")

    for row in smoke:
        if not row["ok"]:
            blockers.append(f"{row['name']} failed: {row['message']}")

    for row in env_rows:
        if row["name"] == "MODEIO_GATEWAY_UPSTREAM_API_KEY" and not row["set"]:
            warnings.append("Set MODEIO_GATEWAY_UPSTREAM_API_KEY before live middleware routing.")

    if blockers:
        overall = "error"
    elif warnings:
        overall = "warning"
    else:
        overall = "ok"

    return {
        "overall": overall,
        "blockers": blockers,
        "warnings": warnings,
    }


def collect_report(python_executable: str) -> Dict[str, Any]:
    dependencies = _dependency_status()
    env_rows = _env_status()
    smoke = _smoke_status(python_executable)
    summary = _summary(dependencies=dependencies, smoke=smoke, env_rows=env_rows)

    return {
        "success": True,
        "tool": TOOL_NAME,
        "repoRoot": str(repo_root()),
        "python": {
            "executable": python_executable,
            "version": sys.version.split()[0],
            "insideVenv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
        },
        "dependencies": dependencies,
        "env": env_rows,
        "smoke": smoke,
        "summary": summary,
    }


def _print_human(report: Dict[str, Any]) -> int:
    print("mode-io-skills doctor")
    print(f"- repo root: {report['repoRoot']}")
    print(
        f"- python: {report['python']['executable']} "
        f"(version {report['python']['version']}, inside venv={report['python']['insideVenv']})"
    )
    print("- dependencies:")
    for row in report["dependencies"]:
        status = "ok" if row["installed"] else ("warn" if row["optional"] else "error")
        print(f"  [{status}] {row['package']} - {row['requiredFor']}")
    print("- environment:")
    for row in report["env"]:
        status = "set" if row["set"] else "unset"
        print(f"  [{status}] {row['name']} - {row['requiredFor']}")
    print("- smoke:")
    for row in report["smoke"]:
        status = "ok" if row["ok"] else "error"
        print(f"  [{status}] {row['name']} - {row['message']}")
    print(f"- overall: {report['summary']['overall']}")
    if report["summary"]["blockers"]:
        print("- blockers:")
        for item in report["summary"]["blockers"]:
            print(f"  {item}")
    if report["summary"]["warnings"]:
        print("- warnings:")
        for item in report["summary"]["warnings"]:
            print(f"  {item}")
    return 0 if report["summary"]["overall"] != "error" else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check mode-io-skills setup readiness and print next fixes.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used for smoke commands.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = collect_report(args.python)
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["summary"]["overall"] != "error" else 1
    return _print_human(report)


if __name__ == "__main__":
    raise SystemExit(main())
