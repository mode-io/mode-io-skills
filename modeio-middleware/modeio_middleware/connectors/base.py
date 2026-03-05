#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ConnectorEvent:
    source: str
    source_event: str
    endpoint_kind: str
    phase: str
    profile: str
    on_plugin_error: Optional[str]
    plugin_overrides: Dict[str, Dict[str, Any]]
    request_body: Dict[str, Any]
    response_body: Dict[str, Any]
    connector_context: Dict[str, Any]
    connector_capabilities: Dict[str, bool]
