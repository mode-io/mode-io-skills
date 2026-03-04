#!/usr/bin/env python3

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-redact" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

import prompt_gateway  # noqa: E402


class TestPromptGatewayContract(unittest.TestCase):
    def test_normalize_modeio_defaults_when_missing(self):
        body = {"model": "gpt-test"}
        options = prompt_gateway._normalize_modeio_options(body)

        self.assertEqual(options.policy, "strict")
        self.assertTrue(options.allow_degraded_unshield)
        self.assertNotIn("modeio", body)

    def test_normalize_modeio_strips_extension_from_payload(self):
        body = {
            "model": "gpt-test",
            "modeio": {
                "policy": "strict",
                "allow_degraded_unshield": False,
            },
        }
        options = prompt_gateway._normalize_modeio_options(body)

        self.assertEqual(options.policy, "strict")
        self.assertFalse(options.allow_degraded_unshield)
        self.assertNotIn("modeio", body)

    def test_make_signed_token_is_stable_and_well_formed(self):
        token_a = prompt_gateway._make_signed_token(
            secret=b"test-secret",
            request_id="req_123",
            entity_type="email",
            index=1,
            original="alice@example.com",
        )
        token_b = prompt_gateway._make_signed_token(
            secret=b"test-secret",
            request_id="req_123",
            entity_type="email",
            index=1,
            original="alice@example.com",
        )

        self.assertEqual(token_a, token_b)
        self.assertRegex(token_a, r"^__MIO_EMAIL_1_[A-F0-9]{10}__$")

    def test_replace_with_entries_prefers_longest_placeholder(self):
        text = "__MIO_NAME_10_ABCDEF1234__ then __MIO_NAME_1_ABCDEF1234__"
        entries = [
            {
                "placeholder": "__MIO_NAME_1_ABCDEF1234__",
                "original": "Alice",
                "type": "NAME",
            },
            {
                "placeholder": "__MIO_NAME_10_ABCDEF1234__",
                "original": "Bob",
                "type": "NAME",
            },
        ]

        restored, replaced = prompt_gateway._replace_with_entries(text, entries)
        self.assertEqual(restored, "Bob then Alice")
        self.assertEqual(replaced, 2)

    def test_validate_and_shield_payload_requires_model(self):
        with self.assertRaises(prompt_gateway.GatewayError) as ctx:
            prompt_gateway._validate_and_shield_payload(
                {"messages": [{"role": "user", "content": "hi"}]},
                request_id="req_test",
                secret=b"secret",
            )

        error = ctx.exception
        self.assertEqual(error.status, 400)
        self.assertEqual(error.code, "MODEIO_VALIDATION_ERROR")

    def test_validate_and_shield_payload_requires_messages(self):
        with self.assertRaises(prompt_gateway.GatewayError) as ctx:
            prompt_gateway._validate_and_shield_payload(
                {"model": "gpt-test", "messages": []},
                request_id="req_test",
                secret=b"secret",
            )

        self.assertEqual(ctx.exception.code, "MODEIO_VALIDATION_ERROR")

    def test_validate_and_shield_payload_rejects_non_object_message(self):
        with self.assertRaises(prompt_gateway.GatewayError) as ctx:
            prompt_gateway._validate_and_shield_payload(
                {"model": "gpt-test", "messages": ["bad"]},
                request_id="req_test",
                secret=b"secret",
            )

        self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(ctx.exception.code, "MODEIO_UNSUPPORTED_MESSAGE_CONTENT")

    def test_validate_and_shield_payload_accepts_null_content(self):
        result = prompt_gateway._validate_and_shield_payload(
            {
                "model": "gpt-test",
                "messages": [
                    {"role": "system", "content": None},
                    {"role": "user", "content": "harmless sentence"},
                ],
            },
            request_id="req_test",
            secret=b"secret",
        )

        self.assertEqual(result.redaction_count, 0)
        self.assertEqual(result.entries, [])

    def test_validate_and_shield_payload_handles_array_text_content(self):
        result = prompt_gateway._validate_and_shield_payload(
            {
                "model": "gpt-test",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Email alice@example.com now"},
                            {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                        ],
                    }
                ],
            },
            request_id="req_test",
            secret=b"secret",
        )

        self.assertGreaterEqual(result.redaction_count, 1)
        text_part = result.payload["messages"][0]["content"][0]["text"]
        self.assertIn("__MIO_EMAIL_", text_part)
        self.assertNotIn("alice@example.com", text_part)
        image_part = result.payload["messages"][0]["content"][1]
        self.assertEqual(image_part["type"], "image_url")

    def test_validate_and_shield_payload_reuses_same_token_across_messages(self):
        result = prompt_gateway._validate_and_shield_payload(
            {
                "model": "gpt-test",
                "messages": [
                    {"role": "user", "content": "Email alice@example.com once"},
                    {"role": "user", "content": "Email alice@example.com twice"},
                ],
            },
            request_id="req_test",
            secret=b"secret",
        )

        self.assertEqual(len(result.entries), 1)
        token = result.entries[0]["placeholder"]
        joined = "\n".join(message["content"] for message in result.payload["messages"])
        self.assertEqual(joined.count(token), 2)

    def test_unshield_chat_response_restores_string_and_array_content(self):
        token = "__MIO_EMAIL_1_AAAA111111__"
        entries = [{"placeholder": token, "original": "alice@example.com", "type": "EMAIL"}]
        payload = {
            "choices": [
                {
                    "message": {"content": f"Primary {token}"},
                },
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": f"Secondary {token}"},
                            {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                        ]
                    }
                },
            ]
        }

        restored, count = prompt_gateway._unshield_chat_response(payload, entries)
        self.assertEqual(count, 2)
        self.assertEqual(restored["choices"][0]["message"]["content"], "Primary alice@example.com")
        self.assertEqual(
            restored["choices"][1]["message"]["content"][0]["text"],
            "Secondary alice@example.com",
        )

    def test_unshield_chat_response_rejects_invalid_choices_type(self):
        with self.assertRaises(ValueError):
            prompt_gateway._unshield_chat_response(
                {"choices": "bad"},
                [{"placeholder": "__MIO_X_1_AAAAA00000__", "original": "x", "type": "X"}],
            )

    def test_build_upstream_headers_prefers_request_authorization(self):
        headers = prompt_gateway._build_upstream_headers(
            {"Authorization": "Bearer client-token"},
            upstream_api_key_env="MODEIO_GATEWAY_UPSTREAM_API_KEY",
        )
        self.assertEqual(headers["Authorization"], "Bearer client-token")

    def test_build_upstream_headers_uses_env_fallback(self):
        with patch.dict(os.environ, {"MODEIO_GATEWAY_UPSTREAM_API_KEY": "env-token"}, clear=False):
            headers = prompt_gateway._build_upstream_headers(
                {},
                upstream_api_key_env="MODEIO_GATEWAY_UPSTREAM_API_KEY",
            )
        self.assertEqual(headers["Authorization"], "Bearer env-token")

    def test_persist_map_if_available_saves_map(self):
        result = prompt_gateway.ShieldResult(
            payload={"model": "gpt-test", "messages": []},
            entries=[
                {
                    "placeholder": "__MIO_EMAIL_1_AAAA111111__",
                    "original": "alice@example.com",
                    "type": "EMAIL",
                }
            ],
            redaction_count=1,
            raw_segments=["Email alice@example.com"],
            shielded_segments=["Email __MIO_EMAIL_1_AAAA111111__"],
        )

        with tempfile.TemporaryDirectory() as map_dir:
            with patch.dict(os.environ, {"MODEIO_REDACT_MAP_DIR": map_dir}, clear=False):
                map_ref = prompt_gateway._persist_map_if_available(result)
            self.assertIsNotNone(map_ref)
            self.assertTrue((Path(map_ref["mapPath"]).exists()))
            self.assertTrue(re.match(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$", map_ref["mapId"]))


if __name__ == "__main__":
    unittest.main()
