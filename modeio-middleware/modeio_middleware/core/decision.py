#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from modeio_middleware.core.contracts import HOOK_ACTION_ALLOW, VALID_HOOK_ACTIONS


@dataclass
class HookDecision:
    action: str = HOOK_ACTION_ALLOW
    findings: List[Dict[str, Any]] = field(default_factory=list)
    message: Optional[str] = None
    request_body: Optional[Dict[str, Any]] = None
    request_headers: Optional[Dict[str, Any]] = None
    response_body: Optional[Dict[str, Any]] = None
    response_headers: Optional[Dict[str, Any]] = None
    event: Optional[Dict[str, Any]] = None


def _coerce_findings(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("field 'findings' must be an array")

    findings: List[Dict[str, Any]] = []
    for finding in raw:
        if isinstance(finding, dict):
            findings.append(finding)
    return findings


def _to_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, HookDecision):
        result: Dict[str, Any] = {
            "action": payload.action,
            "findings": payload.findings,
            "message": payload.message,
        }
        if payload.request_body is not None:
            result["request_body"] = payload.request_body
        if payload.request_headers is not None:
            result["request_headers"] = payload.request_headers
        if payload.response_body is not None:
            result["response_body"] = payload.response_body
        if payload.response_headers is not None:
            result["response_headers"] = payload.response_headers
        if payload.event is not None:
            result["event"] = payload.event
        return result

    if payload is None:
        return {}

    if isinstance(payload, dict):
        return payload

    raise ValueError("plugin hook result must be an object")


def normalize_decision_payload(payload: Any, *, stream: bool) -> Dict[str, Any]:
    data = _to_payload(payload)

    action = str(data.get("action", HOOK_ACTION_ALLOW)).strip().lower()
    if action not in VALID_HOOK_ACTIONS:
        raise ValueError(f"unsupported plugin action '{action}'")

    message = data.get("message")
    if message is not None and not isinstance(message, str):
        raise ValueError("field 'message' must be a string")

    normalized: Dict[str, Any] = {
        "action": action,
        "findings": _coerce_findings(data.get("findings")),
        "message": message,
    }

    if stream:
        if "event" in data:
            normalized["event"] = data["event"]
        return normalized

    if "request_body" in data:
        normalized["request_body"] = data["request_body"]
    if "request_headers" in data:
        normalized["request_headers"] = data["request_headers"]
    if "response_body" in data:
        normalized["response_body"] = data["response_body"]
    if "response_headers" in data:
        normalized["response_headers"] = data["response_headers"]

    return normalized
