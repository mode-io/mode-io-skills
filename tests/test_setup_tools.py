#!/usr/bin/env python3

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bootstrap_env = _load_module("bootstrap_env", "scripts/bootstrap_env.py")
doctor_env = _load_module("doctor_env", "scripts/doctor_env.py")


class TestBootstrapEnv(unittest.TestCase):
    def test_activation_command_posix(self):
        command = bootstrap_env.activation_command(Path("/tmp/example-venv"))
        self.assertEqual(command, "source /tmp/example-venv/bin/activate")

    def test_bootstrap_skip_install_creates_success_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_root = Path(temp_dir)
            (fake_root / "requirements.txt").write_text("requests>=2\n", encoding="utf-8")
            fake_venv = fake_root / ".venv"
            fake_venv_python = fake_venv / "bin" / "python"
            fake_venv_python.parent.mkdir(parents=True)
            fake_venv_python.write_text("", encoding="utf-8")

            with patch.object(bootstrap_env, "repo_root", return_value=fake_root):
                with patch.object(bootstrap_env, "_run_command") as mock_run:
                    mock_run.return_value.returncode = 0
                    mock_run.return_value.stderr = ""
                    payload = bootstrap_env.bootstrap_environment(
                        python_executable="python3",
                        venv_dir=fake_venv,
                        skip_install=True,
                        upgrade_pip=False,
                    )

        self.assertTrue(payload["success"])
        self.assertFalse(payload["installedRequirements"])
        self.assertFalse(payload["createdVenv"])


class TestDoctorEnv(unittest.TestCase):
    def test_summary_reports_error_for_missing_required_dependency(self):
        summary = doctor_env._summary(
            dependencies=[
                {"package": "requests", "requiredFor": "guardrail", "optional": False, "installed": False},
                {"package": "python-docx", "requiredFor": "docx", "optional": True, "installed": False},
            ],
            smoke=[{"name": "redact", "ok": True, "message": "ok"}],
            env_rows=[{"name": "MODEIO_GATEWAY_UPSTREAM_API_KEY", "set": False}],
        )
        self.assertEqual(summary["overall"], "error")
        self.assertTrue(summary["blockers"])
        self.assertTrue(summary["warnings"])

    def test_summary_reports_warning_without_blockers(self):
        summary = doctor_env._summary(
            dependencies=[
                {"package": "requests", "requiredFor": "guardrail", "optional": False, "installed": True},
                {"package": "python-docx", "requiredFor": "docx", "optional": True, "installed": False},
            ],
            smoke=[{"name": "redact", "ok": True, "message": "ok"}],
            env_rows=[{"name": "MODEIO_GATEWAY_UPSTREAM_API_KEY", "set": False}],
        )
        self.assertEqual(summary["overall"], "warning")
        self.assertFalse(summary["blockers"])
        self.assertTrue(summary["warnings"])


if __name__ == "__main__":
    unittest.main()
