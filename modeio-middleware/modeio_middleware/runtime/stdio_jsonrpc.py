#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict, List

from modeio_middleware.protocol.jsonpatch import apply_json_patch
from modeio_middleware.protocol.manifest import PluginManifest
from modeio_middleware.protocol.messages import (
    METHOD_INITIALIZE,
    METHOD_INVOKE,
    PROTOCOL_TO_INTERNAL_ACTION,
    PROTOCOL_ACTION_PATCH,
    to_protocol_hook_name,
)
from modeio_middleware.protocol.validator import normalize_protocol_decision_payload
from modeio_middleware.protocol.versions import PROTOCOL_VERSION, is_supported_protocol_version
from modeio_middleware.runtime.base import PluginRuntime
from modeio_middleware.runtime.supervisor import JsonRpcStdioSupervisor

DEFAULT_HOOK_TIMEOUT_MS = {
    "pre.request": 150,
    "post.response": 120,
    "post.stream.start": 120,
    "post.stream.event": 30,
    "post.stream.end": 80,
}


def _to_timeout_map(raw: Dict[str, int]) -> Dict[str, int]:
    timeouts = dict(DEFAULT_HOOK_TIMEOUT_MS)
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if not isinstance(value, int) or value <= 0:
            continue
        timeouts[key.strip()] = int(value)
    return timeouts


def _default_patch_target(hook_name: str) -> str:
    if hook_name == "pre_request":
        return "request_body"
    if hook_name == "post_response":
        return "response_body"
    if hook_name == "post_stream_event":
        return "event"
    raise ValueError(f"patch is not supported for hook '{hook_name}'")


class StdioJsonRpcRuntime(PluginRuntime):
    runtime_name = "stdio_jsonrpc"

    def __init__(
        self,
        *,
        plugin_name: str,
        command: List[str],
        manifest: PluginManifest,
        timeout_ms: Dict[str, int],
    ):
        self.plugin_name = plugin_name
        self.manifest = manifest
        self.timeout_ms = _to_timeout_map(timeout_ms)
        self._supervisor = JsonRpcStdioSupervisor(plugin_name=plugin_name, command=command)
        self._initialize()

    def _initialize(self) -> None:
        result = self._supervisor.call(
            method=METHOD_INITIALIZE,
            params={
                "protocol_version": PROTOCOL_VERSION,
                "plugin_name": self.plugin_name,
            },
            timeout_ms=500,
        )
        plugin_protocol_version = str(result.get("protocol_version") or "").strip()
        if plugin_protocol_version and not is_supported_protocol_version(plugin_protocol_version):
            raise ValueError(
                f"plugin '{self.plugin_name}' returned unsupported protocol version '{plugin_protocol_version}'"
            )

    def _resolve_timeout(self, protocol_hook_name: str) -> int:
        return int(self.timeout_ms.get(protocol_hook_name, DEFAULT_HOOK_TIMEOUT_MS.get(protocol_hook_name, 120)))

    def _to_jsonable(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {
                str(key): self._to_jsonable(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._to_jsonable(item) for item in value]
        return str(value)

    def _build_protocol_input(self, hook_input: Dict[str, Any]) -> Dict[str, Any]:
        allowed_keys = {
            "request_id",
            "endpoint_kind",
            "profile",
            "context",
            "plugin_config",
            "request_body",
            "request_headers",
            "response_body",
            "response_headers",
            "request_context",
            "response_context",
            "event",
            "plugin_state",
            "source",
            "source_event",
            "surface_capabilities",
            "native_event",
        }
        return {
            key: self._to_jsonable(value)
            for key, value in hook_input.items()
            if key in allowed_keys
        }

    def _apply_patch(self, hook_name: str, hook_input: Dict[str, Any], decision: Dict[str, Any]) -> Dict[str, Any]:
        raw_ops = decision.get("patches")
        if not isinstance(raw_ops, list):
            raise ValueError(f"plugin '{self.plugin_name}' patch action requires 'patches' array")

        target = decision.get("patch_target")
        if not isinstance(target, str) or not target.strip():
            target = _default_patch_target(hook_name)
        else:
            target = target.strip()

        if target not in {"request_body", "response_body", "event"}:
            raise ValueError(f"plugin '{self.plugin_name}' returned unsupported patch target '{target}'")

        base_value = hook_input.get(target)
        if not isinstance(base_value, dict):
            raise ValueError(f"plugin '{self.plugin_name}' patch target '{target}' must be an object")

        patched_value = apply_json_patch(base_value, raw_ops)
        normalized = dict(decision)
        normalized["action"] = "modify"
        normalized[target] = patched_value
        return normalized

    def invoke(self, hook_name: str, hook_input: Dict[str, Any]) -> Any:
        protocol_hook_name = to_protocol_hook_name(hook_name)
        protocol_input = self._build_protocol_input(hook_input)
        result = self._supervisor.call(
            method=METHOD_INVOKE,
            params={
                "hook": protocol_hook_name,
                "input": protocol_input,
            },
            timeout_ms=self._resolve_timeout(protocol_hook_name),
        )

        decision = normalize_protocol_decision_payload(result)
        action = decision.get("action")
        if action in PROTOCOL_TO_INTERNAL_ACTION:
            mapped = dict(decision)
            mapped["action"] = PROTOCOL_TO_INTERNAL_ACTION[action]
            decision = mapped

        if decision.get("action") == "modify" and action == PROTOCOL_ACTION_PATCH:
            decision = self._apply_patch(hook_name, hook_input, decision)

        return decision

    def shutdown(self) -> None:
        self._supervisor.shutdown()
