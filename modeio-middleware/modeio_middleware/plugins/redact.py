#!/usr/bin/env python3

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Dict

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
REDACT_PACKAGE_ROOT = REPO_ROOT / "modeio-redact"
if str(REDACT_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(REDACT_PACKAGE_ROOT))

from modeio_middleware.plugins.base import MiddlewarePlugin
from modeio_middleware.plugins.redact_utils import restore_tokens_deep, shield_request_body


class Plugin(MiddlewarePlugin):
    name = "redact"
    version = "0.1.0"

    def pre_request(self, hook_input: Dict[str, Any]) -> Dict[str, Any]:
        request_id = hook_input["request_id"]
        endpoint_kind = hook_input.get("endpoint_kind", "chat_completions")
        request_body = hook_input["request_body"]

        updated_body, redaction_count, entries = shield_request_body(
            endpoint_kind,
            request_body,
            request_id=request_id,
        )

        plugin_state = hook_input.get("plugin_state")
        if isinstance(plugin_state, dict):
            plugin_state["entries"] = entries
            plugin_state["redactionCount"] = redaction_count

        if redaction_count <= 0:
            return {"action": "allow"}

        finding = {
            "class": "pii_exposure",
            "severity": "medium",
            "confidence": 0.8,
            "reason": "redact plugin shielded sensitive text before upstream call",
            "evidence": [f"redaction_count={redaction_count}"],
        }
        return {
            "action": "modify",
            "request_body": updated_body,
            "findings": [finding],
            "message": "sensitive text shielded before provider call",
        }

    def post_response(self, hook_input: Dict[str, Any]) -> Dict[str, Any]:
        plugin_state = hook_input.get("plugin_state")
        if not isinstance(plugin_state, dict):
            return {"action": "allow"}

        entries = plugin_state.get("entries", [])
        if not isinstance(entries, list) or not entries:
            return {"action": "allow"}

        payload = copy.deepcopy(hook_input["response_body"])
        restored_payload, replaced_total = restore_tokens_deep(payload, entries)

        if replaced_total <= 0:
            return {"action": "allow"}

        finding = {
            "class": "pii_restore",
            "severity": "low",
            "confidence": 0.8,
            "reason": "redact plugin restored shielded values in model response",
            "evidence": [f"restore_count={replaced_total}"],
        }
        return {
            "action": "modify",
            "response_body": restored_payload,
            "findings": [finding],
            "message": "shielded values restored in downstream response",
        }

    def post_stream_event(self, hook_input: Dict[str, Any]) -> Dict[str, Any]:
        plugin_state = hook_input.get("plugin_state")
        if not isinstance(plugin_state, dict):
            return {"action": "allow", "event": hook_input.get("event")}

        entries = plugin_state.get("entries", [])
        if not isinstance(entries, list) or not entries:
            return {"action": "allow", "event": hook_input.get("event")}

        event = hook_input.get("event")
        if not isinstance(event, dict):
            raise ValueError("stream event must be an object")

        if event.get("data_type") != "json":
            return {"action": "allow", "event": event}

        payload = event.get("payload")
        if not isinstance(payload, dict):
            return {"action": "allow", "event": event}

        restored_payload, replaced_total = restore_tokens_deep(payload, entries)
        if replaced_total <= 0:
            return {"action": "allow", "event": event}

        updated_event = dict(event)
        updated_event["payload"] = restored_payload

        finding = {
            "class": "pii_restore_stream",
            "severity": "low",
            "confidence": 0.8,
            "reason": "redact plugin restored shielded values in streamed response events",
            "evidence": [f"restore_count={replaced_total}"],
        }
        return {
            "action": "modify",
            "event": updated_event,
            "findings": [finding],
            "message": "shielded values restored in stream events",
        }
