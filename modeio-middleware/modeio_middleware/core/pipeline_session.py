#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class PipelineSession:
    request_id: str
    profile: str
    upstream_called: bool = False
    pre_actions: List[str] = field(default_factory=list)
    post_actions: List[str] = field(default_factory=list)
    degraded: List[str] = field(default_factory=list)
    active_plugins: List[Any] = field(default_factory=list)
    plugins_released: bool = False
