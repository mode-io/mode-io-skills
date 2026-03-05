#!/usr/bin/env python3

import unittest

from modeio_middleware.core.errors import MiddlewareError  # noqa: E402
from modeio_middleware.core.profiles import (  # noqa: E402
    normalize_profile_name,
    resolve_plugin_error_policy,
    resolve_profile_plugin_overrides,
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
            resolve_profile_plugins({"plugins": ["example_policy", 123]})

    def test_resolve_profile_plugin_overrides_returns_mapping(self):
        overrides = resolve_profile_plugin_overrides(
            {
                "plugin_overrides": {
                    "example_policy": {
                        "enabled": True,
                        "preset": "quiet",
                    }
                }
            }
        )
        self.assertTrue(overrides["example_policy"]["enabled"])
        self.assertEqual(overrides["example_policy"]["preset"], "quiet")

    def test_resolve_profile_plugin_overrides_rejects_non_object_override(self):
        with self.assertRaises(MiddlewareError):
            resolve_profile_plugin_overrides(
                {
                    "plugin_overrides": {
                        "example_policy": True,
                    }
                }
            )

    def test_resolve_profile_plugin_overrides_rejects_invalid_enabled(self):
        with self.assertRaises(MiddlewareError):
            resolve_profile_plugin_overrides(
                {
                    "plugin_overrides": {
                        "example_policy": {
                            "enabled": "yes",
                        }
                    }
                }
            )

    def test_resolve_profile_plugin_overrides_rejects_invalid_preset(self):
        with self.assertRaises(MiddlewareError):
            resolve_profile_plugin_overrides(
                {
                    "plugin_overrides": {
                        "example_policy": {
                            "preset": True,
                        }
                    }
                }
            )

    def test_resolve_profile_plugin_overrides_rejects_invalid_capabilities_grant(self):
        with self.assertRaises(MiddlewareError):
            resolve_profile_plugin_overrides(
                {
                    "plugin_overrides": {
                        "example_policy": {
                            "capabilities_grant": {
                                "can_patch": "yes",
                            }
                        }
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
