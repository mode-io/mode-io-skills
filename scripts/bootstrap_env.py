#!/usr/bin/env python3
"""Bootstrap a repo-local virtualenv for mode-io-skills."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Sequence

TOOL_NAME = "modeio-skills-bootstrap"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def activation_command(venv_dir: Path) -> str:
    if os.name == "nt":
        return f"{venv_dir}\\Scripts\\Activate.ps1"
    return f"source {shlex.quote(str(venv_dir / 'bin' / 'activate'))}"


def _format_command(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _run_command(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _error_payload(
    *,
    error_type: str,
    message: str,
    command: Sequence[str] | None = None,
    returncode: int | None = None,
    stderr: str | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "success": False,
        "tool": TOOL_NAME,
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    if command is not None:
        payload["error"]["command"] = _format_command(command)
    if returncode is not None:
        payload["error"]["returncode"] = returncode
    if stderr:
        payload["error"]["stderr"] = stderr
    return payload


def bootstrap_environment(
    *,
    python_executable: str,
    venv_dir: Path,
    skip_install: bool,
    upgrade_pip: bool,
) -> Dict[str, Any]:
    root = repo_root()
    requirements_path = root / "requirements.txt"
    created_venv = False

    if not venv_dir.exists():
        create_command = [python_executable, "-m", "venv", str(venv_dir)]
        create_result = _run_command(create_command, cwd=root)
        if create_result.returncode != 0:
            return _error_payload(
                error_type="command_failed",
                message="failed to create virtualenv",
                command=create_command,
                returncode=create_result.returncode,
                stderr=create_result.stderr.strip(),
            )
        created_venv = True

    venv_python = venv_python_path(venv_dir)
    if not venv_python.exists():
        return _error_payload(
            error_type="missing_python",
            message=f"virtualenv python not found at {venv_python}",
        )

    steps = []
    if upgrade_pip:
        steps.append([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    if not skip_install:
        steps.append([str(venv_python), "-m", "pip", "install", "-r", str(requirements_path)])

    for command in steps:
        result = _run_command(command, cwd=root)
        if result.returncode != 0:
            return _error_payload(
                error_type="command_failed",
                message="dependency installation failed",
                command=command,
                returncode=result.returncode,
                stderr=result.stderr.strip(),
            )

    return {
        "success": True,
        "tool": TOOL_NAME,
        "repoRoot": str(root),
        "venvDir": str(venv_dir),
        "venvPython": str(venv_python),
        "createdVenv": created_venv,
        "installedRequirements": not skip_install,
        "upgradedPip": upgrade_pip,
        "activationCommand": activation_command(venv_dir),
        "nextCommands": [
            activation_command(venv_dir),
            f"{shlex.quote(str(venv_python))} scripts/doctor_env.py",
            "make smoke-redact-lite",
            "make skill-audit-tests",
        ],
    }


def _print_human(payload: Dict[str, Any]) -> int:
    if not payload.get("success"):
        error = payload["error"]
        print("mode-io-skills bootstrap failed", file=sys.stderr)
        print(f"- reason: {error['message']}", file=sys.stderr)
        if error.get("command"):
            print(f"- command: {error['command']}", file=sys.stderr)
        if error.get("stderr"):
            print(f"- stderr: {error['stderr']}", file=sys.stderr)
        return 1

    print("mode-io-skills bootstrap complete")
    print(f"- repo root: {payload['repoRoot']}")
    print(f"- venv: {payload['venvDir']}")
    print(f"- python: {payload['venvPython']}")
    print(f"- created venv: {payload['createdVenv']}")
    print(f"- installed requirements: {payload['installedRequirements']}")
    print(f"- activation: {payload['activationCommand']}")
    print("- next:")
    for item in payload["nextCommands"]:
        print(f"  {item}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description="Create a repo-local .venv and install mode-io-skills requirements.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to create the virtualenv.")
    parser.add_argument("--venv-dir", default=str(root / ".venv"), help="Virtualenv directory path.")
    parser.add_argument("--skip-install", action="store_true", help="Create the virtualenv but skip pip install.")
    parser.add_argument("--upgrade-pip", action="store_true", help="Upgrade pip inside the virtualenv before install.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    payload = bootstrap_environment(
        python_executable=args.python,
        venv_dir=Path(args.venv_dir).expanduser(),
        skip_install=args.skip_install,
        upgrade_pip=args.upgrade_pip,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload.get("success") else 1
    return _print_human(payload)


if __name__ == "__main__":
    raise SystemExit(main())
