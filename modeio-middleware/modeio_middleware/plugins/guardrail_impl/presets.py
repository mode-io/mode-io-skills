#!/usr/bin/env python3

from __future__ import annotations

from typing import Any

PRESET_INTERACTIVE = "interactive"
PRESET_QUIET = "quiet"
DEFAULT_PRESET = PRESET_INTERACTIVE
VALID_PRESETS = {PRESET_INTERACTIVE, PRESET_QUIET}


def normalize_preset(raw: Any, *, default: str = DEFAULT_PRESET) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return default
    candidate = raw.strip().lower()
    if candidate in VALID_PRESETS:
        return candidate
    return default
