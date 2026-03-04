#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "modeio-guardrail" / "scripts" / "safety.py"
SCRIPTS_DIR = REPO_ROOT / "modeio-guardrail" / "scripts"

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

    def _run_main(self, args):
        out = StringIO()
        err = StringIO()
        exit_code = 0
        with patch.object(sys, "argv", ["safety.py", *args]), redirect_stdout(out), redirect_stderr(err):
            try:
                safety.main()
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
                exit_code = code
        return exit_code, out.getvalue(), err.getvalue()

    def test_success_envelope_shape(self):
        payload = safety._success_envelope({"approved": True})
        self.assertTrue(payload["success"])
        self.assertEqual(payload["tool"], "modeio-guardrail")
        self.assertEqual(payload["mode"], "api")
        self.assertEqual(payload["data"]["approved"], True)

    def test_error_envelope_shape(self):
        payload = safety._error_envelope(
            error_type="network_error",
            message="request failed",
            status_code=503,
        )
        self.assertFalse(payload["success"])
        self.assertEqual(payload["tool"], "modeio-guardrail")
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
        self.assertEqual(payload["tool"], "modeio-guardrail")
        self.assertEqual(payload["error"]["type"], "network_error")

    def test_main_json_http_error_is_classified_as_api_error(self):
        http_error = safety.requests.HTTPError("upstream 503")
        response = safety.requests.Response()
        response.status_code = 503
        http_error.response = response

        with patch("safety.detect_safety", side_effect=http_error):
            code, stdout, _ = self._run_main(["--input", "DROP TABLE users", "--json"])

        self.assertEqual(code, 1)
        payload = json.loads(stdout)
        self.assertEqual(payload["error"]["type"], "api_error")
        self.assertEqual(payload["error"]["status_code"], 503)

    def test_main_json_invalid_payload_type_is_api_error(self):
        with patch("safety.detect_safety", return_value=["bad"]):
            code, stdout, _ = self._run_main(["--input", "DROP TABLE users", "--json"])

        self.assertEqual(code, 1)
        payload = json.loads(stdout)
        self.assertEqual(payload["error"]["type"], "api_error")
        self.assertEqual(payload["error"]["details"]["receivedType"], "list")

    def test_main_json_invalid_json_error_is_api_error(self):
        with patch("safety.detect_safety", side_effect=ValueError("bad json")):
            code, stdout, _ = self._run_main(["--input", "DROP TABLE users", "--json"])

        self.assertEqual(code, 1)
        payload = json.loads(stdout)
        self.assertEqual(payload["error"]["type"], "api_error")

    def test_main_json_normalizes_null_approved_to_false(self):
        with patch(
            "safety.detect_safety",
            return_value={"approved": None, "risk_level": "medium", "recommendation": "review"},
        ):
            code, stdout, _ = self._run_main(["--input", "rm -rf /tmp/cache", "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["approved"], False)
        self.assertEqual(payload["data"]["risk_level"], "medium")


if __name__ == "__main__":
    unittest.main()
