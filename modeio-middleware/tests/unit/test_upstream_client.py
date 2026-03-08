#!/usr/bin/env python3

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.core.engine import GatewayRuntimeConfig  # noqa: E402
from modeio_middleware.core.errors import MiddlewareError  # noqa: E402
from modeio_middleware.core.upstream_client import forward_upstream_json  # noqa: E402


class _FakeResponse:
    def __init__(self, *, status_code: int, payload=None, headers=None, json_error: Exception | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _FakeClient:
    def __init__(self, behavior):
        self._behavior = behavior
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, *, headers, json):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if isinstance(self._behavior, Exception):
            raise self._behavior
        return self._behavior


class _ClientFactory:
    def __init__(self, *behaviors):
        self._behaviors = list(behaviors)
        self.instances = []

    def __call__(self, *args, **kwargs):
        del args, kwargs
        behavior = self._behaviors.pop(0)
        client = _FakeClient(behavior)
        self.instances.append(client)
        return client


class TestUpstreamClient(unittest.TestCase):
    def setUp(self):
        self.config = GatewayRuntimeConfig(
            upstream_chat_completions_url="https://upstream.example/v1/chat/completions",
            upstream_responses_url="https://upstream.example/v1/responses",
            upstream_timeout_seconds=5,
            upstream_api_key_env="MODEIO_TEST_UPSTREAM_KEY",
        )

    def test_forward_upstream_json_prefers_incoming_authorization_header(self):
        factory = _ClientFactory(_FakeResponse(status_code=200, payload={"ok": True}))
        with patch("modeio_middleware.core.upstream_client.httpx.Client", side_effect=factory):
            with patch.dict(os.environ, {"MODEIO_TEST_UPSTREAM_KEY": "fallback-secret"}, clear=False):
                payload = forward_upstream_json(
                    config=self.config,
                    endpoint_kind="chat_completions",
                    payload={"model": "gpt-test"},
                    incoming_headers={"Authorization": "Bearer incoming-secret"},
                )

        self.assertEqual(payload, {"ok": True})
        sent_headers = factory.instances[0].calls[0]["headers"]
        self.assertEqual(sent_headers["Authorization"], "Bearer incoming-secret")

    def test_forward_upstream_json_retries_retryable_status_then_succeeds(self):
        factory = _ClientFactory(
            _FakeResponse(status_code=503, payload={"error": "busy"}),
            _FakeResponse(status_code=200, payload={"ok": True}),
        )
        with patch("modeio_middleware.core.upstream_client.httpx.Client", side_effect=factory):
            with patch("modeio_middleware.core.upstream_client.time.sleep") as sleep_mock:
                payload = forward_upstream_json(
                    config=self.config,
                    endpoint_kind="chat_completions",
                    payload={"model": "gpt-test"},
                    incoming_headers={},
                )

        self.assertEqual(payload, {"ok": True})
        self.assertEqual(len(factory.instances), 2)
        sleep_mock.assert_called_once()

    def test_forward_upstream_json_rejects_non_object_json(self):
        factory = _ClientFactory(_FakeResponse(status_code=200, payload=["not", "an", "object"]))
        with patch("modeio_middleware.core.upstream_client.httpx.Client", side_effect=factory):
            with self.assertRaises(MiddlewareError) as error_ctx:
                forward_upstream_json(
                    config=self.config,
                    endpoint_kind="chat_completions",
                    payload={"model": "gpt-test"},
                    incoming_headers={},
                )

        self.assertEqual(error_ctx.exception.code, "MODEIO_UPSTREAM_INVALID_JSON")

    def test_forward_upstream_json_retries_timeout_exception_then_raises(self):
        timeout_error = httpx.ReadTimeout("timed out")
        factory = _ClientFactory(timeout_error, timeout_error, timeout_error)
        with patch("modeio_middleware.core.upstream_client.httpx.Client", side_effect=factory):
            with patch("modeio_middleware.core.upstream_client.time.sleep") as sleep_mock:
                with self.assertRaises(MiddlewareError) as error_ctx:
                    forward_upstream_json(
                        config=self.config,
                        endpoint_kind="chat_completions",
                        payload={"model": "gpt-test"},
                        incoming_headers={},
                    )

        self.assertEqual(error_ctx.exception.code, "MODEIO_UPSTREAM_TIMEOUT")
        self.assertEqual(sleep_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
