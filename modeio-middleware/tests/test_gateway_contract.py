#!/usr/bin/env python3

import json
import sys
import threading
import types
import urllib.error
import urllib.request
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import middleware_gateway as gateway  # noqa: E402

from modeio_middleware.plugins.base import MiddlewarePlugin  # noqa: E402


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


class _UpstreamStub:
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


class _GatewayStub:
    def __init__(self, upstream_url, *, plugins=None, profiles=None):
        self._server = None
        self._thread = None
        self.base_url = ""
        self.config = gateway.GatewayRuntimeConfig(
            upstream_url=upstream_url,
            upstream_timeout_seconds=5,
            upstream_api_key_env="MODEIO_GATEWAY_UPSTREAM_API_KEY",
            default_profile="dev",
            profiles=profiles
            or {
                "dev": {
                    "on_plugin_error": "warn",
                    "plugins": ["guardrail", "redact"],
                }
            },
            plugins=plugins
            or {
                "guardrail": {
                    "enabled": False,
                    "module": "modeio_middleware.plugins.guardrail",
                },
                "redact": {
                    "enabled": False,
                    "module": "modeio_middleware.plugins.redact",
                },
            },
        )

    def start(self):
        self._server = gateway.create_server("127.0.0.1", 0, self.config)
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


class _BlockerPlugin(MiddlewarePlugin):
    name = "blocker"

    def pre_request(self, _hook_input):
        return {"action": "block", "message": "blocked by blocker plugin"}


def _register_blocker_plugin_module(module_name: str):
    module = types.ModuleType(module_name)
    module.Plugin = _BlockerPlugin
    sys.modules[module_name] = module


class TestGatewayContract(unittest.TestCase):
    def _start_pair(self, response_factory, *, status=200, plugins=None, profiles=None):
        upstream = _UpstreamStub(response_factory=response_factory, status=status)
        upstream.start()
        gateway_stub = _GatewayStub(
            upstream_url=f"{upstream.base_url}/v1/chat/completions",
            plugins=plugins,
            profiles=profiles,
        )
        gateway_stub.start()
        return upstream, gateway_stub

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

    def test_healthz_reports_ready(self):
        upstream, gateway_stub = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, _headers, payload = self._http_get_json(f"{gateway_stub.base_url}/healthz")
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["service"], "modeio-middleware")
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_rejects_stream_true(self):
        upstream, gateway_stub = self._start_pair(lambda _payload: _completion_payload("ok"))
        try:
            status, headers, payload = self._post_gateway(
                gateway_stub.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_UNSUPPORTED_STREAMING")
            self.assertEqual(headers["x-modeio-upstream-called"], "false")
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_modeio_metadata_not_forwarded_to_upstream(self):
        upstream, gateway_stub = self._start_pair(lambda payload: _completion_payload(payload["messages"][0]["content"]))
        try:
            status, _headers, _payload = self._post_gateway(
                gateway_stub.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(status, 200)
            upstream_payload = upstream.requests[-1]["body"]
            self.assertNotIn("modeio", upstream_payload)
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_redact_plugin_shields_and_restores(self):
        plugins = {
            "guardrail": {
                "enabled": False,
                "module": "modeio_middleware.plugins.guardrail",
            },
            "redact": {
                "enabled": True,
                "module": "modeio_middleware.plugins.redact",
            },
        }
        profiles = {
            "dev": {
                "on_plugin_error": "warn",
                "plugins": ["redact"],
            }
        }

        def echo_user_content(payload):
            content = payload["messages"][0]["content"]
            return _completion_payload(f"Echo: {content}")

        upstream, gateway_stub = self._start_pair(echo_user_content, plugins=plugins, profiles=profiles)
        try:
            status, headers, payload = self._post_gateway(
                gateway_stub.base_url,
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
            self.assertNotIn("alice@example.com", json.dumps(upstream_payload))
            self.assertIn("__MIO_EMAIL_", json.dumps(upstream_payload))

            content = payload["choices"][0]["message"]["content"]
            self.assertIn("alice@example.com", content)
            self.assertIn("redact:modify", headers["x-modeio-pre-actions"])
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_blocking_plugin_blocks_before_upstream_call(self):
        module_name = "modeio_middleware.tests.plugins.blocker"
        _register_blocker_plugin_module(module_name)

        plugins = {
            "blocker": {
                "enabled": True,
                "module": module_name,
            }
        }
        profiles = {
            "dev": {
                "on_plugin_error": "warn",
                "plugins": ["blocker"],
            }
        }

        upstream, gateway_stub = self._start_pair(
            lambda payload: _completion_payload(payload["messages"][0]["content"]),
            plugins=plugins,
            profiles=profiles,
        )
        try:
            status, headers, payload = self._post_gateway(
                gateway_stub.base_url,
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )
            self.assertEqual(status, 403)
            self.assertEqual(payload["error"]["code"], "MODEIO_PLUGIN_BLOCKED")
            self.assertEqual(headers["x-modeio-upstream-called"], "false")
            self.assertEqual(len(upstream.requests), 0)
        finally:
            gateway_stub.stop()
            upstream.stop()


if __name__ == "__main__":
    unittest.main()
