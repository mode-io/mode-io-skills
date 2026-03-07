#!/usr/bin/env python3

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.resources import (  # noqa: E402
    bundled_default_config_path,
    bundled_example_plugin_dir,
    bundled_protocol_schema_dir,
)


class TestPackagingResources(unittest.TestCase):
    def test_bundled_resources_exist(self):
        self.assertTrue(bundled_default_config_path().exists())
        self.assertTrue((bundled_example_plugin_dir() / "manifest.json").exists())
        self.assertTrue((bundled_example_plugin_dir() / "plugin.py").exists())
        self.assertTrue((bundled_protocol_schema_dir() / "MODEIO_PLUGIN_MANIFEST.schema.json").exists())
        self.assertTrue((bundled_protocol_schema_dir() / "MODEIO_PLUGIN_MESSAGE.schema.json").exists())

    def test_repo_and_bundled_default_configs_match(self):
        repo_payload = json.loads((PACKAGE_ROOT / "config" / "default.json").read_text(encoding="utf-8"))
        bundled_payload = json.loads(bundled_default_config_path().read_text(encoding="utf-8"))
        self.assertEqual(repo_payload, bundled_payload)

    def test_repo_and_bundled_example_manifest_match(self):
        repo_payload = json.loads((PACKAGE_ROOT / "plugins_external" / "example" / "manifest.json").read_text(encoding="utf-8"))
        bundled_payload = json.loads((bundled_example_plugin_dir() / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(repo_payload, bundled_payload)


if __name__ == "__main__":
    unittest.main()
