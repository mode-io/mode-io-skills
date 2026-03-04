#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ANONYMIZE_SCRIPT = REPO_ROOT / "modeio-redact" / "scripts" / "anonymize.py"
DEANONYMIZE_SCRIPT = REPO_ROOT / "modeio-redact" / "scripts" / "deanonymize.py"


class TestDeanonymizeContract(unittest.TestCase):
    def _run_cli(self, script_path, args, env=None):
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, str(script_path)] + args,
            capture_output=True,
            text=True,
            env=merged_env,
        )

    def test_deanonymize_uses_latest_map_by_default(self):
        source_text = "Email: alice@example.com"

        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"MODEIO_REDACT_MAP_DIR": tmpdir}
            anon_result = self._run_cli(
                ANONYMIZE_SCRIPT,
                [
                    "--input",
                    source_text,
                    "--level",
                    "lite",
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(anon_result.returncode, 0)
            anon_payload = json.loads(anon_result.stdout)
            anonymized_text = anon_payload["data"]["anonymizedContent"]

            deanonymize_result = self._run_cli(
                DEANONYMIZE_SCRIPT,
                [
                    "--input",
                    anonymized_text,
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(deanonymize_result.returncode, 0)

            payload = json.loads(deanonymize_result.stdout)
            self.assertTrue(payload["success"])
            self.assertEqual(payload["mode"], "local-map")
            self.assertEqual(payload["data"]["deanonymizedContent"], source_text)

    def test_deanonymize_accepts_map_id_reference(self):
        source_text = "Phone: 415-555-1234"

        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"MODEIO_REDACT_MAP_DIR": tmpdir}
            anon_result = self._run_cli(
                ANONYMIZE_SCRIPT,
                [
                    "--input",
                    source_text,
                    "--level",
                    "lite",
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(anon_result.returncode, 0)
            anon_payload = json.loads(anon_result.stdout)
            anonymized_text = anon_payload["data"]["anonymizedContent"]
            map_id = anon_payload["data"]["mapRef"]["mapId"]

            deanonymize_result = self._run_cli(
                DEANONYMIZE_SCRIPT,
                [
                    "--input",
                    anonymized_text,
                    "--map",
                    map_id,
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(deanonymize_result.returncode, 0)
            payload = json.loads(deanonymize_result.stdout)

            self.assertTrue(payload["success"])
            self.assertEqual(payload["data"]["deanonymizedContent"], source_text)
            self.assertEqual(payload["data"]["mapRef"]["mapId"], map_id)

    def test_deanonymize_accepts_map_path_reference(self):
        source_text = "Email: alice@example.com"

        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"MODEIO_REDACT_MAP_DIR": tmpdir}
            anon_result = self._run_cli(
                ANONYMIZE_SCRIPT,
                [
                    "--input",
                    source_text,
                    "--level",
                    "lite",
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(anon_result.returncode, 0)
            anon_payload = json.loads(anon_result.stdout)
            anonymized_text = anon_payload["data"]["anonymizedContent"]
            map_path = anon_payload["data"]["mapRef"]["mapPath"]

            result = self._run_cli(
                DEANONYMIZE_SCRIPT,
                [
                    "--input",
                    anonymized_text,
                    "--map",
                    map_path,
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)

            self.assertTrue(payload["success"])
            self.assertEqual(payload["data"]["deanonymizedContent"], source_text)

    def test_deanonymize_reports_map_error_when_no_maps_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"MODEIO_REDACT_MAP_DIR": tmpdir}
            result = self._run_cli(
                DEANONYMIZE_SCRIPT,
                [
                    "--input",
                    "Email: [EMAIL_1]",
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["success"])
            self.assertEqual(payload["error"]["type"], "map_error")

    def test_deanonymize_validation_error_on_empty_input(self):
        result = self._run_cli(
            DEANONYMIZE_SCRIPT,
            [
                "--input",
                "   ",
                "--json",
            ],
        )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["type"], "validation_error")

    def test_deanonymize_returns_map_error_for_invalid_map_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_map = Path(tmpdir) / "bad.json"
            bad_map.write_text("{broken", encoding="utf-8")

            result = self._run_cli(
                DEANONYMIZE_SCRIPT,
                [
                    "--input",
                    "Email: [EMAIL_1]",
                    "--map",
                    str(bad_map),
                    "--json",
                ],
            )
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)

            self.assertFalse(payload["success"])
            self.assertEqual(payload["error"]["type"], "map_error")

    def test_replacement_summary_counts_repeated_tokens(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            map_path = Path(tmpdir) / "summary-map.json"
            map_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "1",
                        "mapId": "summary-map",
                        "entries": [
                            {"placeholder": "[EMAIL_1]", "original": "alice@example.com", "type": "email"},
                            {"placeholder": "[PHONE_1]", "original": "415-555-1234", "type": "phone"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = self._run_cli(
                DEANONYMIZE_SCRIPT,
                [
                    "--input",
                    "[EMAIL_1] and [PHONE_1] and [EMAIL_1]",
                    "--map",
                    str(map_path),
                    "--json",
                ],
            )
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)

            summary = payload["data"]["replacementSummary"]
            self.assertEqual(summary["totalReplacements"], 3)
            self.assertEqual(summary["replacementsByType"]["email"], 2)
            self.assertEqual(summary["replacementsByType"]["phone"], 1)

    def test_hash_mismatch_produces_warning_but_succeeds(self):
        source_text = "Email: alice@example.com"

        with tempfile.TemporaryDirectory() as tmpdir:
            env = {"MODEIO_REDACT_MAP_DIR": tmpdir}
            anon_result = self._run_cli(
                ANONYMIZE_SCRIPT,
                [
                    "--input",
                    source_text,
                    "--level",
                    "lite",
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(anon_result.returncode, 0)
            anon_payload = json.loads(anon_result.stdout)
            anonymized_text = anon_payload["data"]["anonymizedContent"] + " extra"

            deanonymize_result = self._run_cli(
                DEANONYMIZE_SCRIPT,
                [
                    "--input",
                    anonymized_text,
                    "--json",
                ],
                env=env,
            )
            self.assertEqual(deanonymize_result.returncode, 0)
            payload = json.loads(deanonymize_result.stdout)

            self.assertTrue(payload["success"])
            warning_codes = [item["code"] for item in payload["data"].get("warnings", [])]
            self.assertIn("input_hash_mismatch", warning_codes)

    def test_longer_placeholder_replaced_first(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            map_path = Path(tmpdir) / "custom-map.json"
            map_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "1",
                        "mapId": "custom-map",
                        "createdAt": "2026-03-04T00:00:00Z",
                        "anonymizedHash": "",
                        "entries": [
                            {"placeholder": "[NAME_1]", "original": "Alice", "type": "name"},
                            {"placeholder": "[NAME_10]", "original": "Bob", "type": "name"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = self._run_cli(
                DEANONYMIZE_SCRIPT,
                [
                    "--input",
                    "[NAME_10] met [NAME_1]",
                    "--map",
                    str(map_path),
                    "--json",
                ],
            )
            self.assertEqual(result.returncode, 0)

            payload = json.loads(result.stdout)
            self.assertTrue(payload["success"])
            self.assertEqual(payload["data"]["deanonymizedContent"], "Bob met Alice")


if __name__ == "__main__":
    unittest.main()
