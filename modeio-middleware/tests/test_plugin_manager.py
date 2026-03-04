#!/usr/bin/env python3

import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

from modeio_middleware.core.plugin_manager import PluginManager  # noqa: E402
from modeio_middleware.plugins.base import MiddlewarePlugin  # noqa: E402


def _register_test_plugin(module_name: str, plugin_cls):
    module = types.ModuleType(module_name)
    module.Plugin = plugin_cls
    sys.modules[module_name] = module


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


class _ErrorPlugin(MiddlewarePlugin):
    name = "error"

    def pre_request(self, _hook_input):
        raise RuntimeError("boom")


class _BlockPlugin(MiddlewarePlugin):
    name = "block"

    def pre_request(self, _hook_input):
        return {"action": "block", "message": "blocked by test plugin"}


class TestPluginManager(unittest.TestCase):
    def setUp(self):
        _register_test_plugin("modeio_middleware.tests.plugins.modify", _ModifyPlugin)
        _register_test_plugin("modeio_middleware.tests.plugins.error", _ErrorPlugin)
        _register_test_plugin("modeio_middleware.tests.plugins.block", _BlockPlugin)

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


if __name__ == "__main__":
    unittest.main()
