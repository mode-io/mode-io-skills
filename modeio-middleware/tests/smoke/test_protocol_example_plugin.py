#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
EXAMPLE_DIR = PACKAGE_ROOT / "plugins_external" / "example"

sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.protocol.manifest import load_plugin_manifest  # noqa: E402
from modeio_middleware.runtime.stdio_jsonrpc import StdioJsonRpcRuntime  # noqa: E402


def _sample_hook_input() -> dict:
    return {
        "request_id": "req_example_plugin",
        "endpoint_kind": "chat_completions",
        "profile": "dev",
        "request_body": {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "hello"}],
        },
        "request_headers": {},
        "plugin_config": {},
        "plugin_state": {},
    }


class TestShippedExamplePlugin(unittest.TestCase):
    def test_manifest_loads(self):
        manifest = load_plugin_manifest(EXAMPLE_DIR / "manifest.json")
        self.assertEqual(manifest.name, "examples/hello-policy")
        self.assertEqual(manifest.transport, "stdio-jsonrpc")

    def test_runtime_invokes(self):
        manifest = load_plugin_manifest(EXAMPLE_DIR / "manifest.json")
        runtime = StdioJsonRpcRuntime(
            plugin_name=manifest.name,
            command=[sys.executable, str(EXAMPLE_DIR / "plugin.py")],
            manifest=manifest,
            timeout_ms=manifest.timeout_ms,
        )
        try:
            result = runtime.invoke("pre_request", _sample_hook_input())
        finally:
            runtime.shutdown()

        self.assertEqual(result["action"], "warn")
        self.assertIn("example external policy observed request", result["message"])


if __name__ == "__main__":
    unittest.main()
