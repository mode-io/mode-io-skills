#!/usr/bin/env python3

import io
import json
import sys
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import setup_middleware_gateway as setup_gateway  # noqa: E402


class HealthServer:
    def __init__(self):
        self._server = None
        self._thread = None
        self.health_url = ""

    def start(self):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                if self.path == "/healthz":
                    body = b'{"ok":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(404)
                self.end_headers()

            def log_message(self, _format, *_args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self._server.server_address
        self.health_url = f"http://{host}:{port}/healthz"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)


class TestSetupGateway(unittest.TestCase):
    def test_normalize_gateway_base_url(self):
        self.assertEqual(
            setup_gateway._normalize_gateway_base_url("http://127.0.0.1:8787/v1/"),
            "http://127.0.0.1:8787/v1",
        )

    def test_normalize_gateway_base_url_requires_http(self):
        with self.assertRaises(setup_gateway.SetupError):
            setup_gateway._normalize_gateway_base_url("127.0.0.1:8787/v1")

    def test_derive_health_url(self):
        self.assertEqual(
            setup_gateway._derive_health_url("http://127.0.0.1:8787/v1"),
            "http://127.0.0.1:8787/healthz",
        )

    def test_derive_claude_hook_url(self):
        self.assertEqual(
            setup_gateway._derive_claude_hook_url("http://127.0.0.1:8787/v1"),
            "http://127.0.0.1:8787/connectors/claude/hooks",
        )

    def test_codex_env_command_variants(self):
        url = "http://127.0.0.1:8787/v1"
        self.assertEqual(
            setup_gateway._codex_env_command("bash", url),
            'export OPENAI_BASE_URL="http://127.0.0.1:8787/v1"',
        )
        self.assertEqual(
            setup_gateway._codex_env_command("powershell", url),
            '$env:OPENAI_BASE_URL = "http://127.0.0.1:8787/v1"',
        )

    def test_codex_unset_command_variants(self):
        self.assertEqual(setup_gateway._codex_unset_env_command("bash"), "unset OPENAI_BASE_URL")
        self.assertEqual(
            setup_gateway._codex_unset_env_command("powershell"),
            "Remove-Item Env:OPENAI_BASE_URL",
        )

    def test_apply_opencode_base_url_updates_nested_object(self):
        source = {
            "model": "openai/gpt-4o-mini",
            "provider": {
                "openai": {
                    "options": {
                        "apiKey": "secret",
                    }
                }
            },
        }
        updated, changed = setup_gateway._apply_opencode_base_url(source, "http://127.0.0.1:8787/v1")
        self.assertTrue(changed)
        self.assertEqual(updated["provider"]["openai"]["options"]["baseURL"], "http://127.0.0.1:8787/v1")

    def test_apply_and_uninstall_opencode_config_file(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "opencode.json"
            apply_result = setup_gateway._apply_opencode_config_file(
                config_path=path,
                gateway_base_url="http://127.0.0.1:8787/v1",
                create_if_missing=True,
            )
            self.assertTrue(apply_result["changed"])
            self.assertTrue(path.exists())

            uninstall_result = setup_gateway._uninstall_opencode_config_file(
                config_path=path,
                gateway_base_url="http://127.0.0.1:8787/v1",
                force_remove=False,
            )
            self.assertTrue(uninstall_result["changed"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("baseURL", payload["provider"]["openai"]["options"])

    def test_apply_and_uninstall_claude_settings_file(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.json"
            apply_result = setup_gateway._apply_claude_settings_file(
                config_path=path,
                gateway_base_url="http://127.0.0.1:8787/v1",
                create_if_missing=True,
            )
            self.assertTrue(apply_result["changed"])
            self.assertTrue(path.exists())

            payload = json.loads(path.read_text(encoding="utf-8"))
            hooks = payload["hooks"]
            self.assertIn("UserPromptSubmit", hooks)
            self.assertIn("Stop", hooks)

            uninstall_result = setup_gateway._uninstall_claude_settings_file(
                config_path=path,
                gateway_base_url="http://127.0.0.1:8787/v1",
                force_remove=False,
            )
            self.assertTrue(uninstall_result["changed"])
            self.assertEqual(uninstall_result["removedHooks"], 2)

            payload_after = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("hooks", payload_after)

    def test_health_check_reports_healthy(self):
        server = HealthServer()
        server.start()
        try:
            health = setup_gateway._check_gateway_health(server.health_url, timeout_seconds=2)
            self.assertTrue(health.checked)
            self.assertTrue(health.ok)
            self.assertEqual(health.status_code, 200)
        finally:
            server.stop()

    def test_main_json_validation_error(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = setup_gateway.main(["--json", "--create-opencode-config"])
        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["type"], "validation_error")

    def test_main_json_validation_error_for_claude_create(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = setup_gateway.main(["--json", "--create-claude-settings"])
        self.assertEqual(code, 2)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["type"], "validation_error")


if __name__ == "__main__":
    unittest.main()
