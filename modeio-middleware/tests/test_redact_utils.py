#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "modeio-middleware"
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from modeio_middleware.core.contracts import ENDPOINT_CHAT_COMPLETIONS, ENDPOINT_RESPONSES
from modeio_middleware.plugins.redact_utils import restore_tokens_deep, shield_request_body


class TestRedactUtils(unittest.TestCase):
    def test_shield_request_body_redacts_repeated_email_with_stable_token(self):
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": "Email alice@example.com and cc alice@example.com",
                }
            ]
        }

        updated_body, redaction_count, entries = shield_request_body(
            ENDPOINT_CHAT_COMPLETIONS,
            payload,
            request_id="req_test",
        )

        content = updated_body["messages"][0]["content"]
        self.assertEqual(redaction_count, 2)
        self.assertEqual(len(entries), 1)
        self.assertNotIn("alice@example.com", content)
        self.assertEqual(content.count(entries[0]["placeholder"]), 2)

    def test_shield_request_body_redacts_responses_input_parts(self):
        payload = {
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Reach me at alice@example.com",
                        }
                    ],
                }
            ]
        }

        updated_body, redaction_count, entries = shield_request_body(
            ENDPOINT_RESPONSES,
            payload,
            request_id="req_test",
        )

        text = updated_body["input"][0]["content"][0]["text"]
        self.assertEqual(redaction_count, 1)
        self.assertEqual(len(entries), 1)
        self.assertNotIn("alice@example.com", text)

    def test_restore_tokens_deep_restores_nested_payload(self):
        entries = [
            {
                "placeholder": "__MIO_EMAIL_1_TOKEN__",
                "original": "alice@example.com",
                "type": "EMAIL",
            }
        ]
        payload = {
            "output_text": "Email __MIO_EMAIL_1_TOKEN__",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "__MIO_EMAIL_1_TOKEN__"}],
                }
            ],
        }

        restored, replaced = restore_tokens_deep(payload, entries)

        self.assertEqual(replaced, 2)
        self.assertEqual(restored["output_text"], "Email alice@example.com")
        self.assertEqual(restored["output"][0]["content"][0]["text"], "alice@example.com")


if __name__ == "__main__":
    unittest.main()
