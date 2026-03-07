#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LEGACY_PLUGIN_TEMPLATE = """#!/usr/bin/env python3

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

LEGACY_TEST_TEMPLATE = """#!/usr/bin/env python3

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

STDIO_PLUGIN_TEMPLATE = """#!/usr/bin/env python3

from __future__ import annotations

import json
import sys


def _reply(request_id, result=None, error=None):
    payload = {
        \"jsonrpc\": \"2.0\",
        \"id\": request_id,
    }
    if error is not None:
        payload[\"error\"] = error
    else:
        payload[\"result\"] = result or {{}}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + \"\\n\")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        if not line.strip():
            continue

        request = json.loads(line)
        method = request.get(\"method\")
        request_id = request.get(\"id\")

        if method == \"modeio.initialize\":
            _reply(request_id, {{
                \"protocol_version\": \"1.0\",
                \"name\": \"{plugin_name}\",
            }})
            continue

        if method == \"modeio.invoke\":
            _reply(request_id, {{
                \"decision\": {{
                    \"action\": \"annotate\",
                    \"message\": \"stdio plugin scaffold decision\",
                    \"findings\": []
                }}
            }})
            continue

        if method == \"modeio.shutdown\":
            _reply(request_id, {{\"ok\": True}})
            return 0

        _reply(request_id, error={{\"code\": -32601, \"message\": f\"unknown method: {method}\"}})

    return 0


if __name__ == \"__main__\":
    raise SystemExit(main())
"""

STDIO_TEST_TEMPLATE = """#!/usr/bin/env python3

import json
import unittest
from pathlib import Path


class Test{class_name}ProtocolPlugin(unittest.TestCase):
    def test_manifest_is_present(self):
        manifest_path = Path(__file__).resolve().parents[2] / \"modeio-middleware\" / \"plugins_external\" / \"{module_name}\" / \"manifest.json\"
        payload = json.loads(manifest_path.read_text(encoding=\"utf-8\"))
        self.assertEqual(payload[\"protocol_version\"], \"1.0\")
        self.assertEqual(payload[\"transport\"], \"stdio-jsonrpc\")


if __name__ == \"__main__\":
    unittest.main()
"""


def _to_module_name(raw: str) -> str:
    value = raw.strip().lower().replace("-", "_")
    value = re.sub(r"[^a-z0-9_]", "", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        raise ValueError("plugin name is empty after normalization")
    if value in {"base", "redact"}:
        raise ValueError(f"plugin name '{value}' is reserved")
    return value


def _to_class_name(module_name: str) -> str:
    return "".join(part.capitalize() for part in module_name.split("_"))


def _write_legacy_plugin(repo_root: Path, module_name: str, class_name: str, force: bool) -> None:
    plugin_path = repo_root / "modeio_middleware" / "plugins" / f"{module_name}.py"
    test_path = repo_root / "tests" / f"test_plugin_{module_name}.py"

    for path in (plugin_path, test_path):
        if path.exists() and not force:
            raise SystemExit(f"Refusing to overwrite existing file: {path}")

    plugin_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)

    plugin_path.write_text(LEGACY_PLUGIN_TEMPLATE.format(plugin_name=module_name), encoding="utf-8")
    test_path.write_text(
        LEGACY_TEST_TEMPLATE.format(
            module_name=module_name,
            class_name=class_name,
        ),
        encoding="utf-8",
    )

    print(f"Created plugin: {plugin_path}")
    print(f"Created test: {test_path}")


def _write_stdio_plugin(repo_root: Path, module_name: str, class_name: str, force: bool) -> None:
    plugin_dir = repo_root / "plugins_external" / module_name
    plugin_path = plugin_dir / "plugin.py"
    manifest_path = plugin_dir / "manifest.json"
    test_path = repo_root / "tests" / f"test_protocol_plugin_{module_name}.py"

    for path in (plugin_path, manifest_path, test_path):
        if path.exists() and not force:
            raise SystemExit(f"Refusing to overwrite existing file: {path}")

    plugin_dir.mkdir(parents=True, exist_ok=True)
    test_path.parent.mkdir(parents=True, exist_ok=True)

    plugin_path.write_text(STDIO_PLUGIN_TEMPLATE.format(plugin_name=module_name), encoding="utf-8")

    manifest_payload = {
        "name": module_name,
        "version": "0.1.0",
        "protocol_version": "1.0",
        "transport": "stdio-jsonrpc",
        "hooks": [
            "pre.request",
            "post.response",
            "post.stream.start",
            "post.stream.event",
            "post.stream.end",
        ],
        "capabilities": {
            "can_patch": False,
            "can_block": False,
            "needs_network": False,
            "needs_raw_body": False,
        },
    }
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    test_path.write_text(
        STDIO_TEST_TEMPLATE.format(
            module_name=module_name,
            class_name=class_name,
        ),
        encoding="utf-8",
    )

    print(f"Created stdio plugin: {plugin_path}")
    print(f"Created manifest: {manifest_path}")
    print(f"Created test: {test_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new modeio-middleware plugin")
    parser.add_argument("name", help="Plugin name (kebab-case or snake_case)")
    parser.add_argument(
        "--runtime",
        choices=["legacy_inprocess", "stdio_jsonrpc"],
        default="stdio_jsonrpc",
        help="Plugin runtime scaffold type (`legacy_inprocess` is internal-only for bundled plugins)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args(argv)

    module_name = _to_module_name(args.name)
    class_name = _to_class_name(module_name)

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    if args.runtime == "legacy_inprocess":
        _write_legacy_plugin(repo_root, module_name, class_name, args.force)
    else:
        _write_stdio_plugin(repo_root, module_name, class_name, args.force)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
