#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))
import middleware_gateway as gateway  # noqa: E402

from modeio_middleware.core.errors import MiddlewareError  # noqa: E402
from modeio_middleware.core.profiles import (  # noqa: E402
    normalize_profile_name,
    resolve_plugin_error_policy,
    resolve_profile,
    resolve_profile_plugins,
)


class TestProfilePolicy(unittest.TestCase):
    def test_normalize_profile_name_uses_default(self):
        self.assertEqual(normalize_profile_name(None, default_profile="dev"), "dev")
        self.assertEqual(normalize_profile_name("", default_profile="staging"), "staging")

    def test_resolve_profile_returns_named_profile(self):
        profiles = {"dev": {"on_plugin_error": "warn", "plugins": []}}
        profile = resolve_profile(profiles, "dev")
        self.assertEqual(profile["on_plugin_error"], "warn")

    def test_resolve_profile_raises_for_unknown_profile(self):
        with self.assertRaises(MiddlewareError):
            resolve_profile({"dev": {}}, "prod")

    def test_resolve_plugin_error_policy_prefers_override(self):
        policy = resolve_plugin_error_policy({"on_plugin_error": "warn"}, "fail_safe")
        self.assertEqual(policy, "fail_safe")

    def test_resolve_plugin_error_policy_rejects_invalid(self):
        with self.assertRaises(MiddlewareError):
            resolve_plugin_error_policy({"on_plugin_error": "warn"}, "broken")

    def test_resolve_profile_plugins_requires_string_entries(self):
        with self.assertRaises(MiddlewareError):
            resolve_profile_plugins({"plugins": ["guardrail", 123]})


if __name__ == "__main__":
    unittest.main()
