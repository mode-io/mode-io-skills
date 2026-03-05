#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from modeio_middleware.core.contracts import ENDPOINT_CHAT_COMPLETIONS, ENDPOINT_RESPONSES

TEXT_PART_TYPES = {"text", "input_text", "output_text"}


@dataclass(frozen=True)
class RequestIntent:
    endpoint_kind: str
    segments: List[str]
    instruction: str


def _collect_message_texts(messages: Any) -> List[str]:
    if not isinstance(messages, list):
        return []

    segments: List[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue

        content = message.get("content")
        if isinstance(content, str) and content.strip():
            segments.append(content)
            continue

        if not isinstance(content, list):
            continue

        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") not in TEXT_PART_TYPES:
                continue

            part_text = part.get("text")
            if isinstance(part_text, str) and part_text.strip():
                segments.append(part_text)

    return segments


def _collect_content_value_texts(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []

    if isinstance(value, list):
        segments: List[str] = []
        for item in value:
            segments.extend(_collect_content_value_texts(item))
        return segments

    if not isinstance(value, dict):
        return []

    content = value.get("content")
    if content is not None:
        return _collect_content_value_texts(content)

    segments: List[str] = []
    for key in ("text", "input_text", "instructions"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            segments.append(candidate)
    return segments


def collect_request_texts(endpoint_kind: str, request_body: Dict[str, Any]) -> List[str]:
    if endpoint_kind == ENDPOINT_CHAT_COMPLETIONS:
        return _collect_message_texts(request_body.get("messages"))

    if endpoint_kind == ENDPOINT_RESPONSES:
        segments: List[str] = []
        input_value = request_body.get("input")
        if input_value is not None:
            segments.extend(_collect_content_value_texts(input_value))

        instructions = request_body.get("instructions")
        if isinstance(instructions, str) and instructions.strip():
            segments.append(instructions)

        return segments

    return []


def extract_request_intent(endpoint_kind: str, request_body: Dict[str, Any]) -> RequestIntent:
    segments = collect_request_texts(endpoint_kind, request_body)
    instruction = "\n\n".join(segments).strip()
    return RequestIntent(
        endpoint_kind=endpoint_kind,
        segments=segments,
        instruction=instruction,
    )
