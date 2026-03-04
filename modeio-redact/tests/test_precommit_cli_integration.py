#!/usr/bin/env python3

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPTS_SOURCE_DIR = Path(__file__).resolve().parents[1] / "scripts"


class TestPrecommitCliIntegration(unittest.TestCase):
    def _run(self, args, *, cwd: Path, expected_code: int = 0):
        result = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected_code,
            msg=(
                f"command failed: {' '.join(args)}\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            ),
        )
        return result

    def _prepare_repo(self, repo_root: Path) -> Path:
        scripts_dir = repo_root / "modeio-redact" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        for filename in ("detect_local.py", "precommit_scan.py", "setup_precommit_scan.py"):
            shutil.copy2(SCRIPTS_SOURCE_DIR / filename, scripts_dir / filename)

        self._run(["git", "init"], cwd=repo_root)
        return scripts_dir

    def test_install_scan_block_scan_and_uninstall(self):
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            scripts_dir = self._prepare_repo(repo_root)

            setup_script = scripts_dir / "setup_precommit_scan.py"
            scan_script = scripts_dir / "precommit_scan.py"
            hook_path = repo_root / ".git" / "hooks" / "pre-commit"

            install = self._run([sys.executable, str(setup_script), "--json"], cwd=repo_root)
            install_payload = json.loads(install.stdout)
            self.assertTrue(install_payload["success"])
            self.assertTrue(hook_path.exists())
            hook_body = hook_path.read_text(encoding="utf-8")
            self.assertIn("modeio-redact-precommit-scan", hook_body)

            (repo_root / "sample.txt").write_text("contact=alice@example.com\n", encoding="utf-8")
            self._run(["git", "add", "sample.txt"], cwd=repo_root)

            scan = self._run([sys.executable, str(scan_script), "--json"], cwd=repo_root, expected_code=1)
            scan_payload = json.loads(scan.stdout)
            self.assertFalse(scan_payload["success"])
            self.assertGreaterEqual(scan_payload["findingCount"], 1)
            self.assertEqual(scan_payload["findings"][0]["path"], "sample.txt")

            uninstall = self._run(
                [sys.executable, str(setup_script), "--uninstall", "--json"],
                cwd=repo_root,
            )
            uninstall_payload = json.loads(uninstall.stdout)
            self.assertTrue(uninstall_payload["success"])
            self.assertFalse(hook_path.exists())


if __name__ == "__main__":
    unittest.main()
