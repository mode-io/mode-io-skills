#!/usr/bin/env python3

import json
import sys
import types
import urllib.error
import urllib.request
import unittest
from pathlib import Path

try:
    from compression import zstd as zstd_codec
except Exception:  # pragma: no cover
    zstd_codec = None

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"
TESTS_DIR = REPO_ROOT / "modeio-middleware" / "tests"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from helpers.gateway_harness import GatewayStub, UpstreamStub, completion_payload, responses_payload  # noqa: E402
from modeio_middleware.plugins.base import MiddlewarePlugin  # noqa: E402


class _BlockerPlugin(MiddlewarePlugin):
    name = "blocker"

    def pre_request(self, _hook_input):
        return {"action": "block", "message": "blocked by blocker plugin"}


def _register_blocker_plugin_module(module_name: str):
    module = types.ModuleType(module_name)
    module.Plugin = _BlockerPlugin
    sys.modules[module_name] = module


class TestGatewayContract(unittest.TestCase):
    def _start_pair(self, response_factory, *, status=200, stream_factory=None, plugins=None, profiles=None):
        upstream = UpstreamStub(response_factory=response_factory, status=status, stream_factory=stream_factory)
        upstream.start()
        gateway_stub = GatewayStub(
            upstream_base_url=upstream.base_url,
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

    def _post_json(self, gateway_url, path, payload, headers=None):
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            f"{gateway_url}{path}",
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

    def _post_raw(self, gateway_url, path, body, headers=None):
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            f"{gateway_url}{path}",
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

    def _post_stream(self, gateway_url, path, payload):
        request = urllib.request.Request(
            f"{gateway_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8", errors="replace")
                return response.status, response.headers, body
        except urllib.error.HTTPError as error:
            try:
                body = error.read().decode("utf-8", errors="replace")
                return error.code, error.headers, body
            finally:
                error.close()

    def test_healthz_reports_ready(self):
        upstream, gateway_stub = self._start_pair(lambda _path, _payload: completion_payload("ok"))
        try:
            status, _headers, payload = self._http_get_json(f"{gateway_stub.base_url}/healthz")
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["service"], "modeio-middleware")
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_chat_modeio_metadata_not_forwarded_to_upstream(self):
        upstream, gateway_stub = self._start_pair(
            lambda _path, payload: completion_payload(payload["messages"][0]["content"])
        )
        try:
            status, _headers, _payload = self._post_json(
                gateway_stub.base_url,
                "/v1/chat/completions",
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

    def test_responses_modeio_metadata_not_forwarded_to_upstream(self):
        upstream, gateway_stub = self._start_pair(
            lambda _path, payload: responses_payload(str(payload.get("input", "")))
        )
        try:
            status, _headers, payload = self._post_json(
                gateway_stub.base_url,
                "/v1/responses",
                {
                    "model": "gpt-test",
                    "input": "hello from responses",
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(status, 200)
            self.assertIn("output_text", payload)
            upstream_payload = upstream.requests[-1]["body"]
            self.assertNotIn("modeio", upstream_payload)
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_invalid_modeio_plugin_preset_returns_validation_error(self):
        upstream, gateway_stub = self._start_pair(
            lambda _path, payload: completion_payload(payload["messages"][0]["content"])
        )
        try:
            status, _headers, payload = self._post_json(
                gateway_stub.base_url,
                "/v1/chat/completions",
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "modeio": {
                        "plugins": {
                            "custom_policy": {
                                "preset": True,
                            }
                        }
                    },
                },
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_VALIDATION_ERROR")
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_invalid_modeio_plugin_mode_returns_validation_error(self):
        upstream, gateway_stub = self._start_pair(
            lambda _path, payload: completion_payload(payload["messages"][0]["content"])
        )
        try:
            status, _headers, payload = self._post_json(
                gateway_stub.base_url,
                "/v1/chat/completions",
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "modeio": {
                        "plugins": {
                            "custom_policy": {
                                "mode": True,
                            }
                        }
                    },
                },
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_VALIDATION_ERROR")
        finally:
            gateway_stub.stop()
            upstream.stop()

    @unittest.skipIf(zstd_codec is None, "compression.zstd unavailable")
    def test_responses_accepts_zstd_encoded_request_body(self):
        upstream, gateway_stub = self._start_pair(
            lambda _path, payload: responses_payload(str(payload.get("input", "")))
        )
        try:
            raw_payload = json.dumps(
                {
                    "model": "gpt-test",
                    "input": "hello zstd",
                    "modeio": {"profile": "dev"},
                }
            ).encode("utf-8")
            encoded = zstd_codec.compress(raw_payload)

            status, _headers, payload = self._post_raw(
                gateway_stub.base_url,
                "/v1/responses",
                encoded,
                headers={"Content-Encoding": "zstd"},
            )
            self.assertEqual(status, 200)
            self.assertIn("output_text", payload)
            self.assertEqual(upstream.requests[-1]["body"]["input"], "hello zstd")
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_rejects_unknown_content_encoding(self):
        upstream, gateway_stub = self._start_pair(
            lambda _path, payload: responses_payload(str(payload.get("input", "")))
        )
        try:
            raw_payload = json.dumps(
                {
                    "model": "gpt-test",
                    "input": "hello",
                }
            ).encode("utf-8")
            status, _headers, payload = self._post_raw(
                gateway_stub.base_url,
                "/v1/responses",
                raw_payload,
                headers={"Content-Encoding": "snappy"},
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_VALIDATION_ERROR")
            self.assertIn("unsupported Content-Encoding", payload["error"]["message"])
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_chat_stream_is_passed_through(self):
        def stream_factory(_path, payload):
            content = payload["messages"][0]["content"]
            return [
                {"choices": [{"delta": {"content": f"Echo: {content}"}}]},
                "[DONE]",
            ]

        upstream, gateway_stub = self._start_pair(
            lambda _path, _payload: completion_payload("unused"),
            stream_factory=stream_factory,
        )
        try:
            status, headers, body = self._post_stream(
                gateway_stub.base_url,
                "/v1/chat/completions",
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello stream"}],
                    "stream": True,
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(headers["x-modeio-upstream-called"], "true")
            self.assertEqual(headers["x-modeio-streaming"], "true")
            self.assertIn("Echo: hello stream", body)
            self.assertIn("[DONE]", body)
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_responses_stream_is_passed_through(self):
        def stream_factory(_path, _payload):
            return [
                {"type": "response.output_text.delta", "delta": "hello"},
                {"type": "response.completed"},
                "[DONE]",
            ]

        upstream, gateway_stub = self._start_pair(
            lambda _path, _payload: responses_payload("unused"),
            stream_factory=stream_factory,
        )
        try:
            status, headers, body = self._post_stream(
                gateway_stub.base_url,
                "/v1/responses",
                {
                    "model": "gpt-test",
                    "input": "hello response stream",
                    "stream": True,
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(headers["x-modeio-streaming"], "true")
            self.assertIn("response.output_text.delta", body)
            self.assertIn("[DONE]", body)
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_redact_plugin_shields_and_restores_non_stream_chat(self):
        plugins = {
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

        def echo_user_content(_path, payload):
            content = payload["messages"][0]["content"]
            return completion_payload(f"Echo: {content}")

        upstream, gateway_stub = self._start_pair(echo_user_content, plugins=plugins, profiles=profiles)
        try:
            status, headers, payload = self._post_json(
                gateway_stub.base_url,
                "/v1/chat/completions",
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

    def test_redact_plugin_restores_streamed_chat_content(self):
        plugins = {
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

        def stream_factory(_path, payload):
            content = payload["messages"][0]["content"]
            return [
                {"choices": [{"delta": {"content": f"Echo: {content}"}}]},
                "[DONE]",
            ]

        upstream, gateway_stub = self._start_pair(
            lambda _path, _payload: completion_payload("unused"),
            stream_factory=stream_factory,
            plugins=plugins,
            profiles=profiles,
        )
        try:
            status, _headers, body = self._post_stream(
                gateway_stub.base_url,
                "/v1/chat/completions",
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "email alice@example.com"}],
                    "stream": True,
                },
            )
            self.assertEqual(status, 200)
            self.assertNotIn("__MIO_EMAIL_", body)
            self.assertIn("alice@example.com", body)
            self.assertNotIn("alice@example.com", json.dumps(upstream.requests[-1]["body"]))
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
            lambda _path, payload: completion_payload(payload["messages"][0]["content"]),
            plugins=plugins,
            profiles=profiles,
        )
        try:
            status, headers, payload = self._post_json(
                gateway_stub.base_url,
                "/v1/chat/completions",
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

    def test_profile_plugin_override_can_enable_plugin(self):
        module_name = "modeio_middleware.tests.plugins.blocker_profile_enabled"
        _register_blocker_plugin_module(module_name)

        plugins = {
            "blocker": {
                "enabled": False,
                "module": module_name,
            }
        }
        profiles = {
            "profile_with_override": {
                "on_plugin_error": "warn",
                "plugins": ["blocker"],
                "plugin_overrides": {
                    "blocker": {
                        "enabled": True,
                    }
                },
            }
        }

        upstream, gateway_stub = self._start_pair(
            lambda _path, payload: completion_payload(payload["messages"][0]["content"]),
            plugins=plugins,
            profiles=profiles,
        )
        try:
            status, _headers, payload = self._post_json(
                gateway_stub.base_url,
                "/v1/chat/completions",
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "modeio": {
                        "profile": "profile_with_override",
                    },
                },
            )
            self.assertEqual(status, 403)
            self.assertEqual(payload["error"]["code"], "MODEIO_PLUGIN_BLOCKED")
            self.assertEqual(len(upstream.requests), 0)
        finally:
            gateway_stub.stop()
            upstream.stop()

    def test_request_plugin_override_wins_over_profile_plugin_override(self):
        module_name = "modeio_middleware.tests.plugins.blocker_profile_override"
        _register_blocker_plugin_module(module_name)

        plugins = {
            "blocker": {
                "enabled": False,
                "module": module_name,
            }
        }
        profiles = {
            "profile_with_override": {
                "on_plugin_error": "warn",
                "plugins": ["blocker"],
                "plugin_overrides": {
                    "blocker": {
                        "enabled": True,
                    }
                },
            }
        }

        upstream, gateway_stub = self._start_pair(
            lambda _path, payload: completion_payload(payload["messages"][0]["content"]),
            plugins=plugins,
            profiles=profiles,
        )
        try:
            status, _headers, _payload = self._post_json(
                gateway_stub.base_url,
                "/v1/chat/completions",
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "hello"}],
                    "modeio": {
                        "profile": "profile_with_override",
                        "plugins": {
                            "blocker": {
                                "enabled": False,
                            }
                        },
                    },
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(len(upstream.requests), 1)
        finally:
            gateway_stub.stop()
            upstream.stop()


if __name__ == "__main__":
    unittest.main()
