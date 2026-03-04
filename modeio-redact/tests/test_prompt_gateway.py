#!/usr/bin/env python3

import json
import os
import threading
import urllib.error
import urllib.request
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-redact" / "scripts"

import sys

sys.path.insert(0, str(SCRIPTS_DIR))

import prompt_gateway  # noqa: E402


def _completion_payload(content):
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
    }


class UpstreamStub:
    def __init__(self, response_factory, status=200):
        self.response_factory = response_factory
        self.status = status
        self.requests = []
        self._server = None
        self._thread = None
        self.base_url = ""

    def start(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                content_length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode("utf-8")) if body else {}
                owner.requests.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers.items()),
                        "body": payload,
                    }
                )
                response_payload = owner.response_factory(payload)
                response_body = json.dumps(response_payload).encode("utf-8")

                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, _format, *_args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self._server.server_address
        self.base_url = f"http://{host}:{port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class GatewayStub:
    def __init__(self, upstream_url):
        self._server = None
        self._thread = None
        self.base_url = ""
        self.config = prompt_gateway.GatewayConfig(
            upstream_url=upstream_url,
            upstream_timeout_seconds=5,
            upstream_api_key_env="MODEIO_GATEWAY_UPSTREAM_API_KEY",
        )

    def start(self):
        self._server = prompt_gateway.create_server("127.0.0.1", 0, self.config)
        host, port = self._server.server_address
        self.base_url = f"http://{host}:{port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class TestPromptGateway(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._maps_temp_dir = TemporaryDirectory()
        cls._maps_env_patcher = patch.dict(
            os.environ,
            {"MODEIO_REDACT_MAP_DIR": cls._maps_temp_dir.name},
            clear=False,
        )
        cls._maps_env_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._maps_env_patcher.stop()
        cls._maps_temp_dir.cleanup()

    def _start_pair(self, response_factory, status=200):
        upstream = UpstreamStub(response_factory=response_factory, status=status)
        upstream.start()
        gateway = GatewayStub(upstream_url=f"{upstream.base_url}/v1/chat/completions")
        gateway.start()
        return upstream, gateway

    def _http_get_json(self, url):
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, response.headers, body

    def _post_gateway(self, gateway_url, payload, headers=None):
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            f"{gateway_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
                return response.status, response.headers, body
        except urllib.error.HTTPError as error:
            try:
                body = json.loads(error.read().decode("utf-8"))
                return error.code, error.headers, body
            finally:
                error.close()

    def _post_raw(self, url, body: bytes, headers=None):
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return response.status, response.headers, payload
        except urllib.error.HTTPError as error:
            try:
                payload = json.loads(error.read().decode("utf-8"))
                return error.code, error.headers, payload
            finally:
                error.close()

    def test_healthz_reports_ready(self):
        upstream, gateway = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, _headers, payload = self._http_get_json(f"{gateway.base_url}/healthz")
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["service"], "modeio-redact-prompt-gateway")
        finally:
            gateway.stop()
            upstream.stop()

    def test_rejects_stream_true(self):
        upstream, gateway = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_STREAM_UNSUPPORTED")
            self.assertEqual(headers["x-modeio-upstream-called"], "false")
        finally:
            gateway.stop()
            upstream.stop()

    def test_shields_before_upstream_and_restores_response(self):
        def echo_user_content(payload):
            content = payload["messages"][0]["content"]
            return _completion_payload(f"Echo: {content}")

        upstream, gateway = self._start_pair(echo_user_content)
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [
                        {
                            "role": "user",
                            "content": "Please email alice@example.com about account reset.",
                        }
                    ],
                },
            )
            self.assertEqual(status, 200)
            upstream_payload = upstream.requests[-1]["body"]
            dumped_upstream = json.dumps(upstream_payload)
            self.assertNotIn("alice@example.com", dumped_upstream)
            self.assertIn("__MIO_EMAIL_", dumped_upstream)

            content = payload["choices"][0]["message"]["content"]
            self.assertIn("alice@example.com", content)
            self.assertEqual(headers["x-modeio-shielded"], "true")
            self.assertEqual(headers["x-modeio-upstream-called"], "true")
            self.assertEqual(headers["x-modeio-degraded"], "none")
            self.assertGreater(int(headers["x-modeio-redaction-count"]), 0)
        finally:
            gateway.stop()
            upstream.stop()

    def test_modeio_field_not_forwarded_to_upstream(self):
        upstream, gateway = self._start_pair(lambda payload: _completion_payload(payload["messages"][0]["content"]))
        try:
            status, _headers, _payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "Email: alice@example.com"}],
                    "modeio": {
                        "policy": "strict",
                        "allow_degraded_unshield": True,
                    },
                },
            )
            self.assertEqual(status, 200)
            upstream_payload = upstream.requests[-1]["body"]
            self.assertNotIn("modeio", upstream_payload)
        finally:
            gateway.stop()
            upstream.stop()

    def test_forwards_client_authorization_header(self):
        upstream, gateway = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, _headers, _payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                headers={"Authorization": "Bearer client-token"},
            )
            self.assertEqual(status, 200)
            upstream_headers = upstream.requests[-1]["headers"]
            self.assertEqual(upstream_headers.get("Authorization"), "Bearer client-token")
        finally:
            gateway.stop()
            upstream.stop()

    def test_uses_env_api_key_when_client_header_missing(self):
        upstream, gateway = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            with patch.dict(os.environ, {"MODEIO_GATEWAY_UPSTREAM_API_KEY": "env-token"}, clear=False):
                response = self._post_gateway(
                    gateway.base_url,
                    {
                        "model": "gpt-test",
                        "messages": [{"role": "user", "content": "hello"}],
                    },
                )
            status, _headers, _payload = response
            self.assertEqual(status, 200)
            upstream_headers = upstream.requests[-1]["headers"]
            self.assertEqual(upstream_headers.get("Authorization"), "Bearer env-token")
        finally:
            gateway.stop()
            upstream.stop()

    def test_returns_degraded_response_when_unshield_fails(self):
        def bad_response(_payload):
            return _completion_payload(123)

        upstream, gateway = self._start_pair(bad_response)
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "Email: alice@example.com"}],
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(headers["x-modeio-degraded"], "unshield_failed")
            self.assertEqual(payload["choices"][0]["message"]["content"], 123)
        finally:
            gateway.stop()
            upstream.stop()

    def test_rejects_invalid_message_content_shape(self):
        upstream, gateway = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": {"text": "hello"}}],
                },
            )
            self.assertEqual(status, 422)
            self.assertEqual(payload["error"]["code"], "MODEIO_UNSUPPORTED_MESSAGE_CONTENT")
            self.assertEqual(headers["x-modeio-upstream-called"], "false")
        finally:
            gateway.stop()
            upstream.stop()

    def test_persists_map_file_when_redaction_occurs(self):
        upstream, gateway = self._start_pair(lambda payload: _completion_payload(payload["messages"][0]["content"]))
        try:
            with TemporaryDirectory() as map_dir:
                with patch.dict(os.environ, {"MODEIO_REDACT_MAP_DIR": map_dir}, clear=False):
                    status, headers, _payload = self._post_gateway(
                        gateway.base_url,
                        {
                            "model": "gpt-test",
                            "messages": [{"role": "user", "content": "Email: alice@example.com"}],
                        },
                    )
                self.assertEqual(status, 200)
                maps = list(Path(map_dir).glob("*.json"))
                self.assertGreaterEqual(len(maps), 1)
                self.assertIn("x-modeio-map-id", headers)
        finally:
            gateway.stop()
            upstream.stop()

    def test_harmless_prompt_keeps_shielded_false(self):
        upstream, gateway = self._start_pair(lambda payload: _completion_payload(payload["messages"][0]["content"]))
        try:
            status, headers, _payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "Summarize this harmless sentence."}],
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(headers["x-modeio-shielded"], "false")
            self.assertEqual(headers["x-modeio-redaction-count"], "0")
            self.assertEqual(headers["x-modeio-degraded"], "none")
        finally:
            gateway.stop()
            upstream.stop()

    def test_rejects_invalid_modeio_payload_type(self):
        upstream, gateway = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "modeio": "strict",
                },
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_VALIDATION_ERROR")
            self.assertEqual(headers["x-modeio-upstream-called"], "false")
        finally:
            gateway.stop()
            upstream.stop()

    def test_rejects_unsupported_modeio_policy(self):
        upstream, gateway = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "modeio": {"policy": "relaxed"},
                },
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_POLICY_UNSUPPORTED")
            self.assertEqual(headers["x-modeio-upstream-called"], "false")
        finally:
            gateway.stop()
            upstream.stop()

    def test_rejects_invalid_allow_degraded_type(self):
        upstream, gateway = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "modeio": {"policy": "strict", "allow_degraded_unshield": "yes"},
                },
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_VALIDATION_ERROR")
            self.assertEqual(headers["x-modeio-upstream-called"], "false")
        finally:
            gateway.stop()
            upstream.stop()

    def test_returns_gateway_error_on_upstream_5xx(self):
        upstream, gateway = self._start_pair(lambda _payload: {"error": "boom"}, status=500)
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            self.assertEqual(status, 502)
            self.assertEqual(payload["error"]["code"], "MODEIO_UPSTREAM_ERROR")
            self.assertTrue(payload["error"]["retryable"])
            self.assertEqual(headers["x-modeio-upstream-called"], "true")
        finally:
            gateway.stop()
            upstream.stop()

    def test_returns_upstream_4xx_status_and_marks_not_retryable(self):
        upstream, gateway = self._start_pair(lambda _payload: {"error": "unauthorized"}, status=401)
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            self.assertEqual(status, 401)
            self.assertEqual(payload["error"]["code"], "MODEIO_UPSTREAM_ERROR")
            self.assertFalse(payload["error"]["retryable"])
            self.assertEqual(headers["x-modeio-upstream-called"], "true")
        finally:
            gateway.stop()
            upstream.stop()

    def test_returns_gateway_error_on_upstream_invalid_json_root(self):
        upstream, gateway = self._start_pair(lambda _payload: "not-an-object")
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            self.assertEqual(status, 502)
            self.assertEqual(payload["error"]["code"], "MODEIO_UPSTREAM_INVALID_JSON")
            self.assertFalse(payload["error"]["retryable"])
            self.assertEqual(headers["x-modeio-upstream-called"], "true")
        finally:
            gateway.stop()
            upstream.stop()

    def test_rejects_invalid_json_body(self):
        upstream, gateway = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, headers, payload = self._post_raw(
                f"{gateway.base_url}/v1/chat/completions",
                body=b"{invalid-json",
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_VALIDATION_ERROR")
            self.assertEqual(headers["x-modeio-upstream-called"], "false")
        finally:
            gateway.stop()
            upstream.stop()

    def test_rejects_when_unshield_fails_and_degraded_disabled(self):
        def bad_response(_payload):
            return _completion_payload(123)

        upstream, gateway = self._start_pair(bad_response)
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "Email: alice@example.com"}],
                    "modeio": {"policy": "strict", "allow_degraded_unshield": False},
                },
            )
            self.assertEqual(status, 502)
            self.assertEqual(payload["error"]["code"], "MODEIO_UNSHIELD_FAILED")
            self.assertEqual(headers["x-modeio-upstream-called"], "true")
            self.assertEqual(headers["x-modeio-degraded"], "none")
        finally:
            gateway.stop()
            upstream.stop()

    def test_supports_array_text_content_payloads(self):
        def echo_back(payload):
            content = payload["messages"][0]["content"]
            return _completion_payload(content)

        upstream, gateway = self._start_pair(echo_back)
        try:
            status, headers, payload = self._post_gateway(
                gateway.base_url,
                {
                    "model": "gpt-test",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Email alice@example.com"},
                                {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
                            ],
                        }
                    ],
                },
            )
            self.assertEqual(status, 200)
            upstream_payload = upstream.requests[-1]["body"]
            text_part = upstream_payload["messages"][0]["content"][0]["text"]
            self.assertIn("__MIO_EMAIL_", text_part)
            self.assertNotIn("alice@example.com", text_part)

            restored_part = payload["choices"][0]["message"]["content"][0]["text"]
            self.assertIn("alice@example.com", restored_part)
            self.assertEqual(headers["x-modeio-shielded"], "true")
        finally:
            gateway.stop()
            upstream.stop()


if __name__ == "__main__":
    unittest.main()
