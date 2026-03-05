#!/usr/bin/env python3

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.core.config_resolver import load_preset_registry, resolve_plugin_runtime_config
from modeio_middleware.core.errors import MiddlewareError


class TestConfigResolver(unittest.TestCase):
    def test_load_preset_registry_from_file(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "default.json"
            preset_path = root / "presets" / "guardrail.json"
            preset_path.parent.mkdir(parents=True, exist_ok=True)
            preset_path.write_text(
                json.dumps(
                    {
                        "plugin": "guardrail",
                        "presets": {
                            "quiet": {
                                "block_rule": "critical_or_high_irreversible_destructive_unapproved"
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            registry = load_preset_registry(
                {
                    "preset_files": ["presets/guardrail.json"],
                },
                config_file_path=config_path,
            )

            self.assertIn("guardrail", registry)
            self.assertEqual(
                registry["guardrail"]["quiet"]["block_rule"],
                "critical_or_high_irreversible_destructive_unapproved",
            )

    def test_resolve_plugin_runtime_config_merge_precedence(self):
        resolved = resolve_plugin_runtime_config(
            plugin_name="guardrail",
            plugin_config={
                "enabled": False,
                "module": "modeio_middleware.plugins.guardrail",
                "preset": "interactive",
                "base_only": "from_base",
                "shared": "from_base",
            },
            preset_registry={
                "guardrail": {
                    "interactive": {
                        "shared": "from_preset",
                        "preset_only": "from_preset",
                    },
                    "quiet": {
                        "shared": "from_quiet_preset",
                        "quiet_only": "from_quiet_preset",
                    },
                }
            },
            profile_override={
                "enabled": True,
                "preset": "quiet",
                "shared": "from_profile",
                "profile_only": "from_profile",
            },
            request_override={
                "shared": "from_request",
                "request_only": "from_request",
            },
        )

        self.assertTrue(resolved.enabled)
        self.assertEqual(resolved.module_path, "modeio_middleware.plugins.guardrail")
        self.assertEqual(resolved.config["preset"], "quiet")
        self.assertEqual(resolved.config["base_only"], "from_base")
        self.assertEqual(resolved.config["quiet_only"], "from_quiet_preset")
        self.assertEqual(resolved.config["profile_only"], "from_profile")
        self.assertEqual(resolved.config["request_only"], "from_request")
        self.assertEqual(resolved.config["shared"], "from_request")

    def test_resolve_plugin_runtime_config_raises_for_unknown_preset(self):
        with self.assertRaises(MiddlewareError):
            resolve_plugin_runtime_config(
                plugin_name="guardrail",
                plugin_config={
                    "enabled": True,
                    "module": "modeio_middleware.plugins.guardrail",
                    "preset": "missing",
                },
                preset_registry={},
                profile_override={},
                request_override={},
            )


if __name__ == "__main__":
    unittest.main()
