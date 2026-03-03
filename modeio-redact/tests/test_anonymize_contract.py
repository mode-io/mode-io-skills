#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "modeio-redact" / "scripts" / "anonymize.py"
SCRIPTS_DIR = REPO_ROOT / "modeio-redact" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import anonymize  # noqa: E402


class TestAnonymizeContract(unittest.TestCase):
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

    def test_input_type_flag_removed(self):
        result = self._run_cli([
            "--input",
            "Email: alice@example.com",
            "--input-type",
            "file",
        ])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments: --input-type", result.stderr)

    def test_crossborder_requires_explicit_codes_in_json_mode(self):
        result = self._run_cli([
            "--input",
            "Name: John Doe, SSN: 123-45-6789",
            "--level",
            "crossborder",
            "--json",
        ])
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["tool"], "modeio-redact")
        self.assertEqual(payload["level"], "crossborder")
        self.assertEqual(payload["error"]["type"], "validation_error")

    def test_json_success_envelope_for_lite(self):
        result = self._run_cli([
            "--input",
            "Email: alice@example.com, Phone: 415-555-1234",
            "--level",
            "lite",
            "--json",
        ])
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)

        self.assertTrue(payload["success"])
        self.assertEqual(payload["tool"], "modeio-redact")
        self.assertEqual(payload["mode"], "local-regex")
        self.assertEqual(payload["level"], "lite")
        self.assertIn("anonymizedContent", payload["data"])
        self.assertIn("hasPII", payload["data"])

    def test_json_network_error_envelope_for_api_mode(self):
        result = self._run_cli(
            [
                "--input",
                "Email: alice@example.com",
                "--level",
                "dynamic",
                "--json",
            ],
            env={"ANONYMIZE_API_URL": "http://127.0.0.1:9"},
        )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)

        self.assertFalse(payload["success"])
        self.assertEqual(payload["mode"], "api")
        self.assertEqual(payload["level"], "dynamic")
        self.assertEqual(payload["error"]["type"], "network_error")

    @patch("anonymize.requests.post")
    def test_api_payload_uses_text_input_type_and_crossborder_codes(self, mock_post):
        fake_response = Mock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {
            "success": True,
            "data": {
                "anonymizedContent": "[REDACTED]",
                "hasPII": True,
            },
        }
        mock_post.return_value = fake_response

        result = anonymize.anonymize(
            "Name: John Doe, SSN: 123-45-6789",
            level="crossborder",
            sender_code="CN SHA",
            recipient_code="US NYC",
        )

        self.assertTrue(result["success"])
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["inputType"], "text")
        self.assertEqual(payload["level"], "crossborder")
        self.assertEqual(payload["senderCode"], "CN SHA")
        self.assertEqual(payload["recipientCode"], "US NYC")


if __name__ == "__main__":
    unittest.main()
