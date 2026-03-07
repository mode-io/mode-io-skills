#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

from smoke_agent_matrix import parse_args  # noqa: E402
from smoke_matrix.agents import build_agent_command  # noqa: E402
from smoke_matrix.common import parse_agents  # noqa: E402
from smoke_matrix.sandbox import build_sandbox_paths  # noqa: E402


class TestSmokeAgentMatrixSupport(unittest.TestCase):
    def test_parse_agents_accepts_claude_and_dedupes(self):
        self.assertEqual(
            parse_agents("codex,claude,opencode,claude"),
            ("codex", "claude", "opencode"),
        )

    def test_build_sandbox_paths_includes_claude_settings(self):
        paths = build_sandbox_paths(Path("/tmp/modeio-smoke"))
        self.assertEqual(
            paths["claude_settings"],
            Path("/tmp/modeio-smoke/home/.claude/settings.json"),
        )

    def test_build_agent_command_for_claude_uses_print_mode_and_settings(self):
        command = build_agent_command(
            agent="claude",
            token="CLAUDE_TOKEN",
            model="openai/gpt-5.3-codex",
            claude_model="sonnet",
            repo_root=Path("/tmp/repo"),
            codex_output_path=Path("/tmp/codex-last-message.txt"),
            claude_settings_path=Path("/tmp/claude-settings.json"),
            timeout_seconds=30,
        )
        self.assertEqual(command[0], "claude")
        self.assertIn("--print", command)
        self.assertIn("--no-session-persistence", command)
        self.assertIn("--settings", command)
        self.assertEqual(command[command.index("--settings") + 1], "/tmp/claude-settings.json")
        self.assertIn("--model", command)
        self.assertEqual(command[command.index("--model") + 1], "sonnet")

    def test_parse_args_defaults_include_claude(self):
        args = parse_args([])
        self.assertEqual(args.agents, "codex,opencode,openclaw,claude")
        self.assertEqual(args.claude_model, "sonnet")


if __name__ == "__main__":
    unittest.main()
