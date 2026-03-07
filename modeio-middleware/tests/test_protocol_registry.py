#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
FIXTURES_DIR = REPO_ROOT / "modeio-middleware" / "tests" / "fixtures"

sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.core.config_resolver import ResolvedPluginConfig  # noqa: E402
from modeio_middleware.registry.resolver import MODE_OBSERVE, resolve_plugin_runtime_spec  # noqa: E402


class TestProtocolRegistryResolver(unittest.TestCase):
    def test_stdio_runtime_defaults_to_observe_mode(self):
        resolved = ResolvedPluginConfig(
            name="external_policy",
            runtime="stdio_jsonrpc",
            module_path=None,
            enabled=True,
            config={
                "manifest": str(FIXTURES_DIR / "stdio_echo_manifest.json"),
                "command": [sys.executable, str(FIXTURES_DIR / "stdio_echo_plugin.py")],
            },
        )

        spec = resolve_plugin_runtime_spec(resolved=resolved, config_base_dir=REPO_ROOT / "modeio-middleware")
        self.assertEqual(spec.mode, MODE_OBSERVE)
        self.assertFalse(spec.capabilities["can_patch"])

    def test_stdio_runtime_capability_requires_grant(self):
        resolved = ResolvedPluginConfig(
            name="external_policy",
            runtime="stdio_jsonrpc",
            module_path=None,
            enabled=True,
            config={
                "manifest": str(FIXTURES_DIR / "stdio_echo_manifest.json"),
                "command": [sys.executable, str(FIXTURES_DIR / "stdio_echo_plugin.py")],
                "capabilities_grant": {
                    "can_patch": True,
                },
            },
        )

        spec = resolve_plugin_runtime_spec(resolved=resolved, config_base_dir=REPO_ROOT / "modeio-middleware")
        self.assertTrue(spec.capabilities["can_patch"])

    def test_runtime_cache_key_changes_when_runtime_config_changes(self):
        resolved_a = ResolvedPluginConfig(
            name="external_policy",
            runtime="stdio_jsonrpc",
            module_path=None,
            enabled=True,
            config={
                "manifest": str(FIXTURES_DIR / "stdio_echo_manifest.json"),
                "command": [sys.executable, str(FIXTURES_DIR / "stdio_echo_plugin.py")],
                "rewrite_to": "alpha",
            },
        )
        resolved_b = ResolvedPluginConfig(
            name="external_policy",
            runtime="stdio_jsonrpc",
            module_path=None,
            enabled=True,
            config={
                "manifest": str(FIXTURES_DIR / "stdio_echo_manifest.json"),
                "command": [sys.executable, str(FIXTURES_DIR / "stdio_echo_plugin.py")],
                "rewrite_to": "beta",
            },
        )

        spec_a = resolve_plugin_runtime_spec(resolved=resolved_a, config_base_dir=REPO_ROOT / "modeio-middleware")
        spec_b = resolve_plugin_runtime_spec(resolved=resolved_b, config_base_dir=REPO_ROOT / "modeio-middleware")

        self.assertNotEqual(spec_a.runtime_cache_key(), spec_b.runtime_cache_key())

    def test_relative_stdio_command_is_resolved_against_config_directory(self):
        resolved = ResolvedPluginConfig(
            name="external_policy",
            runtime="stdio_jsonrpc",
            module_path=None,
            enabled=True,
            config={
                "manifest": "../plugins_external/example/manifest.json",
                "command": ["python3", "../plugins_external/example/plugin.py"],
                "pool_size": 2,
            },
        )

        spec = resolve_plugin_runtime_spec(resolved=resolved, config_base_dir=REPO_ROOT / "modeio-middleware" / "config")
        self.assertEqual(spec.command[0], "python3")
        self.assertTrue(Path(spec.command[1]).is_absolute())
        self.assertTrue(Path(spec.command[1]).exists())
        self.assertEqual(spec.pool_size, 2)


if __name__ == "__main__":
    unittest.main()
