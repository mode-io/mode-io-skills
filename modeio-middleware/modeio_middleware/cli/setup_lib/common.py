#!/usr/bin/env python3

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class SetupError(RuntimeError):
    pass


@dataclass(frozen=True)
class HealthCheckResult:
    checked: bool
    ok: bool
    status_code: Optional[int]
    message: str


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_gateway_base_url(raw: str) -> str:
    if not isinstance(raw, str):
        raise SetupError("gateway base URL must be a string")
    value = raw.strip()
    if not value:
        raise SetupError("gateway base URL cannot be empty")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise SetupError("gateway base URL must start with http:// or https://")
    return value.rstrip("/")


def detect_os_name(os_name: Optional[str] = None) -> str:
    if os_name:
        return os_name.strip().lower()
    return platform.system().strip().lower()


def derive_health_url(gateway_base_url: str) -> str:
    normalized = normalize_gateway_base_url(gateway_base_url)
    if normalized.endswith("/v1"):
        return normalized[:-3] + "/healthz"
    return normalized + "/healthz"


def ensure_object(value: Any, label: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise SetupError(f"{label} must be an object")


def read_json_file(path: Path) -> Dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SetupError(f"failed to read config file: {path}") from error

    try:
        parsed = json.loads(content)
    except ValueError as error:
        raise SetupError(f"invalid JSON in config file: {path}") from error

    if not isinstance(parsed, dict):
        raise SetupError(f"config root must be an object: {path}")
    return parsed


def write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(body + "\n", encoding="utf-8")
