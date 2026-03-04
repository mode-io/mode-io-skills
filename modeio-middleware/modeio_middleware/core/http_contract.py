#!/usr/bin/env python3

from __future__ import annotations

import json
import secrets
from typing import Any, Dict, Iterable, Optional

CONTRACT_VERSION = "0.1.0"


def new_request_id() -> str:
    return f"req_{secrets.token_hex(8)}"


def bool_header(value: bool) -> str:
    return "true" if value else "false"


def safe_json_dumps(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def error_payload(
    request_id: str,
    code: str,
    message: str,
    *,
    retryable: bool,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "message": message,
        "type": "modeio_error",
        "code": code,
        "request_id": request_id,
        "retryable": bool(retryable),
    }
    if details is not None:
        data["details"] = details
    return {"error": data}


def _csv(values: Iterable[str], default_value: str = "none") -> str:
    materialized = [str(value).strip() for value in values if str(value).strip()]
    if not materialized:
        return default_value
    return ",".join(materialized)


def contract_headers(
    request_id: str,
    *,
    profile: str,
    pre_actions: Iterable[str],
    post_actions: Iterable[str],
    degraded: Iterable[str],
    upstream_called: bool,
) -> Dict[str, str]:
    return {
        "x-modeio-contract-version": CONTRACT_VERSION,
        "x-modeio-request-id": request_id,
        "x-modeio-profile": profile,
        "x-modeio-pre-actions": _csv(pre_actions),
        "x-modeio-post-actions": _csv(post_actions),
        "x-modeio-degraded": _csv(degraded),
        "x-modeio-upstream-called": bool_header(upstream_called),
    }
