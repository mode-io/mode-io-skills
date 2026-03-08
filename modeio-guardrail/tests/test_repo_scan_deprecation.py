#!/usr/bin/env python3

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "modeio-guardrail" / "scripts" / "skill_safety_assessment.py"


class TestRepoScanDeprecation(unittest.TestCase):
    def test_repo_scan_script_exits_with_migration_message(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("modeio-skill-audit", result.stderr)
        self.assertIn("repository scanning", result.stderr)


if __name__ == "__main__":
    unittest.main()
