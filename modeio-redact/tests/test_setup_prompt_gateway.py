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
SCRIPTS_DIR = REPO_ROOT / "modeio-redact" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import setup_prompt_gateway  # noqa: E402


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


class TestSetupPromptGateway(unittest.TestCase):
    def test_normalize_gateway_base_url(self):
        self.assertEqual(
            setup_prompt_gateway._normalize_gateway_base_url("http://127.0.0.1:8787/v1/"),
            "http://127.0.0.1:8787/v1",
        )

    def test_normalize_gateway_base_url_requires_http(self):
        with self.assertRaises(setup_prompt_gateway.SetupError):
            setup_prompt_gateway._normalize_gateway_base_url("127.0.0.1:8787/v1")

    def test_derive_health_url_from_v1(self):
        self.assertEqual(
            setup_prompt_gateway._derive_health_url("http://127.0.0.1:8787/v1"),
            "http://127.0.0.1:8787/healthz",
        )

    def test_default_opencode_config_path_linux_xdg(self):
        path = setup_prompt_gateway._default_opencode_config_path(
            os_name="linux",
            env={"XDG_CONFIG_HOME": "/tmp/xdg"},
            home=Path("/home/test"),
        )
        self.assertEqual(path, Path("/tmp/xdg/opencode/opencode.json"))

    def test_default_opencode_config_path_windows_appdata(self):
        appdata = r"C:\Users\demo\AppData\Roaming"
        path = setup_prompt_gateway._default_opencode_config_path(
            os_name="windows",
            env={"APPDATA": appdata},
            home=Path(r"C:\Users\demo"),
        )
        self.assertEqual(path, Path(appdata) / "opencode" / "opencode.json")

    def test_codex_env_command_variants(self):
        url = "http://127.0.0.1:8787/v1"
        self.assertEqual(
            setup_prompt_gateway._codex_env_command("bash", url),
            'export OPENAI_BASE_URL="http://127.0.0.1:8787/v1"',
        )
        self.assertEqual(
            setup_prompt_gateway._codex_env_command("powershell", url),
            '$env:OPENAI_BASE_URL = "http://127.0.0.1:8787/v1"',
        )
        self.assertEqual(
            setup_prompt_gateway._codex_env_command("fish", url),
            'set -x OPENAI_BASE_URL "http://127.0.0.1:8787/v1"',
        )

    def test_codex_unset_env_command_variants(self):
        self.assertEqual(setup_prompt_gateway._codex_unset_env_command("bash"), "unset OPENAI_BASE_URL")
        self.assertEqual(
            setup_prompt_gateway._codex_unset_env_command("powershell"),
            "Remove-Item Env:OPENAI_BASE_URL",
        )
        self.assertEqual(setup_prompt_gateway._codex_unset_env_command("fish"), "set -e OPENAI_BASE_URL")

    def test_remove_opencode_base_url_match(self):
        source = {
            "provider": {
                "openai": {
                    "options": {
                        "baseURL": "http://127.0.0.1:8787/v1",
                        "apiKey": "x",
                    }
                }
            }
        }
        updated, changed, removed_value, reason = setup_prompt_gateway._remove_opencode_base_url(
            source,
            "http://127.0.0.1:8787/v1",
            force_remove=False,
        )
        self.assertTrue(changed)
        self.assertEqual(removed_value, "http://127.0.0.1:8787/v1")
        self.assertEqual(reason, "removed")
        self.assertNotIn("baseURL", updated["provider"]["openai"]["options"])

    def test_remove_opencode_base_url_mismatch_without_force(self):
        source = {
            "provider": {
                "openai": {
                    "options": {
                        "baseURL": "http://another-proxy.local/v1",
                    }
                }
            }
        }
        updated, changed, removed_value, reason = setup_prompt_gateway._remove_opencode_base_url(
            source,
            "http://127.0.0.1:8787/v1",
            force_remove=False,
        )
        self.assertFalse(changed)
        self.assertEqual(removed_value, "http://another-proxy.local/v1")
        self.assertEqual(reason, "base_url_mismatch")
        self.assertIn("baseURL", updated["provider"]["openai"]["options"])

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
        updated, changed = setup_prompt_gateway._apply_opencode_base_url(
            source,
            "http://127.0.0.1:8787/v1",
        )
        self.assertTrue(changed)
        self.assertEqual(
            updated["provider"]["openai"]["options"]["baseURL"],
            "http://127.0.0.1:8787/v1",
        )
        self.assertEqual(updated["provider"]["openai"]["options"]["apiKey"], "secret")

    def test_apply_opencode_base_url_rejects_wrong_shape(self):
        with self.assertRaises(setup_prompt_gateway.SetupError):
            setup_prompt_gateway._apply_opencode_base_url(
                {"provider": []},
                "http://127.0.0.1:8787/v1",
            )

    def test_apply_opencode_config_file_create_new(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "opencode.json"
            result = setup_prompt_gateway._apply_opencode_config_file(
                config_path=path,
                gateway_base_url="http://127.0.0.1:8787/v1",
                create_if_missing=True,
            )
            self.assertTrue(result["changed"])
            self.assertTrue(result["created"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["provider"]["openai"]["options"]["baseURL"],
                "http://127.0.0.1:8787/v1",
            )

    def test_apply_opencode_config_file_backup_existing(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "opencode.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": {
                            "openai": {
                                "options": {
                                    "baseURL": "http://old.local/v1",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = setup_prompt_gateway._apply_opencode_config_file(
                config_path=path,
                gateway_base_url="http://127.0.0.1:8787/v1",
                create_if_missing=False,
            )
            self.assertTrue(result["changed"])
            self.assertIsNotNone(result["backupPath"])
            self.assertTrue(Path(result["backupPath"]).exists())

    def test_apply_opencode_config_file_missing_without_create(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.json"
            with self.assertRaises(setup_prompt_gateway.SetupError):
                setup_prompt_gateway._apply_opencode_config_file(
                    config_path=path,
                    gateway_base_url="http://127.0.0.1:8787/v1",
                    create_if_missing=False,
                )

    def test_uninstall_opencode_config_file(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "opencode.json"
            path.write_text(
                json.dumps(
                    {
                        "provider": {
                            "openai": {
                                "options": {
                                    "baseURL": "http://127.0.0.1:8787/v1",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            result = setup_prompt_gateway._uninstall_opencode_config_file(
                config_path=path,
                gateway_base_url="http://127.0.0.1:8787/v1",
                force_remove=False,
            )
            self.assertTrue(result["changed"])
            self.assertEqual(result["reason"], "removed")
            self.assertIsNotNone(result["backupPath"])
            updated = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("baseURL", updated["provider"]["openai"]["options"])

    def test_cleanup_gateway_local_maps_removes_only_gateway_entries(self):
        with TemporaryDirectory() as temp_dir:
            map_dir = Path(temp_dir)
            (map_dir / "a.json").write_text(
                json.dumps({"sourceMode": "gateway-local"}),
                encoding="utf-8",
            )
            (map_dir / "b.json").write_text(
                json.dumps({"sourceMode": "api"}),
                encoding="utf-8",
            )
            (map_dir / "c.json").write_text("not-json", encoding="utf-8")

            result = setup_prompt_gateway._cleanup_gateway_local_maps(map_dir)
            self.assertEqual(result["scanned"], 3)
            self.assertEqual(result["matched"], 1)
            self.assertEqual(result["removed"], 1)
            self.assertTrue((map_dir / "b.json").exists())
            self.assertFalse((map_dir / "a.json").exists())

    def test_health_check_success(self):
        server = HealthServer()
        server.start()
        try:
            result = setup_prompt_gateway._check_gateway_health(server.health_url, timeout_seconds=2)
            self.assertTrue(result.checked)
            self.assertTrue(result.ok)
            self.assertEqual(result.status_code, 200)
        finally:
            server.stop()

    def test_health_check_failure_unreachable(self):
        result = setup_prompt_gateway._check_gateway_health(
            "http://127.0.0.1:9/healthz",
            timeout_seconds=1,
        )
        self.assertTrue(result.checked)
        self.assertFalse(result.ok)
        self.assertIsNone(result.status_code)

    def test_main_validation_error_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = setup_prompt_gateway.main(
                [
                    "--json",
                    "--create-opencode-config",
                ]
            )
        self.assertEqual(code, 2)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["type"], "validation_error")

    def test_main_validation_cleanup_requires_uninstall(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = setup_prompt_gateway.main(
                [
                    "--json",
                    "--cleanup-maps",
                ]
            )
        self.assertEqual(code, 2)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["success"])
        self.assertIn("requires --uninstall", payload["error"]["message"])

    def test_main_json_success_no_health(self):
        with TemporaryDirectory() as temp_dir:
            opencode_path = Path(temp_dir) / "opencode.json"
            output = io.StringIO()
            with redirect_stdout(output):
                code = setup_prompt_gateway.main(
                    [
                        "--json",
                        "--skip-health-check",
                        "--client",
                        "opencode",
                        "--apply-opencode",
                        "--create-opencode-config",
                        "--opencode-config",
                        str(opencode_path),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["success"])
            self.assertTrue(payload["opencode"]["changed"])
            self.assertFalse(payload["health"]["checked"])

    def test_main_json_uninstall_with_cleanup_and_opencode_rollback(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            opencode_path = root / "opencode.json"
            opencode_path.write_text(
                json.dumps(
                    {
                        "provider": {
                            "openai": {
                                "options": {
                                    "baseURL": "http://127.0.0.1:8787/v1",
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            map_dir = root / "maps"
            map_dir.mkdir(parents=True, exist_ok=True)
            (map_dir / "x.json").write_text(json.dumps({"sourceMode": "gateway-local"}), encoding="utf-8")
            (map_dir / "y.json").write_text(json.dumps({"sourceMode": "api"}), encoding="utf-8")

            output = io.StringIO()
            with redirect_stdout(output):
                code = setup_prompt_gateway.main(
                    [
                        "--json",
                        "--uninstall",
                        "--skip-health-check",
                        "--client",
                        "opencode",
                        "--apply-opencode",
                        "--opencode-config",
                        str(opencode_path),
                        "--cleanup-maps",
                        "--map-dir",
                        str(map_dir),
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["mode"], "uninstall")
            self.assertTrue(payload["opencode"]["changed"])
            self.assertEqual(payload["cleanup"]["removed"], 1)
            self.assertEqual(payload["cleanup"]["matched"], 1)
            updated = json.loads(opencode_path.read_text(encoding="utf-8"))
            self.assertNotIn("baseURL", updated["provider"]["openai"]["options"])


if __name__ == "__main__":
    unittest.main()
