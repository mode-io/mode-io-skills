#!/usr/bin/env python3

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class ConnectorCapabilities:
    can_patch: bool = True
    can_block: bool = True

    def as_dict(self) -> Dict[str, bool]:
        return {
            "can_patch": self.can_patch,
            "can_block": self.can_block,
        }


@dataclass(frozen=True)
class CanonicalInvocation:
    source: str
    source_event: str
    endpoint_kind: str
    phase: str
    request_id: str
    profile: str
    on_plugin_error: Optional[str]
    plugin_overrides: Dict[str, Dict[str, Any]]
    incoming_headers: Dict[str, str]
    request_body: Dict[str, Any] = field(default_factory=dict)
    response_body: Dict[str, Any] = field(default_factory=dict)
    connector_context: Dict[str, Any] = field(default_factory=dict)
    connector_capabilities: ConnectorCapabilities = field(default_factory=ConnectorCapabilities)
    stream: bool = False


class ConnectorAdapter(ABC):
    route_paths: Tuple[str, ...] = ()

    def matches(self, path: str) -> bool:
        return path in self.route_paths

    @abstractmethod
    def parse(
        self,
        *,
        request_id: str,
        payload: Dict[str, Any],
        incoming_headers: Dict[str, str],
        default_profile: str,
        path: str,
    ) -> CanonicalInvocation:
        raise NotImplementedError
