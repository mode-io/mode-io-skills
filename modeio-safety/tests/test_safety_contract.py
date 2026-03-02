#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "modeio-safety" / "scripts" / "safety.py"
SCRIPTS_DIR = REPO_ROOT / "modeio-safety" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import safety  # noqa: E402


class TestSafetyContract(unittest.TestCase):
    def _run_cli(self, args, env=None):
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH)] + args,
            capture_output=True,
            text=True,
            env=merged_env,
        )

    def test_success_envelope_shape(self):
        payload = safety._success_envelope({"approved": True})
        self.assertTrue(payload["success"])
        self.assertEqual(payload["tool"], "modeio-safety")
        self.assertEqual(payload["mode"], "api")
        self.assertEqual(payload["data"]["approved"], True)

    def test_error_envelope_shape(self):
        payload = safety._error_envelope(
            error_type="network_error",
            message="request failed",
            status_code=503,
        )
        self.assertFalse(payload["success"])
        self.assertEqual(payload["tool"], "modeio-safety")
        self.assertEqual(payload["mode"], "api")
        self.assertEqual(payload["error"]["type"], "network_error")
        self.assertEqual(payload["error"]["status_code"], 503)

    def test_json_validation_error_for_empty_input(self):
        result = self._run_cli(["--input", "   ", "--json"])
        self.assertEqual(result.returncode, 1)

        payload = json.loads(result.stdout)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["type"], "validation_error")

    def test_json_network_error_envelope(self):
        result = self._run_cli(
            ["--input", "Delete all log files in production", "--json"],
            env={"SAFETY_API_URL": "http://127.0.0.1:9"},
        )
        self.assertEqual(result.returncode, 1)

        payload = json.loads(result.stdout)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["tool"], "modeio-safety")
        self.assertEqual(payload["error"]["type"], "network_error")


if __name__ == "__main__":
    unittest.main()
