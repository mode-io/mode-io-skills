#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from modeio_middleware.protocol.manifest import load_plugin_manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate ModeIO plugin manifest")
    parser.add_argument("manifest", help="Path to plugin manifest JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest = load_plugin_manifest(Path(args.manifest).expanduser())
    payload = {
        "name": manifest.name,
        "version": manifest.version,
        "protocol_version": manifest.protocol_version,
        "transport": manifest.transport,
        "hooks": manifest.hooks,
        "capabilities": manifest.capabilities,
        "timeout_ms": manifest.timeout_ms,
        "source_path": manifest.source_path,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
