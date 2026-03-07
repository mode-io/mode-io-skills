#!/usr/bin/env python3

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.cli import new_plugin  # noqa: E402


class TestNewPluginCli(unittest.TestCase):
    def test_stdio_scaffold_writes_expected_files_under_output_dir(self):
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            exit_code = new_plugin.main(["demo-policy", "--output-dir", str(output_dir)])

            self.assertEqual(exit_code, 0)
            plugin_dir = output_dir / "plugins_external" / "demo_policy"
            manifest_path = plugin_dir / "manifest.json"
            plugin_path = plugin_dir / "plugin.py"
            test_path = output_dir / "tests" / "test_protocol_plugin_demo_policy.py"

            self.assertTrue(manifest_path.exists())
            self.assertTrue(plugin_path.exists())
            self.assertTrue(test_path.exists())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["name"], "demo_policy")
            self.assertEqual(manifest["transport"], "stdio-jsonrpc")
            self.assertIn("pre.request", manifest["hooks"])


if __name__ == "__main__":
    unittest.main()
