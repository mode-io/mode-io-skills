#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Iterator, List, Optional


def _to_line_bytes(raw_line: bytes | str) -> bytes:
    if isinstance(raw_line, str):
        return raw_line.encode("utf-8")
    return raw_line


def _decode_line(raw_line: bytes | str) -> str:
    line_bytes = _to_line_bytes(raw_line)
    try:
        text = line_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = line_bytes.decode("utf-8", errors="replace")
    return text.rstrip("\r")


def parse_sse_event(raw_lines: Iterable[bytes | str]) -> Optional[Dict[str, Any]]:
    comments: List[str] = []
    data_lines: List[str] = []
    extra_fields: List[Dict[str, str]] = []
    event_name: Optional[str] = None
    event_id: Optional[str] = None
    retry: Optional[str] = None

    for raw_line in raw_lines:
        text = _decode_line(raw_line)
        if not text:
            continue

        if text.startswith(":"):
            comments.append(text[1:])
            continue

        field_name, separator, value = text.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]

        if field_name == "data":
            data_lines.append(value)
        elif field_name == "event":
            event_name = value
        elif field_name == "id":
            event_id = value
        elif field_name == "retry":
            retry = value
        else:
            extra_fields.append({"name": field_name, "value": value})

    if not any((comments, data_lines, extra_fields, event_name, event_id, retry)):
        return None

    event: Dict[str, Any] = {
        "data_lines": list(data_lines),
    }
    if comments:
        event["comments"] = list(comments)
    if extra_fields:
        event["extra_fields"] = list(extra_fields)
    if event_name is not None:
        event["event_name"] = event_name
    if event_id is not None:
        event["event_id"] = event_id
    if retry is not None:
        event["retry"] = retry

    raw_data = "\n".join(data_lines)
    if not data_lines:
        event["data_type"] = "none"
        event["raw_data"] = ""
        return event

    if raw_data == "[DONE]":
        event["data_type"] = "done"
        event["raw_data"] = raw_data
        return event

    try:
        payload = json.loads(raw_data)
    except ValueError:
        event["data_type"] = "text"
        event["raw_data"] = raw_data
        return event

    event["data_type"] = "json"
    event["payload"] = payload
    return event


def serialize_sse_event(event: Dict[str, Any]) -> bytes:
    lines: List[str] = []

    for comment in event.get("comments") or []:
        lines.append(":" + str(comment))

    if isinstance(event.get("event_name"), str):
        lines.append(f"event: {event['event_name']}")
    if isinstance(event.get("event_id"), str):
        lines.append(f"id: {event['event_id']}")
    if isinstance(event.get("retry"), str):
        lines.append(f"retry: {event['retry']}")

    for field in event.get("extra_fields") or []:
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        if not isinstance(name, str) or not name:
            continue
        value = field.get("value", "")
        lines.append(f"{name}: {value}")

    data_type = str(event.get("data_type") or "text")
    if data_type == "done":
        data_lines = ["[DONE]"]
    elif data_type == "json":
        encoded = json.dumps(event.get("payload"), ensure_ascii=False, separators=(",", ":"))
        data_lines = encoded.split("\n")
    elif data_type == "none":
        data_lines = []
    else:
        raw_data = str(event.get("raw_data", ""))
        data_lines = raw_data.split("\n")

    for data_line in data_lines:
        lines.append(f"data: {data_line}")

    return ("\n".join(lines) + "\n\n").encode("utf-8", errors="replace")


def iter_sse_events(raw_lines: Iterable[bytes | str]) -> Iterator[Dict[str, Any]]:
    buffered: List[bytes] = []
    for raw_line in raw_lines:
        line_bytes = _to_line_bytes(raw_line)
        line_text = _decode_line(line_bytes)
        if line_text == "":
            if buffered:
                parsed = parse_sse_event(buffered)
                if parsed is not None:
                    yield parsed
                buffered = []
            continue
        buffered.append(line_bytes)

    if buffered:
        parsed = parse_sse_event(buffered)
        if parsed is not None:
            yield parsed


def parse_sse_data_line(raw_line: bytes) -> Optional[Dict[str, Any]]:
    return parse_sse_event([raw_line])


def serialize_sse_data_line(event: Dict[str, Any]) -> bytes:
    return serialize_sse_event(event).rstrip(b"\n")
