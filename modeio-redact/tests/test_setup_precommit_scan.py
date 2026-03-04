#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import setup_precommit_scan  # noqa: E402


def _managed_block(label: str = "balanced") -> str:
    return "\n".join(
        [
            setup_precommit_scan.START_MARKER,
            f"echo {label}",
            setup_precommit_scan.END_MARKER,
        ]
    )


class TestSetupPrecommitScan(unittest.TestCase):
    def test_upsert_requires_append_or_overwrite_for_unmanaged_hook(self):
        with self.assertRaises(setup_precommit_scan.SetupError):
            setup_precommit_scan._upsert_managed_block(
                "#!/bin/sh\necho custom\n",
                _managed_block(),
                append=False,
                overwrite=False,
            )

    def test_install_hook_file_creates_default_hook(self):
        with TemporaryDirectory() as temp_dir:
            hook_path = Path(temp_dir) / "pre-commit"
            result = setup_precommit_scan.install_hook_file(
                hook_path,
                managed_block=_managed_block(),
                append=False,
                overwrite=False,
            )
            self.assertTrue(result["changed"])
            self.assertEqual(result["action"], "installed")
            content = hook_path.read_text(encoding="utf-8")
            self.assertIn("#!/usr/bin/env sh", content)
            self.assertIn(setup_precommit_scan.START_MARKER, content)

    def test_install_hook_file_appends_when_requested(self):
        with TemporaryDirectory() as temp_dir:
            hook_path = Path(temp_dir) / "pre-commit"
            hook_path.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")

            result = setup_precommit_scan.install_hook_file(
                hook_path,
                managed_block=_managed_block(),
                append=True,
                overwrite=False,
            )
            self.assertTrue(result["changed"])
            self.assertEqual(result["action"], "appended")
            content = hook_path.read_text(encoding="utf-8")
            self.assertIn("echo custom", content)
            self.assertIn(setup_precommit_scan.START_MARKER, content)

    def test_install_hook_file_updates_existing_managed_block(self):
        with TemporaryDirectory() as temp_dir:
            hook_path = Path(temp_dir) / "pre-commit"
            hook_path.write_text(
                setup_precommit_scan._wrap_as_default_hook(_managed_block("old")),
                encoding="utf-8",
            )

            result = setup_precommit_scan.install_hook_file(
                hook_path,
                managed_block=_managed_block("new"),
                append=False,
                overwrite=False,
            )
            self.assertTrue(result["changed"])
            self.assertEqual(result["action"], "updated")
            content = hook_path.read_text(encoding="utf-8")
            self.assertNotIn("echo old", content)
            self.assertIn("echo new", content)

    def test_uninstall_hook_file_removes_only_managed_block(self):
        with TemporaryDirectory() as temp_dir:
            hook_path = Path(temp_dir) / "pre-commit"
            content = "#!/bin/sh\necho before\n\n" + _managed_block() + "\n\necho after\n"
            hook_path.write_text(content, encoding="utf-8")

            result = setup_precommit_scan.uninstall_hook_file(hook_path)
            self.assertTrue(result["changed"])
            self.assertEqual(result["action"], "removed_block")
            updated = hook_path.read_text(encoding="utf-8")
            self.assertIn("echo before", updated)
            self.assertIn("echo after", updated)
            self.assertNotIn(setup_precommit_scan.START_MARKER, updated)

    def test_uninstall_hook_file_deletes_managed_only_hook(self):
        with TemporaryDirectory() as temp_dir:
            hook_path = Path(temp_dir) / "pre-commit"
            hook_path.write_text(
                setup_precommit_scan._wrap_as_default_hook(_managed_block()),
                encoding="utf-8",
            )

            result = setup_precommit_scan.uninstall_hook_file(hook_path)
            self.assertTrue(result["changed"])
            self.assertEqual(result["action"], "removed_file")
            self.assertFalse(hook_path.exists())


if __name__ == "__main__":
    unittest.main()
