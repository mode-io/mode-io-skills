#!/usr/bin/env python3

from __future__ import annotations

PROTOCOL_NAME = "modeio-plugin-protocol"
PROTOCOL_VERSION = "1.0"
SUPPORTED_PROTOCOL_VERSIONS = ("1.0",)


def is_supported_protocol_version(raw: str) -> bool:
    value = str(raw or "").strip()
    return value in SUPPORTED_PROTOCOL_VERSIONS
