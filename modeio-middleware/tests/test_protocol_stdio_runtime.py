#!/usr/bin/env python3

import json
import sys
import urllib.error
import urllib.request
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"
HELPERS_DIR = REPO_ROOT / "modeio-middleware" / "tests" / "helpers"
FIXTURES_DIR = REPO_ROOT / "modeio-middleware" / "tests" / "fixtures"

sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(HELPERS_DIR))

from gateway_harness import GatewayStub, UpstreamStub, completion_payload  # noqa: E402


def _post_json(gateway_url: str, path: str, payload: dict):
    request = urllib.request.Request(
        f"{gateway_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            return response.status, response.headers, body
    except urllib.error.HTTPError as error:
        try:
            body = json.loads(error.read().decode("utf-8"))
            return error.code, error.headers, body
        finally:
            error.close()


class TestProtocolStdioRuntime(unittest.TestCase):
    def _start_pair(self, plugins: dict, profiles: dict):
        upstream = UpstreamStub(
            response_factory=lambda _path, payload: completion_payload(payload["messages"][0]["content"])
        )
        upstream.start()
        gateway = GatewayStub(upstream.base_url, plugins=plugins, profiles=profiles)
        gateway.start()
        return upstream, gateway

    def _stdio_plugin_base(self) -> dict:
        return {
            "enabled": True,
            "runtime": "stdio_jsonrpc",
            "manifest": str(FIXTURES_DIR / "stdio_echo_manifest.json"),
            "command": [sys.executable, str(FIXTURES_DIR / "stdio_echo_plugin.py")],
            "behavior": "patch",
        }

    def test_stdio_plugin_observe_mode_is_non_intrusive(self):
        plugins = {
            "external_policy": {
                **self._stdio_plugin_base(),
                "rewrite_to": "rewritten-in-observe",
            }
        }
        profiles = {
            "dev": {
                "on_plugin_error": "warn",
                "plugins": ["external_policy"],
            }
        }

        upstream, gateway = self._start_pair(plugins, profiles)
        try:
            status, headers, payload = _post_json(
                gateway.base_url,
                "/v1/chat/completions",
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "original-text"}],
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(payload["choices"][0]["message"]["content"], "original-text")
            self.assertEqual(upstream.requests[-1]["body"]["messages"][0]["content"], "original-text")
            self.assertIn("external_policy:warn", headers["x-modeio-pre-actions"])
        finally:
            gateway.stop()
            upstream.stop()

    def test_stdio_plugin_enforce_mode_allows_patch_when_granted(self):
        plugins = {
            "external_policy": {
                **self._stdio_plugin_base(),
                "mode": "enforce",
                "capabilities_grant": {
                    "can_patch": True,
                },
                "rewrite_to": "rewritten-in-enforce",
            }
        }
        profiles = {
            "dev": {
                "on_plugin_error": "warn",
                "plugins": ["external_policy"],
            }
        }

        upstream, gateway = self._start_pair(plugins, profiles)
        try:
            status, headers, payload = _post_json(
                gateway.base_url,
                "/v1/chat/completions",
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "original-text"}],
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(payload["choices"][0]["message"]["content"], "rewritten-in-enforce")
            self.assertEqual(upstream.requests[-1]["body"]["messages"][0]["content"], "rewritten-in-enforce")
            self.assertIn("external_policy:modify", headers["x-modeio-pre-actions"])
        finally:
            gateway.stop()
            upstream.stop()

    def test_stdio_plugin_assist_mode_downgrades_block(self):
        plugins = {
            "external_policy": {
                **self._stdio_plugin_base(),
                "behavior": "block",
                "mode": "assist",
                "capabilities_grant": {
                    "can_block": True,
                },
            }
        }
        profiles = {
            "dev": {
                "on_plugin_error": "warn",
                "plugins": ["external_policy"],
            }
        }

        upstream, gateway = self._start_pair(plugins, profiles)
        try:
            status, headers, payload = _post_json(
                gateway.base_url,
                "/v1/chat/completions",
                {
                    "model": "gpt-test",
                    "messages": [{"role": "user", "content": "original-text"}],
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(payload["choices"][0]["message"]["content"], "original-text")
            self.assertEqual(len(upstream.requests), 1)
            self.assertIn("external_policy:warn", headers["x-modeio-pre-actions"])
        finally:
            gateway.stop()
            upstream.stop()


if __name__ == "__main__":
    unittest.main()
