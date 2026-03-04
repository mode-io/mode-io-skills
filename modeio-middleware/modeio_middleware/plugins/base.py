#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict


class MiddlewarePlugin:
    name = "base"
    version = "0.1.0"

    def pre_request(self, _hook_input: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": "allow"}

    def post_response(self, _hook_input: Dict[str, Any]) -> Dict[str, Any]:
        return {"action": "allow"}
