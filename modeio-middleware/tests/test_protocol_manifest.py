#!/usr/bin/env python3

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
FIXTURES_DIR = REPO_ROOT / "modeio-middleware" / "tests" / "fixtures"

sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.core.errors import MiddlewareError  # noqa: E402
from modeio_middleware.protocol.manifest import load_plugin_manifest  # noqa: E402


class TestProtocolManifest(unittest.TestCase):
    def test_load_fixture_manifest(self):
        manifest = load_plugin_manifest(FIXTURES_DIR / "stdio_echo_manifest.json")
        self.assertEqual(manifest.name, "tests/stdio-echo-plugin")
        self.assertEqual(manifest.protocol_version, "1.0")
        self.assertTrue(manifest.capabilities["can_patch"])
        self.assertIn("pre.request", manifest.hooks)

    def test_rejects_unsupported_protocol_version(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "tests/bad",
                        "version": "0.1.0",
                        "protocol_version": "2.0",
                        "transport": "stdio-jsonrpc",
                        "hooks": ["pre.request"],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(MiddlewareError):
                load_plugin_manifest(path)


if __name__ == "__main__":
    unittest.main()
