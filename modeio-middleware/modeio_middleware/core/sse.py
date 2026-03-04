#!/usr/bin/env python3

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def parse_sse_data_line(raw_line: bytes) -> Optional[Dict[str, Any]]:
    """Parse a single SSE data line into structured event payload.

    Returns None for non-data lines.
    """
    try:
        text = raw_line.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_line.decode("utf-8", errors="replace")

    text = text.rstrip("\r")
    if not text.startswith("data:"):
        return None

    raw_data = text.split(":", 1)[1].lstrip()
    if raw_data == "[DONE]":
        return {
            "line_type": "data",
            "data_type": "done",
            "raw_data": raw_data,
        }

    try:
        payload = json.loads(raw_data)
    except ValueError:
        return {
            "line_type": "data",
            "data_type": "text",
            "raw_data": raw_data,
        }

    return {
        "line_type": "data",
        "data_type": "json",
        "payload": payload,
    }


def serialize_sse_data_line(event: Dict[str, Any]) -> bytes:
    data_type = event.get("data_type")
    if data_type == "done":
        return b"data: [DONE]"
    if data_type == "json":
        payload = event.get("payload")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return b"data: " + encoded
    raw_data = str(event.get("raw_data", ""))
    return b"data: " + raw_data.encode("utf-8", errors="replace")
