from __future__ import annotations

from pathlib import Path
from typing import List


def build_agent_command(
    *,
    agent: str,
    token: str,
    model: str,
    claude_model: str,
    repo_root: Path,
    codex_output_path: Path,
    claude_settings_path: Path | None,
    timeout_seconds: int,
) -> List[str]:
    prompt = f"Reply with exactly this token and nothing else: {token}"

    if agent == "codex":
        return [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
            "--model",
            model,
            "--output-last-message",
            str(codex_output_path),
            prompt,
        ]

    if agent == "opencode":
        return [
            "opencode",
            "run",
            "--format",
            "json",
            "--model",
            model,
            "--dir",
            str(repo_root),
            prompt,
        ]

    if agent == "openclaw":
        return [
            "openclaw",
            "agent",
            "--local",
            "--json",
            "--session-id",
            f"modeio-smoke-{token.lower()}",
            "--thinking",
            "off",
            "--timeout",
            str(timeout_seconds),
            "--message",
            prompt,
        ]

    if agent == "claude":
        if claude_settings_path is None:
            raise ValueError("claude_settings_path is required for claude smoke runs")
        return [
            "claude",
            "--print",
            "--output-format",
            "text",
            "--permission-mode",
            "bypassPermissions",
            "--no-session-persistence",
            "--settings",
            str(claude_settings_path),
            "--model",
            claude_model,
            prompt,
        ]

    raise ValueError(f"unsupported agent: {agent}")
