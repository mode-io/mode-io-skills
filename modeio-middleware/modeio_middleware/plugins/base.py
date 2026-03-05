#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict

from modeio_middleware.core.decision import HookDecision


class MiddlewarePlugin:
    name = "base"
    version = "0.1.0"

    def pre_request(self, _hook_input: Dict[str, Any]) -> Dict[str, Any] | HookDecision:
        return HookDecision(action="allow")

    def post_response(self, _hook_input: Dict[str, Any]) -> Dict[str, Any] | HookDecision:
        return HookDecision(action="allow")

    def post_stream_start(self, _hook_input: Dict[str, Any]) -> Dict[str, Any] | HookDecision:
        return HookDecision(action="allow")

    def post_stream_event(self, hook_input: Dict[str, Any]) -> Dict[str, Any] | HookDecision:
        return HookDecision(action="allow", event=hook_input.get("event"))

    def post_stream_end(self, _hook_input: Dict[str, Any]) -> Dict[str, Any] | HookDecision:
        return HookDecision(action="allow")
