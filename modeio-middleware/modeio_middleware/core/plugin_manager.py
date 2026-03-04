#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from modeio_middleware.core.contracts import (
    HOOK_ACTION_ALLOW,
    HOOK_ACTION_BLOCK,
    HOOK_ACTION_MODIFY,
    HOOK_ACTION_WARN,
    VALID_HOOK_ACTIONS,
)
from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.plugins.base import MiddlewarePlugin


@dataclass(frozen=True)
class ActivePlugin:
    name: str
    instance: MiddlewarePlugin
    config: Dict[str, Any]


@dataclass
class HookPipelineResult:
    body: Dict[str, Any]
    headers: Dict[str, str]
    actions: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    degraded: List[str] = field(default_factory=list)
    blocked: bool = False
    block_message: str = ""


@dataclass
class StreamEventPipelineResult:
    event: Dict[str, Any]
    actions: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    degraded: List[str] = field(default_factory=list)
    blocked: bool = False
    block_message: str = ""


def _coerce_findings(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("field 'findings' must be an array")
    findings: List[Dict[str, Any]] = []
    for finding in raw:
        if isinstance(finding, dict):
            findings.append(finding)
    return findings


def _normalize_header_map(raw: Dict[str, Any]) -> Dict[str, str]:
    normalized_headers: Dict[str, str] = {}
    for key, value in raw.items():
        normalized_headers[str(key)] = str(value)
    return normalized_headers


class PluginManager:
    def __init__(self, plugins_config: Dict[str, Any]):
        if not isinstance(plugins_config, dict):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                "plugins config must be an object",
            )
        self._plugins_config = plugins_config

    def _instantiate_plugin(self, name: str, module_path: str) -> MiddlewarePlugin:
        try:
            module = importlib.import_module(module_path)
        except Exception as error:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"failed to import plugin '{name}' module '{module_path}'",
                details={"plugin": name, "module": module_path},
            ) from error

        plugin_cls = getattr(module, "Plugin", None)
        if plugin_cls is None:
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"plugin '{name}' module '{module_path}' missing Plugin class",
                details={"plugin": name, "module": module_path},
            )

        plugin = plugin_cls()
        if not isinstance(plugin, MiddlewarePlugin):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                f"plugin '{name}' must inherit MiddlewarePlugin",
                details={"plugin": name, "module": module_path},
            )
        return plugin

    def resolve_active_plugins(
        self,
        plugin_order: Iterable[str],
        plugin_overrides: Dict[str, Dict[str, Any]],
    ) -> List[ActivePlugin]:
        active: List[ActivePlugin] = []
        for plugin_name in plugin_order:
            plugin_config = self._plugins_config.get(plugin_name)
            if not isinstance(plugin_config, dict):
                raise MiddlewareError(
                    500,
                    "MODEIO_CONFIG_ERROR",
                    f"plugin '{plugin_name}' config is missing or invalid",
                )

            module_path = plugin_config.get("module")
            if not isinstance(module_path, str) or not module_path.strip():
                raise MiddlewareError(
                    500,
                    "MODEIO_CONFIG_ERROR",
                    f"plugin '{plugin_name}' module path is missing",
                )

            override = plugin_overrides.get(plugin_name, {})
            if not isinstance(override, dict):
                raise MiddlewareError(
                    400,
                    "MODEIO_VALIDATION_ERROR",
                    f"modeio.plugins.{plugin_name} must be an object",
                )

            enabled = bool(plugin_config.get("enabled", False))
            if "enabled" in override:
                enabled = bool(override["enabled"])

            merged_config: Dict[str, Any] = {
                key: value
                for key, value in plugin_config.items()
                if key not in {"enabled", "module"}
            }
            merged_config.update(
                {
                    key: value
                    for key, value in override.items()
                    if key != "enabled"
                }
            )

            if not enabled:
                continue

            plugin = self._instantiate_plugin(plugin_name, module_path)
            active.append(ActivePlugin(name=plugin_name, instance=plugin, config=merged_config))
        return active

    def _normalize_hook_result(self, plugin_name: str, payload: Any) -> Dict[str, Any]:
        if payload is None:
            return {"action": HOOK_ACTION_ALLOW, "findings": []}
        if not isinstance(payload, dict):
            raise ValueError("plugin hook result must be an object")

        action = str(payload.get("action", HOOK_ACTION_ALLOW)).strip().lower()
        if action not in VALID_HOOK_ACTIONS:
            raise ValueError(f"unsupported plugin action '{action}'")

        message = payload.get("message")
        if message is not None and not isinstance(message, str):
            raise ValueError("field 'message' must be a string")

        normalized: Dict[str, Any] = {
            "action": action,
            "findings": _coerce_findings(payload.get("findings")),
            "message": message,
        }

        if "request_body" in payload:
            normalized["request_body"] = payload["request_body"]
        if "request_headers" in payload:
            normalized["request_headers"] = payload["request_headers"]
        if "response_body" in payload:
            normalized["response_body"] = payload["response_body"]
        if "response_headers" in payload:
            normalized["response_headers"] = payload["response_headers"]

        return normalized

    def _normalize_stream_hook_result(self, payload: Any) -> Dict[str, Any]:
        if payload is None:
            return {"action": HOOK_ACTION_ALLOW, "findings": []}
        if not isinstance(payload, dict):
            raise ValueError("plugin stream hook result must be an object")

        action = str(payload.get("action", HOOK_ACTION_ALLOW)).strip().lower()
        if action not in VALID_HOOK_ACTIONS:
            raise ValueError(f"unsupported plugin action '{action}'")

        message = payload.get("message")
        if message is not None and not isinstance(message, str):
            raise ValueError("field 'message' must be a string")

        normalized: Dict[str, Any] = {
            "action": action,
            "findings": _coerce_findings(payload.get("findings")),
            "message": message,
        }

        if "event" in payload:
            normalized["event"] = payload["event"]

        return normalized

    def _handle_plugin_error(
        self,
        *,
        plugin_name: str,
        error: Exception,
        on_plugin_error: str,
        result: Any,
    ) -> None:
        reason = f"plugin_error:{plugin_name}"
        result.degraded.append(reason)
        result.actions.append(f"{plugin_name}:error")

        if on_plugin_error == "fail_safe":
            result.blocked = True
            result.block_message = f"plugin '{plugin_name}' failed: {type(error).__name__}"
            return

        severity = "medium" if on_plugin_error == "warn" else "low"
        result.findings.append(
            {
                "class": "plugin_error",
                "severity": severity,
                "confidence": 1.0,
                "reason": f"plugin '{plugin_name}' failed",
                "evidence": [type(error).__name__],
            }
        )

    def _apply_stream_lifecycle_hook(
        self,
        active_plugins: Iterable[ActivePlugin],
        *,
        request_id: str,
        endpoint_kind: str,
        profile: str,
        request_context: Dict[str, Any],
        response_context: Optional[Dict[str, Any]],
        shared_state: Dict[str, Any],
        on_plugin_error: str,
        hook_name: str,
        blocked_message_suffix: str,
    ) -> HookPipelineResult:
        result = HookPipelineResult(body={}, headers={})

        for active in reversed(list(active_plugins)):
            plugin_state = shared_state.setdefault(active.name, {})
            hook_input = {
                "request_id": request_id,
                "endpoint_kind": endpoint_kind,
                "profile": profile,
                "request_context": request_context,
                "plugin_config": active.config,
                "state": shared_state,
                "plugin_state": plugin_state,
            }
            if response_context is not None:
                hook_input["response_context"] = response_context

            try:
                payload = getattr(active.instance, hook_name)(hook_input)
                normalized = self._normalize_stream_hook_result(payload)
            except Exception as error:
                self._handle_plugin_error(
                    plugin_name=active.name,
                    error=error,
                    on_plugin_error=on_plugin_error,
                    result=result,
                )
                if result.blocked:
                    return result
                continue

            action = normalized["action"]
            result.actions.append(f"{active.name}:{action}")
            result.findings.extend(normalized["findings"])

            if action == HOOK_ACTION_BLOCK:
                result.blocked = True
                result.block_message = normalized.get("message") or f"plugin '{active.name}' blocked {blocked_message_suffix}"
                return result

        return result

    def apply_pre_request(
        self,
        active_plugins: Iterable[ActivePlugin],
        *,
        request_id: str,
        endpoint_kind: str,
        profile: str,
        request_body: Dict[str, Any],
        request_headers: Dict[str, str],
        context: Dict[str, Any],
        shared_state: Dict[str, Any],
        on_plugin_error: str,
    ) -> HookPipelineResult:
        result = HookPipelineResult(body=copy.deepcopy(request_body), headers=dict(request_headers))

        for active in active_plugins:
            plugin_state = shared_state.setdefault(active.name, {})
            hook_input = {
                "request_id": request_id,
                "endpoint_kind": endpoint_kind,
                "profile": profile,
                "request_body": result.body,
                "request_headers": result.headers,
                "context": context,
                "plugin_config": active.config,
                "state": shared_state,
                "plugin_state": plugin_state,
            }

            try:
                payload = active.instance.pre_request(hook_input)
                normalized = self._normalize_hook_result(active.name, payload)
            except Exception as error:
                self._handle_plugin_error(
                    plugin_name=active.name,
                    error=error,
                    on_plugin_error=on_plugin_error,
                    result=result,
                )
                if result.blocked:
                    return result
                continue

            action = normalized["action"]
            result.actions.append(f"{active.name}:{action}")
            result.findings.extend(normalized["findings"])

            if action == HOOK_ACTION_MODIFY:
                if "request_body" in normalized:
                    if not isinstance(normalized["request_body"], dict):
                        raise MiddlewareError(
                            500,
                            "MODEIO_PLUGIN_ERROR",
                            f"plugin '{active.name}' returned invalid request_body",
                        )
                    result.body = normalized["request_body"]

                if "request_headers" in normalized:
                    if not isinstance(normalized["request_headers"], dict):
                        raise MiddlewareError(
                            500,
                            "MODEIO_PLUGIN_ERROR",
                            f"plugin '{active.name}' returned invalid request_headers",
                        )
                    result.headers.update(_normalize_header_map(normalized["request_headers"]))

            if action == HOOK_ACTION_BLOCK:
                result.blocked = True
                result.block_message = normalized.get("message") or f"plugin '{active.name}' blocked request"
                return result

        return result

    def apply_post_response(
        self,
        active_plugins: Iterable[ActivePlugin],
        *,
        request_id: str,
        endpoint_kind: str,
        profile: str,
        request_context: Dict[str, Any],
        response_body: Dict[str, Any],
        response_headers: Dict[str, str],
        shared_state: Dict[str, Any],
        on_plugin_error: str,
    ) -> HookPipelineResult:
        result = HookPipelineResult(body=copy.deepcopy(response_body), headers=dict(response_headers))

        for active in reversed(list(active_plugins)):
            plugin_state = shared_state.setdefault(active.name, {})
            hook_input = {
                "request_id": request_id,
                "endpoint_kind": endpoint_kind,
                "profile": profile,
                "request_context": request_context,
                "response_body": result.body,
                "response_headers": result.headers,
                "plugin_config": active.config,
                "state": shared_state,
                "plugin_state": plugin_state,
            }

            try:
                payload = active.instance.post_response(hook_input)
                normalized = self._normalize_hook_result(active.name, payload)
            except Exception as error:
                self._handle_plugin_error(
                    plugin_name=active.name,
                    error=error,
                    on_plugin_error=on_plugin_error,
                    result=result,
                )
                if result.blocked:
                    return result
                continue

            action = normalized["action"]
            result.actions.append(f"{active.name}:{action}")
            result.findings.extend(normalized["findings"])

            if action == HOOK_ACTION_MODIFY:
                if "response_body" in normalized:
                    if not isinstance(normalized["response_body"], dict):
                        raise MiddlewareError(
                            500,
                            "MODEIO_PLUGIN_ERROR",
                            f"plugin '{active.name}' returned invalid response_body",
                        )
                    result.body = normalized["response_body"]

                if "response_headers" in normalized:
                    if not isinstance(normalized["response_headers"], dict):
                        raise MiddlewareError(
                            500,
                            "MODEIO_PLUGIN_ERROR",
                            f"plugin '{active.name}' returned invalid response_headers",
                        )
                    result.headers.update(_normalize_header_map(normalized["response_headers"]))

            if action == HOOK_ACTION_BLOCK:
                result.blocked = True
                result.block_message = normalized.get("message") or f"plugin '{active.name}' blocked response"
                return result

        return result

    def apply_post_stream_start(
        self,
        active_plugins: Iterable[ActivePlugin],
        *,
        request_id: str,
        endpoint_kind: str,
        profile: str,
        request_context: Dict[str, Any],
        response_context: Dict[str, Any],
        shared_state: Dict[str, Any],
        on_plugin_error: str,
    ) -> HookPipelineResult:
        return self._apply_stream_lifecycle_hook(
            active_plugins,
            request_id=request_id,
            endpoint_kind=endpoint_kind,
            profile=profile,
            request_context=request_context,
            response_context=response_context,
            shared_state=shared_state,
            on_plugin_error=on_plugin_error,
            hook_name="post_stream_start",
            blocked_message_suffix="stream",
        )

    def apply_post_stream_event(
        self,
        active_plugins: Iterable[ActivePlugin],
        *,
        request_id: str,
        endpoint_kind: str,
        profile: str,
        request_context: Dict[str, Any],
        event: Dict[str, Any],
        shared_state: Dict[str, Any],
        on_plugin_error: str,
    ) -> StreamEventPipelineResult:
        result = StreamEventPipelineResult(event=copy.deepcopy(event))

        for active in reversed(list(active_plugins)):
            plugin_state = shared_state.setdefault(active.name, {})
            hook_input = {
                "request_id": request_id,
                "endpoint_kind": endpoint_kind,
                "profile": profile,
                "request_context": request_context,
                "event": result.event,
                "plugin_config": active.config,
                "state": shared_state,
                "plugin_state": plugin_state,
            }

            try:
                payload = active.instance.post_stream_event(hook_input)
                normalized = self._normalize_stream_hook_result(payload)
            except Exception as error:
                self._handle_plugin_error(
                    plugin_name=active.name,
                    error=error,
                    on_plugin_error=on_plugin_error,
                    result=result,
                )
                if result.blocked:
                    return result
                continue

            action = normalized["action"]
            result.actions.append(f"{active.name}:{action}")
            result.findings.extend(normalized["findings"])

            if action == HOOK_ACTION_MODIFY and "event" in normalized:
                if not isinstance(normalized["event"], dict):
                    raise MiddlewareError(
                        500,
                        "MODEIO_PLUGIN_ERROR",
                        f"plugin '{active.name}' returned invalid stream event",
                    )
                result.event = normalized["event"]

            if action == HOOK_ACTION_BLOCK:
                result.blocked = True
                result.block_message = normalized.get("message") or f"plugin '{active.name}' blocked stream event"
                return result

        return result

    def apply_post_stream_end(
        self,
        active_plugins: Iterable[ActivePlugin],
        *,
        request_id: str,
        endpoint_kind: str,
        profile: str,
        request_context: Dict[str, Any],
        shared_state: Dict[str, Any],
        on_plugin_error: str,
    ) -> HookPipelineResult:
        return self._apply_stream_lifecycle_hook(
            active_plugins,
            request_id=request_id,
            endpoint_kind=endpoint_kind,
            profile=profile,
            request_context=request_context,
            response_context=None,
            shared_state=shared_state,
            on_plugin_error=on_plugin_error,
            hook_name="post_stream_end",
            blocked_message_suffix="stream end",
        )
