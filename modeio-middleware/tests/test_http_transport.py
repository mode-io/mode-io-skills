#!/usr/bin/env python3

import json
import sys
import unittest
from pathlib import Path

from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.core.engine import GatewayRuntimeConfig  # noqa: E402
from modeio_middleware.http_transport import create_app  # noqa: E402


class TestHttpTransport(unittest.TestCase):
    def setUp(self):
        config = GatewayRuntimeConfig(
            upstream_chat_completions_url="https://upstream.example/v1/chat/completions",
            upstream_responses_url="https://upstream.example/v1/responses",
            upstream_timeout_seconds=5,
            upstream_api_key_env="MODEIO_TEST_UPSTREAM_KEY",
            plugins={},
            profiles={"dev": {"on_plugin_error": "warn", "plugins": []}},
        )
        self.client = TestClient(create_app(config))

    def tearDown(self):
        self.client.close()

    def _assert_contract_headers(self, response):
        self.assertIn("x-modeio-contract-version", response.headers)
        self.assertIn("x-modeio-request-id", response.headers)
        self.assertEqual(response.headers["x-modeio-upstream-called"], "false")

    def test_empty_body_returns_contract_validation_error(self):
        response = self.client.post("/v1/chat/completions", content=b"")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "MODEIO_VALIDATION_ERROR")
        self._assert_contract_headers(response)

    def test_malformed_json_returns_contract_validation_error(self):
        response = self.client.post(
            "/v1/chat/completions",
            content=b"{bad",
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "MODEIO_VALIDATION_ERROR")
        self._assert_contract_headers(response)

    def test_non_object_json_returns_contract_validation_error(self):
        response = self.client.post(
            "/v1/chat/completions",
            content=json.dumps(["not", "an", "object"]).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "MODEIO_VALIDATION_ERROR")
        self._assert_contract_headers(response)


if __name__ == "__main__":
    unittest.main()
