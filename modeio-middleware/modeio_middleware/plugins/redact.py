#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
REDACT_PACKAGE_ROOT = REPO_ROOT / "modeio-redact"
if str(REDACT_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(REDACT_PACKAGE_ROOT))

from modeio_redact.detection.detect_local import detect_sensitive_local

from modeio_middleware.plugins.base import MiddlewarePlugin

TEXT_PART_TYPES = {"text", "input_text", "output_text"}


def _normalize_entity_type(raw: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in (raw or "").upper())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip("_")
    return cleaned or "UNKNOWN"


def _make_token(request_id: str, entity_type: str, index: int, original: str) -> str:
    digest_source = f"{request_id}|{entity_type}|{index}|{original}".encode("utf-8")
    signature = hashlib.sha256(digest_source).hexdigest()[:10].upper()
    return f"__MIO_{entity_type}_{index}_{signature}__"


def _replace_tokens(text: str, entries: Sequence[Dict[str, str]]) -> Tuple[str, int]:
    restored = text
    replaced = 0
    ordered = sorted(entries, key=lambda item: len(item["placeholder"]), reverse=True)
    for item in ordered:
        placeholder = item.get("placeholder", "")
        original = item.get("original", "")
        if not placeholder:
            continue
        count = restored.count(placeholder)
        if count <= 0:
            continue
        restored = restored.replace(placeholder, original)
        replaced += count
    return restored, replaced


def _shield_text(
    text: str,
    *,
    request_id: str,
    entries_by_identity: Dict[Tuple[str, str], str],
    entries: List[Dict[str, str]],
    counters: Dict[str, int],
) -> Tuple[str, int]:
    detection = detect_sensitive_local(text)
    sanitized = detection.get("sanitizedText", text)
    if not isinstance(sanitized, str):
        raise ValueError("redact plugin detector returned non-string sanitizedText")

    items = detection.get("items", [])
    if not isinstance(items, list):
        return sanitized, 0

    placeholder_to_token: Dict[str, str] = {}
    replaced_occurrences = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        source_placeholder = item.get("maskedValue")
        original = item.get("value")
        if not isinstance(source_placeholder, str) or not source_placeholder:
            continue
        if not isinstance(original, str) or not original:
            continue

        entity_type = _normalize_entity_type(str(item.get("type", "UNKNOWN")))
        identity_key = (entity_type, original)
        token = entries_by_identity.get(identity_key)
        if token is None:
            index = counters.get(entity_type, 0) + 1
            counters[entity_type] = index
            token = _make_token(request_id, entity_type, index, original)
            entries_by_identity[identity_key] = token
            entries.append(
                {
                    "placeholder": token,
                    "original": original,
                    "type": entity_type,
                }
            )
        placeholder_to_token[source_placeholder] = token

    for source_placeholder in sorted(placeholder_to_token.keys(), key=len, reverse=True):
        token = placeholder_to_token[source_placeholder]
        count = sanitized.count(source_placeholder)
        if count <= 0:
            continue
        sanitized = sanitized.replace(source_placeholder, token)
        replaced_occurrences += count

    return sanitized, replaced_occurrences


class Plugin(MiddlewarePlugin):
    name = "redact"
    version = "0.1.0"

    def pre_request(self, hook_input: Dict[str, Any]) -> Dict[str, Any]:
        request_id = hook_input["request_id"]
        request_body = copy.deepcopy(hook_input["request_body"])
        messages = request_body.get("messages")
        if not isinstance(messages, list):
            return {"action": "allow"}

        entries_by_identity: Dict[Tuple[str, str], str] = {}
        entries: List[Dict[str, str]] = []
        counters: Dict[str, int] = {}
        redaction_count = 0

        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                raise ValueError(f"messages[{index}] must be an object")
            content = message.get("content")

            if isinstance(content, str):
                sanitized, replaced = _shield_text(
                    content,
                    request_id=request_id,
                    entries_by_identity=entries_by_identity,
                    entries=entries,
                    counters=counters,
                )
                message["content"] = sanitized
                redaction_count += replaced
                continue

            if not isinstance(content, list):
                continue

            for part_index, part in enumerate(content):
                if not isinstance(part, dict):
                    raise ValueError(f"messages[{index}].content[{part_index}] must be an object")
                if part.get("type") not in TEXT_PART_TYPES:
                    continue
                part_text = part.get("text")
                if not isinstance(part_text, str):
                    raise ValueError(f"messages[{index}].content[{part_index}].text must be string")
                sanitized, replaced = _shield_text(
                    part_text,
                    request_id=request_id,
                    entries_by_identity=entries_by_identity,
                    entries=entries,
                    counters=counters,
                )
                part["text"] = sanitized
                redaction_count += replaced

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
            "request_body": request_body,
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
        choices = payload.get("choices")
        if not isinstance(choices, list):
            return {"action": "allow"}

        replaced_total = 0
        for index, choice in enumerate(choices):
            if not isinstance(choice, dict):
                raise ValueError(f"choices[{index}] must be an object")
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")

            if isinstance(content, str):
                restored, replaced = _replace_tokens(content, entries)
                message["content"] = restored
                replaced_total += replaced
                continue

            if not isinstance(content, list):
                continue

            for part_index, part in enumerate(content):
                if not isinstance(part, dict):
                    raise ValueError(f"choices[{index}].message.content[{part_index}] must be an object")
                if part.get("type") not in TEXT_PART_TYPES:
                    continue
                part_text = part.get("text")
                if not isinstance(part_text, str):
                    raise ValueError(f"choices[{index}].message.content[{part_index}].text must be string")
                restored, replaced = _replace_tokens(part_text, entries)
                part["text"] = restored
                replaced_total += replaced

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
            "response_body": payload,
            "findings": [finding],
            "message": "shielded values restored in downstream response",
        }
