#!/usr/bin/env python3
"""
Optional install/uninstall helper for modeio-redact git pre-commit scanning.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from detect_local import PROFILE_CHOICES

START_MARKER = "# >>> modeio-redact-precommit-scan >>>"
END_MARKER = "# <<< modeio-redact-precommit-scan <<<"
MANAGED_BLOCK_PATTERN = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL)


class SetupError(RuntimeError):
    pass


def _run_git_command(args: Sequence[str], *, repo_root: Optional[Path] = None) -> str:
    command = ["git", *args]
    try:
        result = subprocess.run(
            command,
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise SetupError("git executable not found") from error

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        detail = stderr if stderr else "unknown git error"
        raise SetupError(f"git command failed: {' '.join(command)} ({detail})")

    return result.stdout


def resolve_repo_root() -> Path:
    output = _run_git_command(["rev-parse", "--show-toplevel"]).strip()
    if not output:
        raise SetupError("unable to resolve git repository root")
    return Path(output)


def resolve_hook_path(repo_root: Path) -> Path:
    hooks_path_raw = _run_git_command(["rev-parse", "--git-path", "hooks"], repo_root=repo_root).strip()
    if not hooks_path_raw:
        raise SetupError("unable to resolve git hooks directory")

    hooks_dir = Path(hooks_path_raw)
    if not hooks_dir.is_absolute():
        hooks_dir = repo_root / hooks_dir
    return hooks_dir / "pre-commit"


def _to_shell_path(path: Path, repo_root: Path) -> str:
    resolved = path.expanduser().resolve()
    root_resolved = repo_root.resolve()

    try:
        relative_path = resolved.relative_to(root_resolved)
    except ValueError:
        return shlex.quote(str(resolved))

    return f'"$MODEIO_REPO_ROOT/{relative_path.as_posix()}"'


def _validate_optional_json_path(raw_path: Optional[str], label: str) -> Optional[Path]:
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if not path.exists():
        raise SetupError(f"{label} not found: {path}")
    return path


def build_managed_block(
    *,
    repo_root: Path,
    profile: str,
    minimum_risk_level: str,
    python_executable: str,
    allowlist_file: Optional[Path],
    blocklist_file: Optional[Path],
    thresholds_file: Optional[Path],
) -> str:
    scan_script = repo_root / "modeio-redact" / "scripts" / "precommit_scan.py"
    if not scan_script.exists():
        raise SetupError(f"scan script not found: {scan_script}")

    command_parts = [
        '"$MODEIO_PYTHON"',
        '"$MODEIO_REPO_ROOT/modeio-redact/scripts/precommit_scan.py"',
        "--profile",
        shlex.quote(profile),
        "--minimum-risk-level",
        shlex.quote(minimum_risk_level),
    ]

    if allowlist_file:
        command_parts.extend(["--allowlist-file", _to_shell_path(allowlist_file, repo_root)])
    if blocklist_file:
        command_parts.extend(["--blocklist-file", _to_shell_path(blocklist_file, repo_root)])
    if thresholds_file:
        command_parts.extend(["--thresholds-file", _to_shell_path(thresholds_file, repo_root)])

    command_line = " ".join(command_parts)
    preferred_python = shlex.quote(python_executable)

    return "\n".join(
        [
            START_MARKER,
            'MODEIO_REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"',
            'if [ -z "$MODEIO_REPO_ROOT" ]; then',
            '  echo "[modeio-redact] Unable to resolve repository root." >&2',
            "  exit 1",
            "fi",
            f"MODEIO_PREFERRED_PYTHON={preferred_python}",
            'if command -v "$MODEIO_PREFERRED_PYTHON" >/dev/null 2>&1; then',
            '  MODEIO_PYTHON="$MODEIO_PREFERRED_PYTHON"',
            "elif command -v python3 >/dev/null 2>&1; then",
            '  MODEIO_PYTHON="python3"',
            "elif command -v python >/dev/null 2>&1; then",
            '  MODEIO_PYTHON="python"',
            "else",
            '  echo "[modeio-redact] Python interpreter not found; blocking commit." >&2',
            "  exit 1",
            "fi",
            command_line,
            "MODEIO_SCAN_EXIT=$?",
            'if [ "$MODEIO_SCAN_EXIT" -ne 0 ]; then',
            '  exit "$MODEIO_SCAN_EXIT"',
            "fi",
            END_MARKER,
        ]
    )


def _wrap_as_default_hook(managed_block: str) -> str:
    return "\n".join(
        [
            "#!/usr/bin/env sh",
            "set -e",
            "",
            managed_block,
            "",
        ]
    )


def _upsert_managed_block(
    existing_content: str,
    managed_block: str,
    *,
    append: bool,
    overwrite: bool,
) -> Tuple[str, str]:
    if MANAGED_BLOCK_PATTERN.search(existing_content):
        return MANAGED_BLOCK_PATTERN.sub(managed_block, existing_content, count=1), "updated"

    if not existing_content.strip():
        return _wrap_as_default_hook(managed_block), "installed"

    if overwrite:
        return _wrap_as_default_hook(managed_block), "overwritten"

    if append:
        base = existing_content.rstrip("\n")
        return base + "\n\n" + managed_block + "\n", "appended"

    raise SetupError(
        "existing pre-commit hook detected and it is not managed by modeio-redact. "
        "Use --append to keep existing logic, or --overwrite to replace it."
    )


def _ensure_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_hook_file(
    hook_path: Path,
    *,
    managed_block: str,
    append: bool,
    overwrite: bool,
) -> Dict[str, Any]:
    existing_content = ""
    if hook_path.exists():
        existing_content = hook_path.read_text(encoding="utf-8")

    updated_content, action = _upsert_managed_block(
        existing_content,
        managed_block,
        append=append,
        overwrite=overwrite,
    )

    changed = updated_content != existing_content
    if changed:
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text(updated_content, encoding="utf-8")

    if hook_path.exists():
        _ensure_executable(hook_path)

    return {
        "path": str(hook_path),
        "action": action,
        "changed": changed,
    }


def _remove_managed_block(existing_content: str) -> Tuple[str, bool]:
    if not MANAGED_BLOCK_PATTERN.search(existing_content):
        return existing_content, False

    updated_content = MANAGED_BLOCK_PATTERN.sub("", existing_content, count=1)
    updated_content = re.sub(r"\n{3,}", "\n\n", updated_content)
    if updated_content and not updated_content.endswith("\n"):
        updated_content += "\n"
    return updated_content, True


def _is_effectively_empty_hook(content: str) -> bool:
    allowed_lines = {
        "#!/usr/bin/env sh",
        "#!/bin/sh",
        "set -e",
        "set -eu",
    }
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return True
    return all(line in allowed_lines for line in lines)


def uninstall_hook_file(hook_path: Path) -> Dict[str, Any]:
    if not hook_path.exists():
        return {
            "path": str(hook_path),
            "changed": False,
            "action": "missing",
            "reason": "hook_not_found",
        }

    existing_content = hook_path.read_text(encoding="utf-8")
    updated_content, changed = _remove_managed_block(existing_content)
    if not changed:
        return {
            "path": str(hook_path),
            "changed": False,
            "action": "unchanged",
            "reason": "managed_block_not_found",
        }

    if _is_effectively_empty_hook(updated_content):
        hook_path.unlink()
        return {
            "path": str(hook_path),
            "changed": True,
            "action": "removed_file",
            "reason": "managed_block_removed",
        }

    hook_path.write_text(updated_content, encoding="utf-8")
    _ensure_executable(hook_path)
    return {
        "path": str(hook_path),
        "changed": True,
        "action": "removed_block",
        "reason": "managed_block_removed",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install or uninstall optional modeio-redact pre-commit scan hook."
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove modeio-managed pre-commit block from hook file.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append modeio block if an unmanaged pre-commit hook already exists.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite unmanaged pre-commit hook with modeio-managed hook.",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILE_CHOICES,
        default="balanced",
        help="Detector profile passed to precommit_scan.py (default: balanced).",
    )
    parser.add_argument(
        "--minimum-risk-level",
        choices=("low", "medium", "high"),
        default="medium",
        help="Minimum risk level that blocks commit (default: medium).",
    )
    parser.add_argument(
        "--allowlist-file",
        type=str,
        default=None,
        help="Optional JSON allowlist file path.",
    )
    parser.add_argument(
        "--blocklist-file",
        type=str,
        default=None,
        help="Optional JSON blocklist file path.",
    )
    parser.add_argument(
        "--thresholds-file",
        type=str,
        default=None,
        help="Optional JSON threshold override file path.",
    )
    parser.add_argument(
        "--python-executable",
        type=str,
        default="python3",
        help="Preferred python executable used by hook (default: python3).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON report.",
    )
    return parser


def _print_human_result(result: Dict[str, Any], *, uninstall: bool) -> None:
    if uninstall:
        if result.get("changed"):
            print(f"Uninstall complete: {result['action']}")
            print(f"Hook path: {result['path']}")
        else:
            print("Uninstall skipped: no managed modeio block found.")
            print(f"Hook path: {result['path']}")
            if result.get("reason"):
                print(f"Reason: {result['reason']}")
        return

    if result.get("changed"):
        print(f"Install complete: {result['action']}")
        print(f"Hook path: {result['path']}")
        print("The scan is optional and can be bypassed with: git commit --no-verify")
    else:
        print("Install skipped: hook content already up to date.")
        print(f"Hook path: {result['path']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.append and args.overwrite:
        message = "append and overwrite cannot be used together"
        if args.json:
            print(json.dumps({"success": False, "error": {"type": "validation_error", "message": message}}, indent=2))
            return 2
        print(f"Error: {message}", file=sys.stderr)
        return 2

    try:
        repo_root = resolve_repo_root()
        hook_path = resolve_hook_path(repo_root)

        if args.uninstall:
            result = uninstall_hook_file(hook_path)
            payload = {
                "success": True,
                "action": "uninstall",
                "repoRoot": str(repo_root),
                "result": result,
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                _print_human_result(result, uninstall=True)
            return 0

        allowlist_file = _validate_optional_json_path(args.allowlist_file, "allowlist file")
        blocklist_file = _validate_optional_json_path(args.blocklist_file, "blocklist file")
        thresholds_file = _validate_optional_json_path(args.thresholds_file, "thresholds file")

        managed_block = build_managed_block(
            repo_root=repo_root,
            profile=args.profile,
            minimum_risk_level=args.minimum_risk_level,
            python_executable=args.python_executable,
            allowlist_file=allowlist_file,
            blocklist_file=blocklist_file,
            thresholds_file=thresholds_file,
        )

        result = install_hook_file(
            hook_path,
            managed_block=managed_block,
            append=args.append,
            overwrite=args.overwrite,
        )
        payload = {
            "success": True,
            "action": "install",
            "repoRoot": str(repo_root),
            "result": result,
            "config": {
                "profile": args.profile,
                "minimumRiskLevel": args.minimum_risk_level,
                "pythonExecutable": args.python_executable,
                "allowlistFile": str(allowlist_file) if allowlist_file else None,
                "blocklistFile": str(blocklist_file) if blocklist_file else None,
                "thresholdsFile": str(thresholds_file) if thresholds_file else None,
            },
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _print_human_result(result, uninstall=False)
        return 0

    except SetupError as error:
        payload = {
            "success": False,
            "tool": "modeio-redact-precommit-setup",
            "error": {
                "type": "runtime_error",
                "message": str(error),
            },
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
