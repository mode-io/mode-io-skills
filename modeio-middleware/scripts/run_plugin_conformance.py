#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modeio_middleware.core.decision import normalize_decision_payload  # noqa: E402
from modeio_middleware.protocol.manifest import load_plugin_manifest  # noqa: E402
from modeio_middleware.runtime.stdio_jsonrpc import StdioJsonRpcRuntime  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run basic conformance checks for stdio-jsonrpc plugin")
    parser.add_argument("manifest", help="Path to plugin manifest JSON")
    parser.add_argument("command", nargs="+", help="Plugin command and args")
    return parser.parse_args(argv)


def _sample_hook_input() -> dict:
    return {
        "request_id": "req_conformance",
        "endpoint_kind": "chat_completions",
        "profile": "dev",
        "request_body": {
            "model": "gpt-test",
            "messages": [{"role": "user", "content": "conformance test"}],
        },
        "request_headers": {},
        "plugin_config": {},
        "state": {},
        "plugin_state": {},
        "services": {},
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = load_plugin_manifest(Path(args.manifest).expanduser())
    runtime = StdioJsonRpcRuntime(
        plugin_name=manifest.name,
        command=[str(item) for item in args.command],
        manifest=manifest,
        timeout_ms=manifest.timeout_ms,
    )
    try:
        result = runtime.invoke("pre_request", _sample_hook_input())
        normalized = normalize_decision_payload(result, stream=False)
        print(
            json.dumps(
                {
                    "ok": True,
                    "plugin": manifest.name,
                    "action": normalized["action"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
