#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Pattern, Sequence, Tuple

from modeio_middleware.core.contracts import ENDPOINT_CHAT_COMPLETIONS, ENDPOINT_RESPONSES

TEXT_PART_TYPES = {"text", "input_text", "output_text"}

EMAIL_PATTERN = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\(\d{2,4}\)|\d{2,4})[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"
)
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
API_KEY_PATTERN = re.compile(r"\b(?:sk|rk|pk)_[A-Za-z0-9]{16,}\b")


@dataclass(frozen=True)
class DetectionCandidate:
    entity_type: str
    value: str
    start: int
    end: int


DETECTION_RULES: Tuple[Tuple[str, Pattern[str]], ...] = (
    ("email", EMAIL_PATTERN),
    ("phone", PHONE_PATTERN),
    ("ssn", SSN_PATTERN),
    ("ipAddress", IPV4_PATTERN),
    ("apiKey", API_KEY_PATTERN),
)


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
    ordered = sorted(entries, key=lambda item: len(item.get("placeholder", "")), reverse=True)
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


def restore_tokens_deep(value: Any, entries: Sequence[Dict[str, str]]) -> Tuple[Any, int]:
    if isinstance(value, str):
        return _replace_tokens(value, entries)

    if isinstance(value, list):
        total = 0
        updated_items: List[Any] = []
        for item in value:
            updated_item, replaced = restore_tokens_deep(item, entries)
            updated_items.append(updated_item)
            total += replaced
        return updated_items, total

    if isinstance(value, dict):
        total = 0
        updated_dict: Dict[str, Any] = {}
        for key, item in value.items():
            updated_item, replaced = restore_tokens_deep(item, entries)
            updated_dict[key] = updated_item
            total += replaced
        return updated_dict, total

    return value, 0


def _iter_detection_candidates(text: str) -> List[DetectionCandidate]:
    candidates: List[DetectionCandidate] = []
    for entity_type, pattern in DETECTION_RULES:
        for match in pattern.finditer(text):
            value = match.group(0)
            if entity_type == "ipAddress" and not _is_valid_ipv4(value):
                continue
            candidates.append(
                DetectionCandidate(
                    entity_type=entity_type,
                    value=value,
                    start=match.start(),
                    end=match.end(),
                )
            )
    return sorted(candidates, key=lambda item: (item.start, -(item.end - item.start), item.entity_type))


def _is_valid_ipv4(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def _detect_sensitive_local(text: str) -> Dict[str, Any]:
    if not text:
        return {"sanitizedText": text or "", "items": []}

    sanitized_parts: List[str] = []
    items: List[Dict[str, Any]] = []
    counters: Dict[str, int] = {}
    cursor = 0

    for candidate in _iter_detection_candidates(text):
        if candidate.start < cursor:
            continue

        sanitized_parts.append(text[cursor : candidate.start])
        index = counters.get(candidate.entity_type, 0) + 1
        counters[candidate.entity_type] = index
        placeholder = f"[{_normalize_entity_type(candidate.entity_type)}_{index}]"
        sanitized_parts.append(placeholder)
        items.append(
            {
                "type": candidate.entity_type,
                "value": candidate.value,
                "maskedValue": placeholder,
                "startIndex": candidate.start,
                "endIndex": candidate.end,
            }
        )
        cursor = candidate.end

    sanitized_parts.append(text[cursor:])
    return {
        "sanitizedText": "".join(sanitized_parts),
        "items": items,
    }


def _shield_text(
    text: str,
    *,
    request_id: str,
    entries_by_identity: Dict[Tuple[str, str], str],
    entries: List[Dict[str, str]],
    counters: Dict[str, int],
) -> Tuple[str, int]:
    detection = _detect_sensitive_local(text)
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


def _shield_content_value(
    value: Any,
    *,
    request_id: str,
    entries_by_identity: Dict[Tuple[str, str], str],
    entries: List[Dict[str, str]],
    counters: Dict[str, int],
) -> Tuple[Any, int]:
    if isinstance(value, str):
        return _shield_text(
            value,
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )

    if isinstance(value, list):
        total = 0
        updated_list: List[Any] = []
        for part_index, part in enumerate(value):
            try:
                updated_part, replaced = _shield_content_node(
                    part,
                    request_id=request_id,
                    entries_by_identity=entries_by_identity,
                    entries=entries,
                    counters=counters,
                )
            except ValueError as error:
                raise ValueError(f"unsupported content part at index {part_index}") from error
            updated_list.append(updated_part)
            total += replaced
        return updated_list, total

    return value, 0


def _shield_content_node(
    value: Any,
    *,
    request_id: str,
    entries_by_identity: Dict[Tuple[str, str], str],
    entries: List[Dict[str, str]],
    counters: Dict[str, int],
) -> Tuple[Any, int]:
    if isinstance(value, str):
        return _shield_text(
            value,
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )

    if isinstance(value, list):
        return _shield_content_value(
            value,
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )

    if not isinstance(value, dict):
        return value, 0

    updated_value = dict(value)
    total = 0

    if updated_value.get("type") in TEXT_PART_TYPES and isinstance(updated_value.get("text"), str):
        sanitized, replaced = _shield_text(
            updated_value["text"],
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )
        updated_value["text"] = sanitized
        total += replaced

    if isinstance(updated_value.get("input_text"), str):
        sanitized, replaced = _shield_text(
            updated_value["input_text"],
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )
        updated_value["input_text"] = sanitized
        total += replaced

    if "content" in updated_value:
        updated_content, replaced = _shield_content_value(
            updated_value["content"],
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )
        updated_value["content"] = updated_content
        total += replaced

    return updated_value, total


def _shield_chat_request_body(
    body: Dict[str, Any],
    *,
    request_id: str,
    entries_by_identity: Dict[Tuple[str, str], str],
    entries: List[Dict[str, str]],
    counters: Dict[str, int],
) -> Tuple[Dict[str, Any], int]:
    payload = copy.deepcopy(body)
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return payload, 0

    total = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"messages[{index}] must be an object")
        content = message.get("content")
        sanitized, replaced = _shield_content_value(
            content,
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )
        message["content"] = sanitized
        total += replaced
    return payload, total


def _shield_responses_request_body(
    body: Dict[str, Any],
    *,
    request_id: str,
    entries_by_identity: Dict[Tuple[str, str], str],
    entries: List[Dict[str, str]],
    counters: Dict[str, int],
) -> Tuple[Dict[str, Any], int]:
    payload = copy.deepcopy(body)
    total = 0

    if "instructions" in payload:
        sanitized, replaced = _shield_content_value(
            payload.get("instructions"),
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )
        payload["instructions"] = sanitized
        total += replaced

    if "input" in payload:
        sanitized, replaced = _shield_content_value(
            payload.get("input"),
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )
        payload["input"] = sanitized
        total += replaced

    return payload, total


def shield_request_body(
    endpoint_kind: str,
    body: Dict[str, Any],
    *,
    request_id: str,
) -> Tuple[Dict[str, Any], int, List[Dict[str, str]]]:
    entries_by_identity: Dict[Tuple[str, str], str] = {}
    entries: List[Dict[str, str]] = []
    counters: Dict[str, int] = {}

    if endpoint_kind == ENDPOINT_CHAT_COMPLETIONS:
        updated_body, redaction_count = _shield_chat_request_body(
            body,
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )
        return updated_body, redaction_count, entries

    if endpoint_kind == ENDPOINT_RESPONSES:
        updated_body, redaction_count = _shield_responses_request_body(
            body,
            request_id=request_id,
            entries_by_identity=entries_by_identity,
            entries=entries,
            counters=counters,
        )
        return updated_body, redaction_count, entries

    return copy.deepcopy(body), 0, []
