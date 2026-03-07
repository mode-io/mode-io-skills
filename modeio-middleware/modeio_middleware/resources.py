#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
RESOURCES_ROOT = PACKAGE_ROOT / "resources"


def bundled_default_config_path() -> Path:
    return RESOURCES_ROOT / "config" / "default.json"


def bundled_example_plugin_dir() -> Path:
    return RESOURCES_ROOT / "plugins_external" / "example"


def bundled_protocol_schema_dir() -> Path:
    return RESOURCES_ROOT / "protocol"
