#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile
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
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_cli(
                [
                    "--input",
                    "Email: alice@example.com, Phone: 415-555-1234",
                    "--level",
                    "lite",
                    "--json",
                ],
                env={"MODEIO_REDACT_MAP_DIR": tmpdir},
            )
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)

            self.assertTrue(payload["success"])
            self.assertEqual(payload["tool"], "modeio-redact")
            self.assertEqual(payload["mode"], "local-regex")
            self.assertEqual(payload["level"], "lite")
            self.assertIn("anonymizedContent", payload["data"])
            self.assertIn("hasPII", payload["data"])
            self.assertIn("mapRef", payload["data"])
            self.assertGreater(payload["data"]["mapRef"]["entryCount"], 0)
            self.assertTrue(Path(payload["data"]["mapRef"]["mapPath"]).exists())

    def test_json_success_without_pii_has_no_map_ref(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_cli(
                [
                    "--input",
                    "Completely harmless sentence without personal data.",
                    "--level",
                    "lite",
                    "--json",
                ],
                env={"MODEIO_REDACT_MAP_DIR": tmpdir},
            )
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["success"])
            self.assertFalse(payload["data"]["hasPII"])
            self.assertNotIn("mapRef", payload["data"])

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

    def test_txt_file_path_is_auto_resolved_and_redacted(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as input_file:
            input_file.write("Email: alice@example.com")
            file_path = input_file.name

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = self._run_cli(
                    [
                        "--input",
                        file_path,
                        "--level",
                        "lite",
                        "--json",
                    ],
                    env={"MODEIO_REDACT_MAP_DIR": tmpdir},
                )
            finally:
                os.unlink(file_path)

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["mode"], "local-regex")
        self.assertEqual(payload["level"], "lite")
        self.assertTrue(payload["data"]["hasPII"])
        self.assertIn("[EMAIL_1]", payload["data"]["anonymizedContent"])

    def test_markdown_file_path_is_auto_resolved_and_redacted(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as input_file:
            input_file.write("Contact: alice@example.com")
            file_path = input_file.name

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = self._run_cli(
                    [
                        "--input",
                        file_path,
                        "--level",
                        "lite",
                        "--json",
                    ],
                    env={"MODEIO_REDACT_MAP_DIR": tmpdir},
                )
            finally:
                os.unlink(file_path)

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["success"])
        self.assertIn("[EMAIL_1]", payload["data"]["anonymizedContent"])

    def test_unsupported_file_extension_returns_json_validation_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as input_file:
            input_file.write('{"email": "alice@example.com"}')
            file_path = input_file.name

        try:
            result = self._run_cli(
                [
                    "--input",
                    file_path,
                    "--level",
                    "dynamic",
                    "--json",
                ]
            )
        finally:
            os.unlink(file_path)

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["type"], "validation_error")

    @patch("anonymize.requests.post")
    def test_api_payload_uses_file_input_type_when_file_path_is_used(self, mock_post):
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

        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as input_file:
            input_file.write("Email: alice@example.com")
            file_path = input_file.name

        try:
            content, input_type = anonymize.resolve_input_source(file_path)
            result = anonymize.anonymize(content, level="dynamic", input_type=input_type)
        finally:
            os.unlink(file_path)

        self.assertTrue(result["success"])
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["inputType"], "file")

    def test_non_file_input_stays_text_mode(self):
        content, input_type = anonymize.resolve_input_source("Email: alice@example.com")
        self.assertEqual(input_type, "text")
        self.assertEqual(content, "Email: alice@example.com")

    def test_maybe_save_map_returns_none_without_entries(self):
        data = {"anonymizedContent": "No placeholders"}
        map_ref = anonymize._maybe_save_map(
            raw_input="No placeholders",
            level="lite",
            mode="local-regex",
            data=data,
        )
        self.assertIsNone(map_ref)
        self.assertNotIn("mapRef", data)

    def test_maybe_save_map_from_local_detection_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original = os.environ.get("MODEIO_REDACT_MAP_DIR")
            os.environ["MODEIO_REDACT_MAP_DIR"] = tmpdir
            try:
                data = {
                    "anonymizedContent": "Email: [EMAIL_1]",
                    "localDetection": {
                        "items": [
                            {
                                "maskedValue": "[EMAIL_1]",
                                "value": "alice@example.com",
                                "type": "email",
                            }
                        ]
                    },
                }
                map_ref = anonymize._maybe_save_map(
                    raw_input="Email: alice@example.com",
                    level="lite",
                    mode="local-regex",
                    data=data,
                )
                self.assertIsNotNone(map_ref)
                self.assertEqual(map_ref["entryCount"], 1)
                self.assertTrue(Path(map_ref["mapPath"]).exists())
            finally:
                if original is None:
                    os.environ.pop("MODEIO_REDACT_MAP_DIR", None)
                else:
                    os.environ["MODEIO_REDACT_MAP_DIR"] = original

    def test_maybe_save_map_from_api_mapping_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original = os.environ.get("MODEIO_REDACT_MAP_DIR")
            os.environ["MODEIO_REDACT_MAP_DIR"] = tmpdir
            try:
                data = {
                    "anonymizedContent": "Name: [NAME_1]",
                    "mapping": [
                        {
                            "anonymized": "[NAME_1]",
                            "original": "Alice",
                            "type": "name",
                        }
                    ],
                }
                map_ref = anonymize._maybe_save_map(
                    raw_input="Name: Alice",
                    level="dynamic",
                    mode="api",
                    data=data,
                )
                self.assertIsNotNone(map_ref)
                self.assertEqual(map_ref["entryCount"], 1)
                self.assertIn("mapRef", data)
            finally:
                if original is None:
                    os.environ.pop("MODEIO_REDACT_MAP_DIR", None)
                else:
                    os.environ["MODEIO_REDACT_MAP_DIR"] = original

    @patch("anonymize.save_map")
    def test_maybe_save_map_propagates_storage_error(self, mock_save_map):
        mock_save_map.side_effect = anonymize.MapStoreError("disk full")
        data = {
            "anonymizedContent": "Email: [EMAIL_1]",
            "mapping": [
                {
                    "anonymized": "[EMAIL_1]",
                    "original": "alice@example.com",
                    "type": "email",
                }
            ],
        }

        with self.assertRaises(anonymize.MapStoreError):
            anonymize._maybe_save_map(
                raw_input="Email: alice@example.com",
                level="dynamic",
                mode="api",
                data=data,
            )

    def test_append_warning_initializes_warning_list(self):
        data = {}
        anonymize._append_warning(data, code="map_persist_failed", message="boom")

        self.assertIn("warnings", data)
        self.assertEqual(len(data["warnings"]), 1)
        self.assertEqual(data["warnings"][0]["code"], "map_persist_failed")

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
