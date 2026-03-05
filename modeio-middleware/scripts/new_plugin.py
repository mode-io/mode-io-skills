#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path

PLUGIN_TEMPLATE = """#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict

from modeio_middleware.core.decision import HookDecision
from modeio_middleware.plugins.base import MiddlewarePlugin


class Plugin(MiddlewarePlugin):
    name = \"{plugin_name}\"
    version = \"0.1.0\"

    def pre_request(self, hook_input: Dict[str, Any]) -> HookDecision:
        _ = hook_input
        return HookDecision(action=\"allow\")
"""

TEST_TEMPLATE = """#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / \"modeio-middleware\" / \"scripts\"
sys.path.insert(0, str(SCRIPTS_DIR))

from modeio_middleware.plugins.{module_name} import Plugin  # noqa: E402


class Test{class_name}Plugin(unittest.TestCase):
    def test_pre_request_default_allow(self):
        result = Plugin().pre_request({{}})
        action = result.get(\"action\") if isinstance(result, dict) else result.action
        self.assertEqual(action, \"allow\")


if __name__ == \"__main__\":
    unittest.main()
"""


def _to_module_name(raw: str) -> str:
    value = raw.strip().lower().replace("-", "_")
    value = re.sub(r"[^a-z0-9_]", "", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        raise ValueError("plugin name is empty after normalization")
    if value in {"base", "guardrail", "redact"}:
        raise ValueError(f"plugin name '{value}' is reserved")
    return value


def _to_class_name(module_name: str) -> str:
    return "".join(part.capitalize() for part in module_name.split("_"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new modeio-middleware plugin")
    parser.add_argument("name", help="Plugin name (kebab-case or snake_case)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args(argv)

    module_name = _to_module_name(args.name)
    class_name = _to_class_name(module_name)

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    plugin_path = repo_root / "modeio_middleware" / "plugins" / f"{module_name}.py"
    test_path = repo_root / "tests" / f"test_plugin_{module_name}.py"

    for path in (plugin_path, test_path):
        if path.exists() and not args.force:
            raise SystemExit(f"Refusing to overwrite existing file: {path}")

    plugin_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)

    plugin_path.write_text(PLUGIN_TEMPLATE.format(plugin_name=module_name), encoding="utf-8")
    test_path.write_text(
        TEST_TEMPLATE.format(
            module_name=module_name,
            class_name=class_name,
        ),
        encoding="utf-8",
    )

    print(f"Created plugin: {plugin_path}")
    print(f"Created test: {test_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
