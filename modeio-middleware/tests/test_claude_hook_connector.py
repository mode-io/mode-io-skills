#!/usr/bin/env python3

import json
import sys
import types
import urllib.error
import urllib.request
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"
TESTS_DIR = REPO_ROOT / "modeio-middleware" / "tests"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from helpers.gateway_harness import GatewayStub, UpstreamStub, completion_payload  # noqa: E402
from modeio_middleware.plugins.base import MiddlewarePlugin  # noqa: E402


class _ClaudeBlockPlugin(MiddlewarePlugin):
    name = "claude_block"

    def pre_request(self, hook_input):
        if hook_input.get("endpoint_kind") == "claude_user_prompt":
            return {"action": "block", "message": "blocked by test pre hook"}
        return {"action": "allow"}

    def post_response(self, hook_input):
        if hook_input.get("endpoint_kind") == "claude_stop":
            return {"action": "block", "message": "blocked by test stop hook"}
        return {"action": "allow"}


class _ClaudeWarnPlugin(MiddlewarePlugin):
    name = "claude_warn"

    def pre_request(self, _hook_input):
        return {
            "action": "warn",
            "findings": [
                {
                    "class": "policy_warning",
                    "severity": "low",
                    "confidence": 1.0,
                    "reason": "review prompt before submission",
                    "evidence": ["test"],
                }
            ],
        }


def _register_plugin(module_name: str, plugin_cls):
    module = types.ModuleType(module_name)
    module.Plugin = plugin_cls
    sys.modules[module_name] = module


def _post_json(gateway_url: str, path: str, payload: dict):
    request = urllib.request.Request(
        f"{gateway_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
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


class TestClaudeHookConnector(unittest.TestCase):
    def _start_pair(self, *, plugins, profiles):
        upstream = UpstreamStub(
            response_factory=lambda _path, payload: completion_payload(payload.get("messages", [{}])[0].get("content", ""))
        )
        upstream.start()
        gateway = GatewayStub(
            upstream_base_url=upstream.base_url,
            plugins=plugins,
            profiles=profiles,
        )
        gateway.start()
        return upstream, gateway

    def test_user_prompt_block_returns_claude_block_decision(self):
        module_name = "modeio_middleware.tests.plugins.claude_block"
        _register_plugin(module_name, _ClaudeBlockPlugin)

        upstream, gateway = self._start_pair(
            plugins={
                "claude_block": {
                    "enabled": True,
                    "module": module_name,
                }
            },
            profiles={
                "dev": {
                    "on_plugin_error": "warn",
                    "plugins": ["claude_block"],
                }
            },
        )
        try:
            status, headers, payload = _post_json(
                gateway.base_url,
                "/connectors/claude/hooks",
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "test prompt",
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(payload.get("decision"), "block")
            self.assertIn("blocked by test pre hook", payload.get("reason", ""))
            self.assertEqual(headers["x-modeio-upstream-called"], "false")
            self.assertIn("claude_block:block", headers["x-modeio-pre-actions"])
            self.assertEqual(len(upstream.requests), 0)
        finally:
            gateway.stop()
            upstream.stop()

    def test_stop_block_returns_claude_block_decision(self):
        module_name = "modeio_middleware.tests.plugins.claude_stop_block"
        _register_plugin(module_name, _ClaudeBlockPlugin)

        upstream, gateway = self._start_pair(
            plugins={
                "claude_block": {
                    "enabled": True,
                    "module": module_name,
                }
            },
            profiles={
                "dev": {
                    "on_plugin_error": "warn",
                    "plugins": ["claude_block"],
                }
            },
        )
        try:
            status, headers, payload = _post_json(
                gateway.base_url,
                "/connectors/claude/hooks",
                {
                    "hook_event_name": "Stop",
                    "status": "completed",
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(payload.get("decision"), "block")
            self.assertIn("blocked by test stop hook", payload.get("reason", ""))
            self.assertIn("claude_block:block", headers["x-modeio-post-actions"])
            self.assertEqual(len(upstream.requests), 0)
        finally:
            gateway.stop()
            upstream.stop()

    def test_user_prompt_warn_returns_system_message(self):
        module_name = "modeio_middleware.tests.plugins.claude_warn"
        _register_plugin(module_name, _ClaudeWarnPlugin)

        upstream, gateway = self._start_pair(
            plugins={
                "claude_warn": {
                    "enabled": True,
                    "module": module_name,
                }
            },
            profiles={
                "dev": {
                    "on_plugin_error": "warn",
                    "plugins": ["claude_warn"],
                }
            },
        )
        try:
            status, headers, payload = _post_json(
                gateway.base_url,
                "/connectors/claude/hooks",
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "test prompt",
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(status, 200)
            self.assertIn("modeio policy findings", payload.get("systemMessage", ""))
            hook_output = payload.get("hookSpecificOutput", {})
            self.assertEqual(hook_output.get("hookEventName"), "UserPromptSubmit")
            self.assertIn("claude_warn:warn", headers["x-modeio-pre-actions"])
            self.assertEqual(len(upstream.requests), 0)
        finally:
            gateway.stop()
            upstream.stop()

    def test_unsupported_claude_event_returns_validation_error(self):
        upstream, gateway = self._start_pair(
            plugins={
                "redact": {
                    "enabled": False,
                    "module": "modeio_middleware.plugins.redact",
                }
            },
            profiles={
                "dev": {
                    "on_plugin_error": "warn",
                    "plugins": ["redact"],
                }
            },
        )
        try:
            status, _headers, payload = _post_json(
                gateway.base_url,
                "/connectors/claude/hooks",
                {
                    "hook_event_name": "SessionStart",
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(status, 400)
            self.assertEqual(payload["error"]["code"], "MODEIO_VALIDATION_ERROR")
        finally:
            gateway.stop()
            upstream.stop()


if __name__ == "__main__":
    unittest.main()
