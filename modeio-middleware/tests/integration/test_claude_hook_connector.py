#!/usr/bin/env python3

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"
TESTS_DIR = REPO_ROOT / "modeio-middleware" / "tests"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from helpers.gateway_harness import completion_payload, post_json, start_gateway_pair  # noqa: E402
from helpers.plugin_modules import register_plugin_module  # noqa: E402
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


class _ClaudeMetadataPlugin(MiddlewarePlugin):
    name = "claude_metadata"

    def pre_request(self, hook_input):
        context = hook_input.get("context")
        request_context = hook_input.get("request_context")
        if not isinstance(context, dict):
            return {"action": "block", "message": "missing pre context"}
        if not isinstance(request_context, dict):
            return {"action": "block", "message": "missing mirrored pre request_context"}
        if context.get("source") != "claude_hooks":
            return {"action": "block", "message": "invalid pre source context"}
        if context.get("source_event") != "UserPromptSubmit":
            return {"action": "block", "message": "invalid pre source_event context"}
        if hook_input.get("source") != "claude_hooks":
            return {"action": "block", "message": "missing pre top-level source"}
        if hook_input.get("source_event") != "UserPromptSubmit":
            return {"action": "block", "message": "missing pre top-level source_event"}
        return {"action": "allow"}

    def post_response(self, hook_input):
        context = hook_input.get("context")
        request_context = hook_input.get("request_context")
        if not isinstance(context, dict):
            return {"action": "block", "message": "missing post context"}
        if not isinstance(request_context, dict):
            return {"action": "block", "message": "missing post request_context"}
        if request_context.get("source") != "claude_hooks":
            return {"action": "block", "message": "invalid post source request_context"}
        if request_context.get("source_event") != "Stop":
            return {"action": "block", "message": "invalid post source_event request_context"}
        if hook_input.get("source") != "claude_hooks":
            return {"action": "block", "message": "missing post top-level source"}
        if hook_input.get("source_event") != "Stop":
            return {"action": "block", "message": "missing post top-level source_event"}
        return {"action": "allow"}


class TestClaudeHookConnector(unittest.TestCase):
    def _start_pair(self, *, plugins, profiles):
        return start_gateway_pair(
            lambda _path, payload: completion_payload(payload.get("messages", [{}])[0].get("content", "")),
            plugins=plugins,
            profiles=profiles,
        )

    def test_user_prompt_block_returns_claude_block_decision(self):
        module_name = "modeio_middleware.tests.plugins.claude_block"
        register_plugin_module(module_name, _ClaudeBlockPlugin)

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
            status, headers, payload = post_json(
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
        register_plugin_module(module_name, _ClaudeBlockPlugin)

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
            status, headers, payload = post_json(
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
        register_plugin_module(module_name, _ClaudeWarnPlugin)

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
            status, headers, payload = post_json(
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
            status, _headers, payload = post_json(
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

    def test_connector_metadata_is_available_on_pre_and_post_hooks(self):
        module_name = "modeio_middleware.tests.plugins.claude_metadata"
        register_plugin_module(module_name, _ClaudeMetadataPlugin)

        upstream, gateway = self._start_pair(
            plugins={
                "claude_metadata": {
                    "enabled": True,
                    "module": module_name,
                }
            },
            profiles={
                "dev": {
                    "on_plugin_error": "warn",
                    "plugins": ["claude_metadata"],
                }
            },
        )
        try:
            pre_status, pre_headers, pre_payload = post_json(
                gateway.base_url,
                "/connectors/claude/hooks",
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "metadata check",
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(pre_status, 200)
            self.assertEqual(pre_payload, {})
            self.assertIn("claude_metadata:allow", pre_headers["x-modeio-pre-actions"])

            post_status, post_headers, post_payload = post_json(
                gateway.base_url,
                "/connectors/claude/hooks",
                {
                    "hook_event_name": "Stop",
                    "status": "completed",
                    "modeio": {"profile": "dev"},
                },
            )
            self.assertEqual(post_status, 200)
            self.assertEqual(post_payload, {})
            self.assertIn("claude_metadata:allow", post_headers["x-modeio-post-actions"])
        finally:
            gateway.stop()
            upstream.stop()


if __name__ == "__main__":
    unittest.main()
