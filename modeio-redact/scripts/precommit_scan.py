#!/usr/bin/env python3
"""
Optional staged-diff scanner for git pre-commit hooks.

Scans added lines from `git diff --cached` with the local detector and
returns non-zero when findings meet the configured minimum risk level.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from detect_local import PROFILE_CHOICES, detect_sensitive_local

RISK_LEVEL_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
}

HUNK_HEADER_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class ScanError(RuntimeError):
    pass


@dataclass(frozen=True)
class AddedLine:
    path: str
    line_number: int
    content: str


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
        raise ScanError("git executable not found") from error

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        detail = stderr if stderr else "unknown git error"
        raise ScanError(f"git command failed: {' '.join(command)} ({detail})")

    return result.stdout


def resolve_repo_root() -> Path:
    output = _run_git_command(["rev-parse", "--show-toplevel"]).strip()
    if not output:
        raise ScanError("unable to resolve git repository root")
    return Path(output)


def read_staged_diff(repo_root: Path) -> str:
    return _run_git_command(
        ["diff", "--cached", "--unified=0", "--no-color", "--no-ext-diff", "--text", "--"],
        repo_root=repo_root,
    )


def parse_staged_added_lines(diff_text: str) -> List[AddedLine]:
    added_lines: List[AddedLine] = []
    current_path: Optional[str] = None
    current_new_line: Optional[int] = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            current_path = None
            current_new_line = None
            continue

        if raw_line.startswith("+++ "):
            target = raw_line[4:].strip()
            if target in {"/dev/null", "b/dev/null"}:
                current_path = None
            elif target.startswith("b/"):
                current_path = target[2:]
            else:
                current_path = target
            current_new_line = None
            continue

        hunk_match = HUNK_HEADER_PATTERN.match(raw_line)
        if hunk_match:
            current_new_line = int(hunk_match.group(1))
            continue

        if current_path is None or current_new_line is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            added_lines.append(
                AddedLine(
                    path=current_path,
                    line_number=current_new_line,
                    content=raw_line[1:],
                )
            )
            current_new_line += 1
            continue

        if raw_line.startswith("-") and not raw_line.startswith("---"):
            continue

        if raw_line.startswith(" "):
            current_new_line += 1
            continue

        if raw_line.startswith("\\ "):
            continue

    return added_lines


def _load_json_file(path_value: Optional[str], label: str) -> Optional[Any]:
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    if not path.exists():
        raise ScanError(f"{label} not found: {path}")

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ScanError(f"failed to read {label}: {path}") from error

    try:
        return json.loads(content)
    except ValueError as error:
        raise ScanError(f"invalid JSON in {label}: {path}") from error


def load_rule_list(path_value: Optional[str], label: str) -> Optional[List[Dict[str, Any]]]:
    payload = _load_json_file(path_value, label)
    if payload is None:
        return None
    if not isinstance(payload, list):
        raise ScanError(f"{label} must be a JSON array")
    return payload


def load_threshold_overrides(path_value: Optional[str]) -> Optional[Dict[str, float]]:
    payload = _load_json_file(path_value, "thresholds file")
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ScanError("thresholds file must be a JSON object")

    normalized: Dict[str, float] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise ScanError("threshold keys must be strings")
        if not isinstance(value, (int, float)):
            raise ScanError(f"threshold for '{key}' must be numeric")
        normalized[key] = float(value)
    return normalized


def _risk_rank(level: str) -> int:
    return RISK_LEVEL_RANK.get(level.lower(), -1)


def _masked_preview(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def collect_findings(
    added_lines: Sequence[AddedLine],
    *,
    profile: str,
    minimum_risk_level: str,
    allowlist_rules: Optional[List[Dict[str, Any]]],
    blocklist_rules: Optional[List[Dict[str, Any]]],
    threshold_overrides: Optional[Dict[str, float]],
) -> List[Dict[str, Any]]:
    minimum_rank = _risk_rank(minimum_risk_level)
    findings: List[Dict[str, Any]] = []

    for added_line in added_lines:
        if not added_line.content.strip():
            continue

        result = detect_sensitive_local(
            added_line.content,
            profile=profile,
            allowlist_rules=allowlist_rules,
            blocklist_rules=blocklist_rules,
            threshold_overrides=threshold_overrides,
        )

        for item in result.get("items", []):
            risk_level = str(item.get("riskLevel", "low")).lower()
            if _risk_rank(risk_level) < minimum_rank:
                continue

            raw_value = str(item.get("value", ""))
            findings.append(
                {
                    "path": added_line.path,
                    "line": added_line.line_number,
                    "type": item.get("type"),
                    "label": item.get("label"),
                    "riskLevel": risk_level,
                    "detectionScore": item.get("detectionScore"),
                    "detectionSource": item.get("detectionSource"),
                    "maskedValue": item.get("maskedValue"),
                    "valuePreview": _masked_preview(raw_value),
                }
            )

    return findings


def format_findings_report(findings: Sequence[Dict[str, Any]], *, max_findings: int) -> str:
    lines = [
        "[modeio-redact] Commit blocked: potential PII/secrets found in staged changes.",
    ]

    visible_findings = list(findings[:max_findings])
    for finding in visible_findings:
        lines.append(
            "  - "
            f"{finding['path']}:{finding['line']} "
            f"{finding['type']} "
            f"(risk={finding['riskLevel']}, source={finding['detectionSource']})"
        )

    hidden_count = len(findings) - len(visible_findings)
    if hidden_count > 0:
        lines.append(f"  - ... and {hidden_count} more finding(s)")

    lines.extend(
        [
            "[modeio-redact] Redact or remove sensitive values before committing.",
            "[modeio-redact] To bypass once, use: git commit --no-verify",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan staged git additions for PII/secrets using local Modeio detector."
    )
    parser.add_argument(
        "--profile",
        choices=PROFILE_CHOICES,
        default="balanced",
        help="Detector profile (default: balanced).",
    )
    parser.add_argument(
        "--minimum-risk-level",
        choices=("low", "medium", "high"),
        default="medium",
        help="Minimum item risk level that blocks commit (default: medium).",
    )
    parser.add_argument(
        "--allowlist-file",
        type=str,
        default=None,
        help="Optional JSON allowlist rules file.",
    )
    parser.add_argument(
        "--blocklist-file",
        type=str,
        default=None,
        help="Optional JSON blocklist rules file.",
    )
    parser.add_argument(
        "--thresholds-file",
        type=str,
        default=None,
        help="Optional JSON threshold override file.",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=20,
        help="Maximum findings to print in human output (default: 20).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print clean summary when no findings are present.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.max_findings <= 0:
        message = "max-findings must be > 0"
        if args.json:
            print(json.dumps({"success": False, "error": {"type": "validation_error", "message": message}}, indent=2))
            return 2
        print(f"Error: {message}", file=sys.stderr)
        return 2

    try:
        repo_root = resolve_repo_root()
        diff_text = read_staged_diff(repo_root)
        added_lines = parse_staged_added_lines(diff_text)

        allowlist_rules = load_rule_list(args.allowlist_file, "allowlist file")
        blocklist_rules = load_rule_list(args.blocklist_file, "blocklist file")
        threshold_overrides = load_threshold_overrides(args.thresholds_file)

        findings = collect_findings(
            added_lines,
            profile=args.profile,
            minimum_risk_level=args.minimum_risk_level,
            allowlist_rules=allowlist_rules,
            blocklist_rules=blocklist_rules,
            threshold_overrides=threshold_overrides,
        )

        payload = {
            "success": len(findings) == 0,
            "tool": "modeio-redact-precommit",
            "repoRoot": str(repo_root),
            "profile": args.profile,
            "minimumRiskLevel": args.minimum_risk_level,
            "stagedAddedLineCount": len(added_lines),
            "findingCount": len(findings),
            "findings": findings,
        }

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif findings:
            print(format_findings_report(findings, max_findings=args.max_findings), file=sys.stderr)
        elif args.verbose:
            print(
                f"[modeio-redact] Scan passed ({len(added_lines)} staged added lines scanned).",
                file=sys.stderr,
            )

        return 1 if findings else 0

    except ScanError as error:
        if args.json:
            print(
                json.dumps(
                    {
                        "success": False,
                        "tool": "modeio-redact-precommit",
                        "error": {
                            "type": "runtime_error",
                            "message": str(error),
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
