#!/usr/bin/env python3

import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.runtime.supervisor import JsonRpcStdioSupervisor  # noqa: E402


class TestJsonRpcStdioSupervisor(unittest.TestCase):
    def _write_plugin(self, directory: Path, body: str) -> Path:
        path = directory / "plugin.py"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return path

    def test_call_rejects_invalid_json_payload(self):
        with TemporaryDirectory() as temp_dir:
            plugin_path = self._write_plugin(
                Path(temp_dir),
                """
                import sys
                for _line in sys.stdin:
                    sys.stdout.write("not-json\\n")
                    sys.stdout.flush()
                    break
                """,
            )
            supervisor = JsonRpcStdioSupervisor(
                plugin_name="invalid-json",
                command=[sys.executable, str(plugin_path)],
            )
            try:
                with self.assertRaisesRegex(RuntimeError, "invalid JSON-RPC payload"):
                    supervisor.call(method="modeio.initialize", params={}, timeout_ms=500)
            finally:
                supervisor.shutdown()

    def test_call_rejects_mismatched_jsonrpc_id(self):
        with TemporaryDirectory() as temp_dir:
            plugin_path = self._write_plugin(
                Path(temp_dir),
                """
                import json
                import sys
                for _line in sys.stdin:
                    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": 999, "result": {}}) + "\\n")
                    sys.stdout.flush()
                    break
                """,
            )
            supervisor = JsonRpcStdioSupervisor(
                plugin_name="mismatched-id",
                command=[sys.executable, str(plugin_path)],
            )
            try:
                with self.assertRaisesRegex(RuntimeError, "mismatched JSON-RPC id"):
                    supervisor.call(method="modeio.initialize", params={}, timeout_ms=500)
            finally:
                supervisor.shutdown()

    def test_call_times_out_when_plugin_does_not_reply(self):
        with TemporaryDirectory() as temp_dir:
            plugin_path = self._write_plugin(
                Path(temp_dir),
                """
                import sys
                import time
                for _line in sys.stdin:
                    time.sleep(0.2)
                    sys.stdout.write('{"jsonrpc":"2.0","id":1,"result":{}}\\n')
                    sys.stdout.flush()
                    break
                """,
            )
            supervisor = JsonRpcStdioSupervisor(
                plugin_name="timeout",
                command=[sys.executable, str(plugin_path)],
            )
            try:
                with self.assertRaises(TimeoutError):
                    supervisor.call(method="modeio.initialize", params={}, timeout_ms=20)
            finally:
                supervisor.shutdown()


if __name__ == "__main__":
    unittest.main()
