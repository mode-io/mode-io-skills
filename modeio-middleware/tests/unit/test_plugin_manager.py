#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"
TESTS_DIR = REPO_ROOT / "modeio-middleware" / "tests"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

from modeio_middleware.core.contracts import ENDPOINT_CHAT_COMPLETIONS  # noqa: E402
from modeio_middleware.core.decision import HookDecision  # noqa: E402
from modeio_middleware.core.plugin_manager import PluginManager  # noqa: E402
from modeio_middleware.core.services.telemetry import PluginTelemetry  # noqa: E402
from modeio_middleware.plugins.base import MiddlewarePlugin  # noqa: E402
from helpers.plugin_modules import register_plugin_module  # noqa: E402


class _ModifyPlugin(MiddlewarePlugin):
    name = "modify"

    def pre_request(self, hook_input):
        body = dict(hook_input["request_body"])
        body["model"] = "rewritten-model"
        return {"action": "modify", "request_body": body}

    def post_response(self, hook_input):
        body = dict(hook_input["response_body"])
        body["tag"] = "done"
        return {"action": "modify", "response_body": body}

    def post_stream_event(self, hook_input):
        event = dict(hook_input["event"])
        payload = dict(event.get("payload") or {})
        payload["tag"] = "stream"
        event["payload"] = payload
        return {"action": "modify", "event": event}


class _ErrorPlugin(MiddlewarePlugin):
    name = "error"

    def pre_request(self, _hook_input):
        raise RuntimeError("boom")


class _BlockPlugin(MiddlewarePlugin):
    name = "block"

    def pre_request(self, _hook_input):
        return {"action": "block", "message": "blocked by test plugin"}


class _DecisionPlugin(MiddlewarePlugin):
    name = "decision"

    def pre_request(self, _hook_input):
        return HookDecision(
            action="warn",
            message="decision-based warning",
            findings=[{"class": "test_decision", "severity": "low", "confidence": 1.0, "reason": "ok", "evidence": []}],
        )


class _InvalidActionPlugin(MiddlewarePlugin):
    name = "invalid_action"

    def pre_request(self, _hook_input):
        return {"action": "defer", "message": "removed action"}


class TestPluginManager(unittest.TestCase):
    def setUp(self):
        register_plugin_module("modeio_middleware.tests.plugins.modify", _ModifyPlugin)
        register_plugin_module("modeio_middleware.tests.plugins.error", _ErrorPlugin)
        register_plugin_module("modeio_middleware.tests.plugins.block", _BlockPlugin)
        register_plugin_module("modeio_middleware.tests.plugins.decision", _DecisionPlugin)
        register_plugin_module("modeio_middleware.tests.plugins.invalid_action", _InvalidActionPlugin)

    def test_resolve_active_plugins_enabled_order(self):
        manager = PluginManager(
            {
                "modify": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.modify",
                },
                "error": {
                    "enabled": False,
                    "module": "modeio_middleware.tests.plugins.error",
                },
            }
        )

        active = manager.resolve_active_plugins(["modify", "error"], {})
        self.assertEqual([plugin.name for plugin in active], ["modify"])

    def test_apply_pre_request_modify(self):
        manager = PluginManager(
            {
                "modify": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.modify",
                }
            }
        )
        active = manager.resolve_active_plugins(["modify"], {})

        result = manager.apply_pre_request(
            active,
            request_id="req1",
            endpoint_kind=ENDPOINT_CHAT_COMPLETIONS,
            profile="dev",
            request_body={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
            request_headers={},
            context={},
            shared_state={},
            on_plugin_error="warn",
        )

        self.assertFalse(result.blocked)
        self.assertEqual(result.body["model"], "rewritten-model")
        self.assertIn("modify:modify", result.actions)

    def test_resolve_active_plugins_reuses_runtime_instances(self):
        manager = PluginManager(
            {
                "modify": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.modify",
                }
            }
        )

        first_active = manager.resolve_active_plugins(["modify"], {})
        second_active = manager.resolve_active_plugins(["modify"], {})

        self.assertIs(first_active[0].runtime, second_active[0].runtime)

    def test_apply_pre_request_downgrades_modify_when_connector_disallows_patch(self):
        manager = PluginManager(
            {
                "modify": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.modify",
                }
            }
        )
        active = manager.resolve_active_plugins(["modify"], {})

        result = manager.apply_pre_request(
            active,
            request_id="req1",
            endpoint_kind=ENDPOINT_CHAT_COMPLETIONS,
            profile="dev",
            request_body={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
            request_headers={},
            context={},
            shared_state={},
            on_plugin_error="warn",
            connector_capabilities={
                "can_patch": False,
                "can_block": True,
            },
        )

        self.assertFalse(result.blocked)
        self.assertEqual(result.body["model"], "gpt-test")
        self.assertIn("modify:warn", result.actions)

    def test_apply_pre_request_error_fail_safe_blocks(self):
        manager = PluginManager(
            {
                "error": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.error",
                }
            }
        )
        active = manager.resolve_active_plugins(["error"], {})

        result = manager.apply_pre_request(
            active,
            request_id="req1",
            endpoint_kind=ENDPOINT_CHAT_COMPLETIONS,
            profile="prod",
            request_body={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
            request_headers={},
            context={},
            shared_state={},
            on_plugin_error="fail_safe",
        )

        self.assertTrue(result.blocked)
        self.assertIn("plugin 'error' failed", result.block_message)

    def test_apply_pre_request_block_action(self):
        manager = PluginManager(
            {
                "block": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.block",
                }
            }
        )
        active = manager.resolve_active_plugins(["block"], {})

        result = manager.apply_pre_request(
            active,
            request_id="req1",
            endpoint_kind=ENDPOINT_CHAT_COMPLETIONS,
            profile="dev",
            request_body={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
            request_headers={},
            context={},
            shared_state={},
            on_plugin_error="warn",
        )
        self.assertTrue(result.blocked)
        self.assertEqual(result.block_message, "blocked by test plugin")

    def test_apply_post_response_modify(self):
        manager = PluginManager(
            {
                "modify": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.modify",
                }
            }
        )
        active = manager.resolve_active_plugins(["modify"], {})

        result = manager.apply_post_response(
            active,
            request_id="req1",
            endpoint_kind=ENDPOINT_CHAT_COMPLETIONS,
            profile="dev",
            request_context={},
            response_body={"id": "resp"},
            response_headers={},
            shared_state={},
            on_plugin_error="warn",
        )
        self.assertFalse(result.blocked)
        self.assertEqual(result.body["tag"], "done")
        self.assertIn("modify:modify", result.actions)

    def test_apply_post_stream_event_modify(self):
        manager = PluginManager(
            {
                "modify": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.modify",
                }
            }
        )
        active = manager.resolve_active_plugins(["modify"], {})

        result = manager.apply_post_stream_event(
            active,
            request_id="req1",
            endpoint_kind=ENDPOINT_CHAT_COMPLETIONS,
            profile="dev",
            request_context={},
            event={"data_type": "json", "payload": {"id": "evt1"}},
            shared_state={},
            on_plugin_error="warn",
        )

        self.assertFalse(result.blocked)
        self.assertEqual(result.event["payload"]["tag"], "stream")
        self.assertIn("modify:modify", result.actions)

    def test_apply_pre_request_accepts_hookdecision_payload(self):
        manager = PluginManager(
            {
                "decision": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.decision",
                }
            }
        )
        active = manager.resolve_active_plugins(["decision"], {})

        result = manager.apply_pre_request(
            active,
            request_id="req1",
            endpoint_kind=ENDPOINT_CHAT_COMPLETIONS,
            profile="dev",
            request_body={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
            request_headers={},
            context={},
            shared_state={},
            on_plugin_error="warn",
        )

        self.assertFalse(result.blocked)
        self.assertIn("decision:warn", result.actions)
        self.assertEqual(result.findings[0]["class"], "test_decision")

    def test_apply_pre_request_records_telemetry(self):
        manager = PluginManager(
            {
                "modify": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.modify",
                }
            }
        )
        active = manager.resolve_active_plugins(["modify"], {})
        telemetry = PluginTelemetry()

        result = manager.apply_pre_request(
            active,
            request_id="req1",
            endpoint_kind=ENDPOINT_CHAT_COMPLETIONS,
            profile="dev",
            request_body={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
            request_headers={},
            context={},
            shared_state={},
            on_plugin_error="warn",
            services={"telemetry": telemetry},
        )

        self.assertFalse(result.blocked)
        snapshot = telemetry.snapshot()
        self.assertEqual(snapshot["modify"]["calls"], 1)
        self.assertEqual(snapshot["modify"]["hooks"]["pre_request"], 1)

    def test_apply_pre_request_rejects_removed_defer_action(self):
        manager = PluginManager(
            {
                "defer": {
                    "enabled": True,
                    "module": "modeio_middleware.tests.plugins.invalid_action",
                }
            }
        )
        active = manager.resolve_active_plugins(["defer"], {})

        result = manager.apply_pre_request(
            active,
            request_id="req1",
            endpoint_kind=ENDPOINT_CHAT_COMPLETIONS,
            profile="dev",
            request_body={"model": "gpt-test", "messages": [{"role": "user", "content": "hello"}]},
            request_headers={},
            context={},
            shared_state={},
            on_plugin_error="warn",
            services={},
        )

        self.assertFalse(result.blocked)
        self.assertIn("defer:error", result.actions)
        self.assertIn("plugin_error:defer", result.degraded)


if __name__ == "__main__":
    unittest.main()
