#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict

from modeio_middleware.protocol.messages import VALID_PROTOCOL_ACTIONS


def normalize_protocol_decision_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("decision"), dict):
        payload = dict(raw["decision"])
    elif isinstance(raw, dict):
        payload = dict(raw)
    else:
        raise ValueError("protocol plugin result must be an object")

    action = str(payload.get("action", "")).strip().lower()
    if action in VALID_PROTOCOL_ACTIONS:
        payload["action"] = action
        return payload

    if action in {"allow", "warn", "modify", "defer", "block"}:
        payload["action"] = action
        return payload

    raise ValueError(f"unsupported protocol action '{action}'")
