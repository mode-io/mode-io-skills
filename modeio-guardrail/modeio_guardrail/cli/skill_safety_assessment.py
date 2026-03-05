#!/usr/bin/env python3
"""
modeio-guardrail Skill Safety Assessment utilities.

This module provides three workflows:
1) deterministic static script scan (low-noise evidence collection)
2) prompt payload rendering with scan highlights
3) assessment output validation against scan evidence
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

TOOL_NAME = "modeio-guardrail"
SCAN_VERSION = "skill-safety-assessment-v1"

SEVERITY_SCORES = {
    "low": 3,
    "medium": 8,
    "high": 15,
    "critical": 25,
}

SEVERITY_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

CONFIDENCE_RANK = {
    "high": 3,
    "medium": 2,
    "low": 1,
}

VERDICTS = {"ALLOW", "WARN", "BLOCK", "UNVERIFIED"}
SEVERITY_VALUES = {"low", "medium", "high", "critical"}
CATEGORY_VALUES = {"A", "B", "C", "D", "E"}
CONFIDENCE_VALUES = {"low", "medium", "high"}

SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    ".open-next",
    ".wrangler",
}

SKIP_ANALYSIS_DIR_PARTS = {
    "tests",
    "test",
    "__tests__",
    "spec",
    "specs",
    "fixtures",
}

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
}

HIGH_PRIORITY_FILES = {
    "SKILL.md",
    "README.md",
    "Makefile",
    "Dockerfile",
    "package.json",
    "setup.py",
    "pyproject.toml",
}

EXECUTABLE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".yml",
    ".yaml",
}

MAX_FILE_BYTES = 600_000

PROMPT_INJECTION_RULES = [
    (
        re.compile(r"\bignore\s+(all\s+)?(previous|prior|system)\s+(instructions|prompts?)\b", re.IGNORECASE),
        "A_IGNORE_PREVIOUS_INSTRUCTIONS",
        "medium",
        "medium",
        "Potential instruction-override phrase in prompt surface.",
        "Remove override wording and enforce explicit system/developer instruction precedence.",
    ),
    (
        re.compile(r"\bbypass\s+(all\s+)?(safety|guardrails?)\b", re.IGNORECASE),
        "A_BYPASS_SAFETY_DIRECTIVE",
        "high",
        "high",
        "Potential safety bypass directive in prompt surface.",
        "Replace with policy-preserving instruction and explicit refusal behavior.",
    ),
    (
        re.compile(r"\boverride\s+(system|developer)\s+instructions\b", re.IGNORECASE),
        "A_OVERRIDE_SYSTEM_DIRECTIVE",
        "high",
        "high",
        "Potential authority escalation in prompt content.",
        "Remove override language and keep hierarchy constraints explicit.",
    ),
]

PROMPT_INJECTION_NEGATION_HINTS = (
    "do not",
    "never",
    "don't",
    "example",
    "examples",
    "threat",
    "detect",
    "scan",
    "checklist",
    "contract",
)

SHELL_OBFUSCATION_RULES = [
    (
        re.compile(r"\bbase64\s+(-d|--decode)\b.*\|\s*(bash|sh|zsh)\b", re.IGNORECASE),
        "D_BASE64_PIPE_EXEC",
        "critical",
        "high",
        "Base64 decode piped directly into shell execution.",
        "Replace with explicit artifact verification and avoid decode-then-exec pipelines.",
    ),
    (
        re.compile(r"\b(curl|wget)\b[^\n]*\|\s*(bash|sh|zsh)\b", re.IGNORECASE),
        "D_DOWNLOAD_PIPE_EXEC",
        "critical",
        "high",
        "Remote content piped directly to shell execution.",
        "Download to disk, verify checksum/signature, and execute only trusted local files.",
    ),
    (
        re.compile(r"\bpowershell(\.exe)?\b[^\n]*\s-(enc|encodedcommand)\b", re.IGNORECASE),
        "D_POWERSHELL_ENCODED_COMMAND",
        "high",
        "high",
        "Encoded PowerShell command execution can hide runtime behavior.",
        "Use plain-text reviewed scripts with explicit argument handling.",
    ),
]

CODE_OBFUSCATION_RULES = [
    (
        re.compile(r"\bexec\s*\(\s*base64\.b64decode\s*\(", re.IGNORECASE),
        "D_PY_EXEC_BASE64",
        "high",
        "high",
        "Python base64 decode chained into exec().",
        "Avoid dynamic exec of decoded payloads and use audited static code paths.",
    ),
    (
        re.compile(r"\b(eval|Function)\s*\(.*Buffer\.from\s*\(.*base64", re.IGNORECASE),
        "D_JS_EVAL_BASE64",
        "high",
        "medium",
        "JavaScript eval/function constructor over base64-decoded payload.",
        "Avoid dynamic evaluation and parse trusted structured data instead.",
    ),
]

DESTRUCTIVE_RULES = [
    (
        re.compile(r"\brm\s+-rf\s+--no-preserve-root\b", re.IGNORECASE),
        "C_RM_NO_PRESERVE_ROOT",
        "critical",
        "high",
        "Explicit no-preserve-root recursive deletion command.",
        "Remove destructive root deletion behavior and require scoped paths.",
    ),
    (
        re.compile(r"\brm\s+-rf\s+/(\s|$)", re.IGNORECASE),
        "C_RM_ROOT_RECURSIVE",
        "critical",
        "high",
        "Recursive deletion targeting filesystem root.",
        "Constrain deletion to explicit non-root paths with allowlisted boundaries.",
    ),
    (
        re.compile(r"\bmkfs\.[a-z0-9]+\b", re.IGNORECASE),
        "C_FILESYSTEM_FORMAT",
        "critical",
        "high",
        "Filesystem formatting command detected.",
        "Gate formatting operations behind explicit operator confirmation and safe targets.",
    ),
    (
        re.compile(r"\bdd\s+if=.*\sof=/dev/", re.IGNORECASE),
        "C_RAW_DEVICE_WRITE",
        "critical",
        "medium",
        "Raw write to block device path detected.",
        "Use non-destructive tooling and explicit target validation before write operations.",
    ),
    (
        re.compile(r"\bchmod\s+777\s+/(etc|bin|usr|var|root)\b", re.IGNORECASE),
        "C_WORLD_WRITABLE_SYSTEM_PATH",
        "high",
        "high",
        "World-writable permission change on sensitive system path.",
        "Use least-privilege permissions and avoid 777 on system directories.",
    ),
    (
        re.compile(r"\bchown\s+root(?::root)?\s+/(etc|bin|usr|var|root)\b", re.IGNORECASE),
        "C_ROOT_OWNERSHIP_SYSTEM_PATH",
        "high",
        "medium",
        "Ownership escalation on sensitive system path.",
        "Restrict ownership changes to audited maintenance workflows.",
    ),
]

ENV_ENUM_PATTERNS = [
    re.compile(r"\bos\.environ\b(?!\s*(\.get|\[))", re.IGNORECASE),
    re.compile(r"\bdict\(\s*os\.environ\s*\)", re.IGNORECASE),
    re.compile(r"\bprocess\.env\b(?!\s*(\.|\[))", re.IGNORECASE),
    re.compile(r"\bObject\.entries\(\s*process\.env\s*\)", re.IGNORECASE),
    re.compile(r"\bprintenv\b", re.IGNORECASE),
    re.compile(r"\benv\s*\|", re.IGNORECASE),
]

NETWORK_SINK_PATTERNS = [
    re.compile(r"\brequests\.(post|get|put|request|patch)\s*\(", re.IGNORECASE),
    re.compile(r"\bfetch\s*\(", re.IGNORECASE),
    re.compile(r"\baxios\.(post|get|put|request|patch)\s*\(", re.IGNORECASE),
    re.compile(r"\burllib\.request\b", re.IGNORECASE),
    re.compile(r"\bhttpx\.(post|get|put|request|patch)\s*\(", re.IGNORECASE),
    re.compile(r"\bcurl\b[^\n]*https?://", re.IGNORECASE),
    re.compile(r"\bwget\b[^\n]*https?://", re.IGNORECASE),
    re.compile(r"\bInvoke-WebRequest\b", re.IGNORECASE),
]

SUSPICIOUS_EGRESS_PATTERNS = [
    re.compile(r"webhook", re.IGNORECASE),
    re.compile(r"discord(?:app)?\.com/api/webhooks", re.IGNORECASE),
    re.compile(r"pastebin", re.IGNORECASE),
    re.compile(r"requestbin", re.IGNORECASE),
    re.compile(r"ngrok", re.IGNORECASE),
    re.compile(r"telegram", re.IGNORECASE),
]

SECRET_NAME_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|private[_-]?key|password|session[_-]?key)",
    re.IGNORECASE,
)

INSTALL_HOOK_NAMES = {
    "preinstall",
    "install",
    "postinstall",
    "prepare",
    "prepublish",
    "prepack",
    "postpack",
}

HOOK_RISK_PATTERNS = [
    re.compile(r"\b(curl|wget|Invoke-WebRequest)\b", re.IGNORECASE),
    re.compile(r"\|\s*(bash|sh|zsh|pwsh|powershell)\b", re.IGNORECASE),
    re.compile(r"\b(node|python|ruby|perl)\s+-e\b", re.IGNORECASE),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\bchmod\s+777\b", re.IGNORECASE),
]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_rel(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return str(rel).replace("\\", "/")


def _is_test_or_fixture_path(rel_path: Path) -> bool:
    lower_parts = {part.lower() for part in rel_path.parts}
    if lower_parts & SKIP_ANALYSIS_DIR_PARTS:
        return True

    name = rel_path.name.lower()
    if name.startswith("test_"):
        return True
    if name.endswith("_test.py") or name.endswith(".spec.js") or name.endswith(".spec.ts"):
        return True
    return False


def _should_scan_file(rel_path: Path) -> bool:
    if _is_test_or_fixture_path(rel_path):
        return False
    if rel_path.name in HIGH_PRIORITY_FILES:
        return True
    if rel_path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    rel_str = str(rel_path).replace("\\", "/")
    if rel_str.startswith(".github/workflows/"):
        return True
    return False


def _is_executable_surface(rel_path: Path) -> bool:
    if rel_path.suffix.lower() in EXECUTABLE_EXTENSIONS:
        return True
    if rel_path.name in {"Makefile", "Dockerfile", "package.json"}:
        return True
    rel_str = str(rel_path).replace("\\", "/")
    if rel_str.startswith(".github/workflows/"):
        return True
    return False


def _is_prompt_surface(rel_path: Path) -> bool:
    rel_str = str(rel_path).replace("\\", "/").lower()
    if rel_path.name == "SKILL.md":
        return True
    if "/prompts/" in f"/{rel_str}":
        return True
    return False


def _truncate_snippet(line: str, limit: int = 180) -> str:
    value = line.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _line_has_any(line: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    for pattern in patterns:
        if pattern.search(line):
            return True
    return False


def _line_number_for_value(lines: Sequence[str], value: str) -> int:
    needle = value.strip()
    if not needle:
        return 1
    for idx, line in enumerate(lines, start=1):
        if needle in line:
            return idx
    return 1


def _add_finding(
    findings: List[Dict[str, Any]],
    dedupe: set[tuple[str, str, int, str]],
    *,
    rule_id: str,
    category: str,
    severity: str,
    confidence: str,
    file_path: str,
    line: int,
    snippet: str,
    why: str,
    fix: str,
    tags: Optional[Sequence[str]] = None,
) -> None:
    dedupe_key = (rule_id, file_path, line, snippet)
    if dedupe_key in dedupe:
        return
    dedupe.add(dedupe_key)
    findings.append(
        {
            "rule_id": rule_id,
            "category": category,
            "severity": severity,
            "confidence": confidence,
            "file": file_path,
            "line": int(line),
            "snippet": _truncate_snippet(snippet),
            "why": why,
            "fix": fix,
            "tags": list(tags or []),
        }
    )


def _is_pattern_or_comment_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    if "re.compile(" in line:
        return True
    if stripped.startswith(("assert ", "self.assert", "expect(")):
        return True
    return False


def _scan_prompt_injection(
    rel_path: str,
    lines: Sequence[str],
    findings: List[Dict[str, Any]],
    dedupe: set[tuple[str, str, int, str]],
) -> None:
    for idx, line in enumerate(lines, start=1):
        lowered = line.lower()
        if any(hint in lowered for hint in PROMPT_INJECTION_NEGATION_HINTS):
            continue
        for pattern, rule_id, severity, confidence, why, fix in PROMPT_INJECTION_RULES:
            if pattern.search(line):
                _add_finding(
                    findings,
                    dedupe,
                    rule_id=rule_id,
                    category="A",
                    severity=severity,
                    confidence=confidence,
                    file_path=rel_path,
                    line=idx,
                    snippet=line,
                    why=why,
                    fix=fix,
                    tags=["prompt-injection"],
                )


def _scan_obfuscation_and_download_exec(
    rel_path: str,
    lines: Sequence[str],
    findings: List[Dict[str, Any]],
    dedupe: set[tuple[str, str, int, str]],
    *,
    is_shell_surface: bool,
) -> None:
    active_rules = SHELL_OBFUSCATION_RULES if is_shell_surface else CODE_OBFUSCATION_RULES
    for idx, line in enumerate(lines, start=1):
        if _is_pattern_or_comment_line(line):
            continue
        for pattern, rule_id, severity, confidence, why, fix in active_rules:
            if pattern.search(line):
                _add_finding(
                    findings,
                    dedupe,
                    rule_id=rule_id,
                    category="D",
                    severity=severity,
                    confidence=confidence,
                    file_path=rel_path,
                    line=idx,
                    snippet=line,
                    why=why,
                    fix=fix,
                    tags=["obfuscation", "remote-exec"],
                )


def _scan_destructive_commands(
    rel_path: str,
    lines: Sequence[str],
    findings: List[Dict[str, Any]],
    dedupe: set[tuple[str, str, int, str]],
) -> None:
    for idx, line in enumerate(lines, start=1):
        if _is_pattern_or_comment_line(line):
            continue
        for pattern, rule_id, severity, confidence, why, fix in DESTRUCTIVE_RULES:
            if pattern.search(line):
                _add_finding(
                    findings,
                    dedupe,
                    rule_id=rule_id,
                    category="C",
                    severity=severity,
                    confidence=confidence,
                    file_path=rel_path,
                    line=idx,
                    snippet=line,
                    why=why,
                    fix=fix,
                    tags=["destructive", "privilege"],
                )


def _nearest_distance(points_a: Sequence[int], points_b: Sequence[int]) -> Tuple[int, int]:
    best_distance = 10**9
    best_b = points_b[0]
    for a in points_a:
        for b in points_b:
            distance = abs(a - b)
            if distance < best_distance:
                best_distance = distance
                best_b = b
    return best_distance, best_b


def _scan_secret_exfiltration(
    rel_path: str,
    lines: Sequence[str],
    findings: List[Dict[str, Any]],
    dedupe: set[tuple[str, str, int, str]],
) -> None:
    env_lines: List[int] = []
    sink_lines: List[int] = []
    suspicious_sink_lines: List[int] = []
    secret_name_lines: List[int] = []

    for idx, line in enumerate(lines, start=1):
        if _is_pattern_or_comment_line(line):
            continue
        if _line_has_any(line, ENV_ENUM_PATTERNS):
            env_lines.append(idx)
        if _line_has_any(line, NETWORK_SINK_PATTERNS):
            sink_lines.append(idx)
        if _line_has_any(line, SUSPICIOUS_EGRESS_PATTERNS):
            suspicious_sink_lines.append(idx)
        if SECRET_NAME_PATTERN.search(line):
            secret_name_lines.append(idx)

    if env_lines and sink_lines:
        if suspicious_sink_lines:
            _, target_line = _nearest_distance(env_lines, suspicious_sink_lines)
            snippet = lines[target_line - 1] if target_line - 1 < len(lines) else ""
            _add_finding(
                findings,
                dedupe,
                rule_id="B_ENV_ENUM_SUSPICIOUS_EGRESS",
                category="B",
                severity="critical",
                confidence="high",
                file_path=rel_path,
                line=target_line,
                snippet=snippet,
                why="Environment enumeration appears alongside suspicious external egress destination.",
                fix="Remove broad env access and block outbound transfer of credential material.",
                tags=["secret-exfiltration", "network-egress"],
            )
        else:
            distance, target_line = _nearest_distance(env_lines, sink_lines)
            if distance <= 40:
                snippet = lines[target_line - 1] if target_line - 1 < len(lines) else ""
                _add_finding(
                    findings,
                    dedupe,
                    rule_id="B_ENV_ENUM_NETWORK_CORRELATION",
                    category="B",
                    severity="high",
                    confidence="medium",
                    file_path=rel_path,
                    line=target_line,
                    snippet=snippet,
                    why="Environment enumeration is correlated with outbound network activity.",
                    fix="Constrain env access to explicit allowlisted keys and avoid transmitting secret-bearing payloads.",
                    tags=["secret-exfiltration", "network-egress"],
                )

    if secret_name_lines and suspicious_sink_lines:
        distance, target_line = _nearest_distance(secret_name_lines, suspicious_sink_lines)
        if distance <= 30:
            snippet = lines[target_line - 1] if target_line - 1 < len(lines) else ""
            _add_finding(
                findings,
                dedupe,
                rule_id="B_SECRET_NAME_SUSPICIOUS_EGRESS",
                category="B",
                severity="high",
                confidence="high",
                file_path=rel_path,
                line=target_line,
                snippet=snippet,
                why="Secret-like identifiers appear near suspicious outbound endpoint usage.",
                fix="Remove secret transfer paths and enforce approved destination controls.",
                tags=["secret-exfiltration", "suspicious-endpoint"],
            )


def _scan_package_hooks(
    rel_path: str,
    lines: Sequence[str],
    text: str,
    findings: List[Dict[str, Any]],
    dedupe: set[tuple[str, str, int, str]],
) -> None:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return

    scripts = payload.get("scripts")
    if not isinstance(scripts, dict):
        return

    for hook_name in sorted(INSTALL_HOOK_NAMES):
        command = scripts.get(hook_name)
        if not isinstance(command, str):
            continue
        if not _line_has_any(command, HOOK_RISK_PATTERNS):
            continue

        lowered = command.lower()
        severity = "high"
        confidence = "high"
        rule_id = "E_INSTALL_HOOK_RISKY_COMMAND"
        why = "Install/update lifecycle hook executes high-risk shell behavior."
        fix = "Remove risky hook execution or replace with reviewed local build steps."

        if re.search(r"\b(curl|wget)\b[^\n]*\|\s*(bash|sh|zsh)", lowered):
            severity = "critical"
            rule_id = "E_INSTALL_HOOK_DOWNLOAD_EXEC"
            why = "Install hook performs download-and-exec pipeline."
            fix = "Disallow remote pipe execution in install hooks and require verified local artifacts."

        line_no = _line_number_for_value(lines, f'"{hook_name}"')
        _add_finding(
            findings,
            dedupe,
            rule_id=rule_id,
            category="E",
            severity=severity,
            confidence=confidence,
            file_path=rel_path,
            line=line_no,
            snippet=f"{hook_name}: {command}",
            why=why,
            fix=fix,
            tags=["install-hook", hook_name],
        )


def _scan_workflow_run_blocks(
    rel_path: str,
    lines: Sequence[str],
    findings: List[Dict[str, Any]],
    dedupe: set[tuple[str, str, int, str]],
) -> None:
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        single_match = re.match(r"^\s*run:\s*(.+)$", line)
        if single_match and single_match.group(1).strip() not in {"|", ">"}:
            command = single_match.group(1).strip()
            _scan_workflow_command(rel_path, idx + 1, command, findings, dedupe)
            idx += 1
            continue

        block_match = re.match(r"^(\s*)run:\s*[|>]\s*$", line)
        if block_match:
            base_indent = len(block_match.group(1))
            idx += 1
            while idx < len(lines):
                block_line = lines[idx]
                if not block_line.strip():
                    idx += 1
                    continue
                current_indent = len(block_line) - len(block_line.lstrip(" "))
                if current_indent <= base_indent:
                    break
                _scan_workflow_command(rel_path, idx + 1, block_line.strip(), findings, dedupe)
                idx += 1
            continue

        idx += 1


def _scan_workflow_command(
    rel_path: str,
    line_no: int,
    command: str,
    findings: List[Dict[str, Any]],
    dedupe: set[tuple[str, str, int, str]],
) -> None:
    if re.search(r"\b(curl|wget)\b[^\n]*\|\s*(bash|sh|zsh)", command, re.IGNORECASE):
        _add_finding(
            findings,
            dedupe,
            rule_id="E_WORKFLOW_DOWNLOAD_EXEC",
            category="E",
            severity="critical",
            confidence="high",
            file_path=rel_path,
            line=line_no,
            snippet=command,
            why="Workflow run step includes download-and-exec behavior.",
            fix="Download artifacts securely, verify integrity, and execute only trusted local files.",
            tags=["workflow", "download-exec"],
        )
        return

    if re.search(r"\brm\s+-rf\s+/(\s|$)", command, re.IGNORECASE):
        _add_finding(
            findings,
            dedupe,
            rule_id="E_WORKFLOW_ROOT_DELETE",
            category="E",
            severity="critical",
            confidence="high",
            file_path=rel_path,
            line=line_no,
            snippet=command,
            why="Workflow run step includes recursive root deletion.",
            fix="Limit deletion paths to explicit temporary directories.",
            tags=["workflow", "destructive"],
        )


def _score_findings(findings: Sequence[Dict[str, Any]]) -> Tuple[int, bool]:
    total = 0
    has_obfuscation = False
    for finding in findings:
        total += SEVERITY_SCORES.get(str(finding.get("severity", "low")), 0)
        if str(finding.get("category")) == "D":
            has_obfuscation = True
    if has_obfuscation:
        total += 10
    return min(total, 100), has_obfuscation


def _suggested_verdict(score: int, findings: Sequence[Dict[str, Any]], partial_coverage: bool) -> str:
    has_critical = any(f.get("severity") == "critical" for f in findings)
    has_high = any(f.get("severity") == "high" for f in findings)
    if partial_coverage and not findings:
        return "UNVERIFIED"
    if has_critical or score >= 70:
        return "BLOCK"
    if score >= 35 or has_high:
        return "WARN"
    if partial_coverage:
        return "UNVERIFIED"
    return "ALLOW"


def _finding_sort_key(finding: Dict[str, Any]) -> Tuple[int, int, str, int, str]:
    severity_rank = SEVERITY_RANK.get(str(finding.get("severity", "low")), 0)
    confidence_rank = CONFIDENCE_RANK.get(str(finding.get("confidence", "low")), 0)
    file_value = str(finding.get("file", ""))
    line_value = int(finding.get("line", 0))
    rule_id = str(finding.get("rule_id", ""))
    return (-severity_rank, -confidence_rank, file_value, line_value, rule_id)


def scan_repository(target_repo: Path, max_findings: int = 80) -> Dict[str, Any]:
    target_repo = target_repo.resolve()
    findings: List[Dict[str, Any]] = []
    dedupe: set[tuple[str, str, int, str]] = set()

    stats: Dict[str, Any] = {
        "total_files_seen": 0,
        "candidate_files": 0,
        "files_scanned": 0,
        "skipped_large_files": 0,
        "skipped_unreadable_files": 0,
    }

    for dirpath, dirnames, filenames in os.walk(target_repo):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIR_NAMES]
        root = Path(dirpath)
        for filename in filenames:
            stats["total_files_seen"] += 1
            abs_path = root / filename
            rel_path = abs_path.relative_to(target_repo)

            if not _should_scan_file(rel_path):
                continue

            stats["candidate_files"] += 1
            try:
                file_size = abs_path.stat().st_size
            except OSError:
                stats["skipped_unreadable_files"] += 1
                continue

            if file_size > MAX_FILE_BYTES:
                stats["skipped_large_files"] += 1
                continue

            try:
                text = abs_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    text = abs_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    stats["skipped_unreadable_files"] += 1
                    continue
            except OSError:
                stats["skipped_unreadable_files"] += 1
                continue

            if "\x00" in text:
                stats["skipped_unreadable_files"] += 1
                continue

            stats["files_scanned"] += 1
            rel = _safe_rel(abs_path, target_repo)
            lines = text.splitlines()

            is_executable = _is_executable_surface(rel_path)
            is_prompt = _is_prompt_surface(rel_path)
            rel_str = str(rel_path).replace("\\", "/")
            is_shell_surface = rel_path.suffix.lower() in {".sh", ".bash", ".zsh", ".ps1"}
            if rel_str.startswith(".github/workflows/"):
                is_shell_surface = True

            if is_prompt:
                _scan_prompt_injection(rel, lines, findings, dedupe)

            if is_executable:
                _scan_obfuscation_and_download_exec(
                    rel,
                    lines,
                    findings,
                    dedupe,
                    is_shell_surface=is_shell_surface,
                )
                _scan_destructive_commands(rel, lines, findings, dedupe)
                _scan_secret_exfiltration(rel, lines, findings, dedupe)

            if rel_path.name == "package.json":
                _scan_package_hooks(rel, lines, text, findings, dedupe)

            if rel_str.startswith(".github/workflows/") and rel_path.suffix.lower() in {".yml", ".yaml"}:
                _scan_workflow_run_blocks(rel, lines, findings, dedupe)

    findings_sorted = sorted(findings, key=_finding_sort_key)
    if max_findings > 0:
        findings_sorted = findings_sorted[:max_findings]

    for idx, finding in enumerate(findings_sorted, start=1):
        finding["evidence_id"] = f"E-{idx:03d}"

    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for finding in findings_sorted:
        severity = str(finding.get("severity", "low"))
        if severity in severity_counts:
            severity_counts[severity] += 1

    risk_score, obfuscation_bonus = _score_findings(findings_sorted)
    partial_coverage = bool(stats["skipped_large_files"] or stats["skipped_unreadable_files"])

    coverage_notes: List[str] = []
    if stats["skipped_large_files"]:
        coverage_notes.append(
            f"Skipped {stats['skipped_large_files']} large file(s) over {MAX_FILE_BYTES} bytes."
        )
    if stats["skipped_unreadable_files"]:
        coverage_notes.append(f"Skipped {stats['skipped_unreadable_files']} unreadable or binary file(s).")
    if not coverage_notes:
        coverage_notes.append("Coverage complete for configured file classes.")

    suggested_verdict = _suggested_verdict(risk_score, findings_sorted, partial_coverage)

    highlights: List[Dict[str, Any]] = []
    for finding in findings_sorted:
        if finding["severity"] in {"critical", "high", "medium"}:
            highlights.append(
                {
                    "evidence_id": finding["evidence_id"],
                    "severity": finding["severity"],
                    "category": finding["category"],
                    "file": finding["file"],
                    "line": finding["line"],
                    "summary": (
                        f"{finding['evidence_id']} [{finding['severity']}/{finding['category']}] "
                        f"{finding['file']}:{finding['line']} - {finding['why']}"
                    ),
                }
            )
    highlights = highlights[:12]

    required_highlight_refs = [
        item["evidence_id"] for item in highlights if item["severity"] in {"critical", "high"}
    ]

    return {
        "version": SCAN_VERSION,
        "tool": TOOL_NAME,
        "target_repo": str(target_repo),
        "generated_at_utc": _now_utc_iso(),
        "summary": {
            "total_files_seen": stats["total_files_seen"],
            "candidate_files": stats["candidate_files"],
            "files_scanned": stats["files_scanned"],
            "skipped_large_files": stats["skipped_large_files"],
            "skipped_unreadable_files": stats["skipped_unreadable_files"],
            "partial_coverage": partial_coverage,
            "coverage_notes": coverage_notes,
            "finding_count": len(findings_sorted),
            "severity_counts": severity_counts,
        },
        "scoring": {
            "risk_score": risk_score,
            "obfuscation_bonus_applied": obfuscation_bonus,
            "suggested_verdict": suggested_verdict,
        },
        "required_highlight_evidence_ids": required_highlight_refs,
        "highlights": highlights,
        "findings": findings_sorted,
    }


def build_prompt_payload(
    scan_result: Dict[str, Any],
    target_repo: str,
    context: Optional[str],
    focus: Optional[str],
    include_full_findings: bool,
) -> str:
    highlights = scan_result.get("highlights", [])
    required_refs = scan_result.get("required_highlight_evidence_ids", [])

    payload: Dict[str, Any] = {
        "target_repo": target_repo,
        "context": context or "",
        "focus": focus or "",
        "script_scan_summary": scan_result.get("summary", {}),
        "script_scan_scoring": scan_result.get("scoring", {}),
        "required_highlight_evidence_ids": required_refs,
        "script_scan_highlights": highlights,
    }

    if include_full_findings:
        payload["script_scan_findings"] = scan_result.get("findings", [])

    lines: List[str] = []
    lines.append("Skill Safety Assessment prompt input")
    lines.append("Use contract: modeio-guardrail/prompts/static_repo_scan.md")
    lines.append("")
    lines.append("SCRIPT_SCAN_HIGHLIGHTS")
    if highlights:
        for item in highlights:
            lines.append(f"- {item['summary']}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("SCRIPT_SCAN_JSON")
    lines.append("```json")
    lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
    lines.append("```")
    return "\n".join(lines)


def _extract_first_json_object(text: str) -> Optional[str]:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
            continue

    return None


def _extract_json_summary(assessment_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    heading = re.search(r"#\s*JSON_SUMMARY", assessment_text, flags=re.IGNORECASE)
    if not heading:
        return None, "Missing # JSON_SUMMARY section."

    tail = assessment_text[heading.end() :]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", tail, flags=re.IGNORECASE | re.DOTALL)
    candidate = fenced.group(1) if fenced else _extract_first_json_object(tail)
    if not candidate:
        return None, "Could not locate JSON object under # JSON_SUMMARY."

    try:
        parsed = json.loads(candidate)
    except ValueError as exc:
        return None, f"Invalid JSON_SUMMARY payload: {exc}"
    if not isinstance(parsed, dict):
        return None, "JSON_SUMMARY payload must be a JSON object."
    return parsed, None


def validate_assessment_output(
    assessment_text: str,
    scan_result: Dict[str, Any],
) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    summary, parse_error = _extract_json_summary(assessment_text)
    if parse_error:
        errors.append(parse_error)
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "stats": {},
        }

    verdict = summary.get("verdict")
    if verdict not in VERDICTS:
        errors.append("JSON_SUMMARY.verdict must be one of ALLOW/WARN/BLOCK/UNVERIFIED.")

    risk_score = summary.get("risk_score")
    if not isinstance(risk_score, int) or not (0 <= risk_score <= 100):
        errors.append("JSON_SUMMARY.risk_score must be an integer between 0 and 100.")

    confidence = summary.get("confidence")
    if confidence not in CONFIDENCE_VALUES:
        errors.append("JSON_SUMMARY.confidence must be one of low/medium/high.")

    findings = summary.get("findings")
    if not isinstance(findings, list):
        errors.append("JSON_SUMMARY.findings must be an array.")
        findings = []

    coverage_notes = summary.get("coverage_notes")
    if not isinstance(coverage_notes, str) or not coverage_notes.strip():
        errors.append("JSON_SUMMARY.coverage_notes must be a non-empty string.")

    scan_findings = scan_result.get("findings", [])
    evidence_by_id: Dict[str, Dict[str, Any]] = {}
    for item in scan_findings:
        evidence_id = item.get("evidence_id")
        if isinstance(evidence_id, str):
            evidence_by_id[evidence_id] = item

    required_refs = set(scan_result.get("required_highlight_evidence_ids", []) or [])
    seen_refs: set[str] = set()

    required_finding_keys = {
        "id",
        "severity",
        "category",
        "file",
        "line",
        "snippet",
        "why",
        "fix",
        "evidence_refs",
    }

    for idx, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            errors.append(f"findings[{idx}] must be an object.")
            continue

        missing = sorted(required_finding_keys - set(finding.keys()))
        if missing:
            errors.append(f"findings[{idx}] missing required keys: {', '.join(missing)}")
            continue

        severity = finding.get("severity")
        category = finding.get("category")
        if severity not in SEVERITY_VALUES:
            errors.append(f"findings[{idx}].severity must be low/medium/high/critical.")
        if category not in CATEGORY_VALUES:
            errors.append(f"findings[{idx}].category must be one of A/B/C/D/E.")

        refs = finding.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"findings[{idx}].evidence_refs must be a non-empty array.")
            continue

        finding_file = str(finding.get("file", "")).replace("\\", "/")
        finding_line = finding.get("line")
        if not isinstance(finding_line, int):
            errors.append(f"findings[{idx}].line must be an integer.")
            continue

        ref_has_location_match = False
        for ref in refs:
            if not isinstance(ref, str):
                errors.append(f"findings[{idx}] has non-string evidence ref.")
                continue
            evidence = evidence_by_id.get(ref)
            if evidence is None:
                errors.append(f"findings[{idx}] references unknown evidence id: {ref}")
                continue
            seen_refs.add(ref)

            evidence_file = str(evidence.get("file", "")).replace("\\", "/")
            evidence_line = int(evidence.get("line", 0))
            if evidence_file == finding_file and evidence_line == finding_line:
                ref_has_location_match = True

        if not ref_has_location_match:
            errors.append(
                f"findings[{idx}] file/line does not match any referenced evidence entry."
            )

    missing_required_refs = sorted(required_refs - seen_refs)
    if missing_required_refs:
        errors.append(
            "Missing required highlight evidence references: " + ", ".join(missing_required_refs)
        )

    partial_coverage = bool(scan_result.get("summary", {}).get("partial_coverage"))
    if partial_coverage and verdict == "ALLOW":
        errors.append("ALLOW verdict is invalid when script scan reports partial coverage.")

    if not findings and scan_result.get("findings"):
        warnings.append("Assessment contains no findings while script scan found evidence.")

    valid = len(errors) == 0
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "assessment_finding_count": len(findings),
            "script_finding_count": len(scan_result.get("findings", [])),
            "required_highlight_refs": sorted(required_refs),
            "referenced_evidence_ids": sorted(seen_refs),
        },
    }


def _print_scan_text(scan_result: Dict[str, Any]) -> None:
    summary = scan_result.get("summary", {})
    scoring = scan_result.get("scoring", {})
    print("Skill Safety Assessment scan complete")
    print(f"Target: {scan_result.get('target_repo')}")
    print(
        "Coverage: "
        f"scanned={summary.get('files_scanned', 0)} "
        f"candidate={summary.get('candidate_files', 0)} "
        f"partial={summary.get('partial_coverage', False)}"
    )
    print(
        "Risk: "
        f"score={scoring.get('risk_score', 0)} "
        f"suggested_verdict={scoring.get('suggested_verdict', 'UNVERIFIED')}"
    )

    highlights = scan_result.get("highlights", [])
    if not highlights:
        print("Highlights: none")
        return

    print("Highlights:")
    for item in highlights:
        print(f"- {item.get('summary')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Skill Safety Assessment utilities: deterministic scan, prompt payload rendering, "
            "and output validation."
        )
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Run deterministic static skill safety scan.")
    scan_parser.add_argument("--target-repo", required=True, help="Path to the repository to scan.")
    scan_parser.add_argument(
        "--max-findings",
        type=int,
        default=80,
        help="Maximum number of findings to include in output.",
    )
    scan_parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    scan_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional file path to write scan JSON.",
    )

    prompt_parser = subparsers.add_parser(
        "prompt",
        help="Render prompt payload with script scan highlights.",
    )
    prompt_parser.add_argument("--target-repo", required=True, help="Path to target repository.")
    prompt_parser.add_argument("--context", default=None, help="Optional environment/use-case context.")
    prompt_parser.add_argument("--focus", default=None, help="Optional extra concerns to prioritize.")
    prompt_parser.add_argument(
        "--scan-file",
        default=None,
        help="Optional existing scan JSON file. If omitted, scanner runs first.",
    )
    prompt_parser.add_argument(
        "--max-findings",
        type=int,
        default=80,
        help="Max findings when scanner runs inline.",
    )
    prompt_parser.add_argument(
        "--include-full-findings",
        action="store_true",
        help="Include full findings list in SCRIPT_SCAN_JSON payload.",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate assessment output against scan evidence references.",
    )
    validate_parser.add_argument("--scan-file", required=True, help="Scan JSON file from scan command.")
    validate_parser.add_argument(
        "--assessment-file",
        default=None,
        help="Assessment output file. If omitted, reads from stdin.",
    )
    validate_parser.add_argument("--json", action="store_true", help="Emit JSON validation report.")

    args = parser.parse_args()

    if args.command == "scan":
        target_repo = Path(args.target_repo).expanduser().resolve()
        if not target_repo.exists() or not target_repo.is_dir():
            print(f"Error: --target-repo must be an existing directory: {target_repo}", file=sys.stderr)
            return 2

        scan_result = scan_repository(target_repo=target_repo, max_findings=max(0, args.max_findings))

        if args.output:
            output_path = Path(args.output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(scan_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if args.json:
            print(json.dumps(scan_result, ensure_ascii=False, indent=2))
        else:
            _print_scan_text(scan_result)
        return 0

    if args.command == "prompt":
        target_repo = Path(args.target_repo).expanduser().resolve()
        if not target_repo.exists() or not target_repo.is_dir():
            print(f"Error: --target-repo must be an existing directory: {target_repo}", file=sys.stderr)
            return 2

        if args.scan_file:
            scan_file = Path(args.scan_file).expanduser().resolve()
            try:
                scan_result = json.loads(scan_file.read_text(encoding="utf-8"))
            except OSError as exc:
                print(f"Error: failed to read --scan-file: {exc}", file=sys.stderr)
                return 2
            except ValueError as exc:
                print(f"Error: invalid --scan-file JSON: {exc}", file=sys.stderr)
                return 2
        else:
            scan_result = scan_repository(target_repo=target_repo, max_findings=max(0, args.max_findings))

        prompt_text = build_prompt_payload(
            scan_result=scan_result,
            target_repo=str(target_repo),
            context=args.context,
            focus=args.focus,
            include_full_findings=bool(args.include_full_findings),
        )
        print(prompt_text)
        return 0

    if args.command == "validate":
        scan_file = Path(args.scan_file).expanduser().resolve()
        try:
            scan_result = json.loads(scan_file.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"Error: failed to read --scan-file: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"Error: invalid --scan-file JSON: {exc}", file=sys.stderr)
            return 2

        if args.assessment_file:
            assessment_path = Path(args.assessment_file).expanduser().resolve()
            try:
                assessment_text = assessment_path.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"Error: failed to read --assessment-file: {exc}", file=sys.stderr)
                return 2
        else:
            assessment_text = sys.stdin.read()

        report = validate_assessment_output(assessment_text=assessment_text, scan_result=scan_result)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print("Validation result:", "valid" if report.get("valid") else "invalid")
            if report.get("errors"):
                print("Errors:")
                for item in report["errors"]:
                    print(f"- {item}")
            if report.get("warnings"):
                print("Warnings:")
                for item in report["warnings"]:
                    print(f"- {item}")

        return 0 if report.get("valid") else 1

    print("Error: unknown command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
