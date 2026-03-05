from __future__ import annotations

from pathlib import Path
from typing import List


def build_agent_command(
    *,
    agent: str,
    token: str,
    model: str,
    repo_root: Path,
    codex_output_path: Path,
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

    raise ValueError(f"unsupported agent: {agent}")
