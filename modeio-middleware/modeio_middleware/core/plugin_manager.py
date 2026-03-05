#!/usr/bin/env python3

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from modeio_middleware.core.config_resolver import resolve_plugin_runtime_config
from modeio_middleware.core.contracts import (
    HOOK_ACTION_BLOCK,
    HOOK_ACTION_DEFER,
    HOOK_ACTION_MODIFY,
    HOOK_ACTION_WARN,
)
from modeio_middleware.core.decision import normalize_decision_payload
from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.registry.loader import create_plugin_runtime
from modeio_middleware.registry.resolver import (
    MODE_ASSIST,
    MODE_OBSERVE,
    resolve_plugin_runtime_spec,
)
from modeio_middleware.runtime.base import PluginRuntime


@dataclass(frozen=True)
class ActivePlugin:
    name: str
    runtime: PluginRuntime
    config: Dict[str, Any]
    mode: str
    capabilities: Dict[str, bool]
    supported_hooks: List[str]


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


def _normalize_header_map(raw: Dict[str, Any]) -> Dict[str, str]:
    normalized_headers: Dict[str, str] = {}
    for key, value in raw.items():
        normalized_headers[str(key)] = str(value)
    return normalized_headers


class PluginManager:
    def __init__(
        self,
        plugins_config: Dict[str, Any],
        preset_registry: Optional[Dict[str, Any]] = None,
        config_base_dir: Optional[str] = None,
    ):
        if not isinstance(plugins_config, dict):
            raise MiddlewareError(
                500,
                "MODEIO_CONFIG_ERROR",
                "plugins config must be an object",
            )
        self._plugins_config = plugins_config
        self._preset_registry = preset_registry or {}
        if isinstance(config_base_dir, str) and config_base_dir.strip():
            self._config_base_dir = Path(config_base_dir.strip())
        else:
            self._config_base_dir = Path.cwd()

    def resolve_active_plugins(
        self,
        plugin_order: Iterable[str],
        request_plugin_overrides: Dict[str, Dict[str, Any]],
        profile_plugin_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[ActivePlugin]:
        profile_overrides = profile_plugin_overrides or {}
        active: List[ActivePlugin] = []
        for plugin_name in plugin_order:
            plugin_config = self._plugins_config.get(plugin_name)
            request_override = request_plugin_overrides.get(plugin_name, {})
            if not isinstance(request_override, dict):
                raise MiddlewareError(
                    400,
                    "MODEIO_VALIDATION_ERROR",
                    f"modeio.plugins.{plugin_name} must be an object",
                )

            profile_override = profile_overrides.get(plugin_name, {})
            if not isinstance(profile_override, dict):
                raise MiddlewareError(
                    500,
                    "MODEIO_CONFIG_ERROR",
                    f"profile.plugin_overrides.{plugin_name} must be an object",
                    retryable=False,
                )

            resolved = resolve_plugin_runtime_config(
                plugin_name=plugin_name,
                plugin_config=plugin_config,
                preset_registry=self._preset_registry,
                profile_override=profile_override,
                request_override=request_override,
            )

            if not resolved.enabled:
                continue

            spec = resolve_plugin_runtime_spec(
                resolved=resolved,
                config_base_dir=self._config_base_dir,
            )
            runtime = create_plugin_runtime(spec)
            active.append(
                ActivePlugin(
                    name=plugin_name,
                    runtime=runtime,
                    config=spec.hook_config,
                    mode=spec.mode,
                    capabilities=spec.capabilities,
                    supported_hooks=spec.supported_hooks,
                )
            )
        return active

    def shutdown_active_plugins(self, active_plugins: Iterable[ActivePlugin]) -> None:
        for active in reversed(list(active_plugins)):
            try:
                active.runtime.shutdown()
            except Exception:
                continue

    def _apply_action_controls(
        self,
        *,
        active: ActivePlugin,
        action: str,
        result: Any,
        connector_capabilities: Optional[Dict[str, bool]],
    ) -> str:
        original_action = action
        effective_action = action

        can_patch = bool(active.capabilities.get("can_patch", False))
        can_block = bool(active.capabilities.get("can_block", False))
        can_defer = bool(active.capabilities.get("can_defer", False))

        if effective_action == HOOK_ACTION_MODIFY and not can_patch:
            effective_action = HOOK_ACTION_WARN
        elif effective_action == HOOK_ACTION_BLOCK and not can_block:
            effective_action = HOOK_ACTION_WARN
        elif effective_action == HOOK_ACTION_DEFER and not can_defer:
            effective_action = HOOK_ACTION_WARN

        if isinstance(connector_capabilities, dict):
            connector_can_patch = bool(connector_capabilities.get("can_patch", True))
            connector_can_block = bool(connector_capabilities.get("can_block", True))
            connector_can_defer = bool(connector_capabilities.get("can_defer", True))

            if effective_action == HOOK_ACTION_MODIFY and not connector_can_patch:
                effective_action = HOOK_ACTION_WARN
            elif effective_action == HOOK_ACTION_BLOCK and not connector_can_block:
                effective_action = HOOK_ACTION_WARN
            elif effective_action == HOOK_ACTION_DEFER and not connector_can_defer:
                effective_action = HOOK_ACTION_WARN

        if active.mode == MODE_OBSERVE and effective_action in {
            HOOK_ACTION_MODIFY,
            HOOK_ACTION_BLOCK,
            HOOK_ACTION_DEFER,
        }:
            effective_action = HOOK_ACTION_WARN
        elif active.mode == MODE_ASSIST and effective_action == HOOK_ACTION_BLOCK:
            effective_action = HOOK_ACTION_WARN

        if effective_action != original_action:
            result.degraded.append(
                f"action_downgraded:{active.name}:{original_action}->{effective_action}:{active.mode}"
            )

        return effective_action

    def _normalize_hook_result(self, plugin_name: str, payload: Any) -> Dict[str, Any]:
        _ = plugin_name
        return normalize_decision_payload(payload, stream=False)

    def _normalize_stream_hook_result(self, payload: Any) -> Dict[str, Any]:
        return normalize_decision_payload(payload, stream=True)

    def _record_telemetry(
        self,
        services: Optional[Dict[str, Any]],
        *,
        plugin_name: str,
        hook_name: str,
        action: str,
        duration_ms: float,
        errored: bool,
    ) -> None:
        if not isinstance(services, dict):
            return
        telemetry = services.get("telemetry")
        if telemetry is None:
            return

        record = getattr(telemetry, "record", None)
        if not callable(record):
            return

        record(
            plugin_name=plugin_name,
            hook_name=hook_name,
            action=action,
            duration_ms=duration_ms,
            errored=errored,
        )

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
        services: Optional[Dict[str, Any]],
        hook_name: str,
        blocked_message_suffix: str,
        connector_capabilities: Optional[Dict[str, bool]],
    ) -> HookPipelineResult:
        result = HookPipelineResult(body={}, headers={})

        for active in reversed(list(active_plugins)):
            if hook_name not in active.supported_hooks:
                continue
            plugin_state = shared_state.setdefault(active.name, {})
            hook_input = {
                "request_id": request_id,
                "endpoint_kind": endpoint_kind,
                "profile": profile,
                "request_context": request_context,
                "plugin_config": active.config,
                "state": shared_state,
                "plugin_state": plugin_state,
                "services": services or {},
            }
            if response_context is not None:
                hook_input["response_context"] = response_context

            start = time.perf_counter()
            try:
                payload = active.runtime.invoke(hook_name, hook_input)
                normalized = self._normalize_stream_hook_result(payload)
            except Exception as error:
                duration_ms = (time.perf_counter() - start) * 1000
                self._record_telemetry(
                    services,
                    plugin_name=active.name,
                    hook_name=hook_name,
                    action="error",
                    duration_ms=duration_ms,
                    errored=True,
                )
                self._handle_plugin_error(
                    plugin_name=active.name,
                    error=error,
                    on_plugin_error=on_plugin_error,
                    result=result,
                )
                if result.blocked:
                    return result
                continue

            action = self._apply_action_controls(
                active=active,
                action=normalized["action"],
                result=result,
                connector_capabilities=connector_capabilities,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            self._record_telemetry(
                services,
                plugin_name=active.name,
                hook_name=hook_name,
                action=action,
                duration_ms=duration_ms,
                errored=False,
            )
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
        services: Optional[Dict[str, Any]] = None,
        connector_capabilities: Optional[Dict[str, bool]] = None,
    ) -> HookPipelineResult:
        result = HookPipelineResult(body=copy.deepcopy(request_body), headers=dict(request_headers))

        for active in active_plugins:
            if "pre_request" not in active.supported_hooks:
                continue
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
                "services": services or {},
            }

            start = time.perf_counter()
            try:
                payload = active.runtime.invoke("pre_request", hook_input)
                normalized = self._normalize_hook_result(active.name, payload)
            except Exception as error:
                duration_ms = (time.perf_counter() - start) * 1000
                self._record_telemetry(
                    services,
                    plugin_name=active.name,
                    hook_name="pre_request",
                    action="error",
                    duration_ms=duration_ms,
                    errored=True,
                )
                self._handle_plugin_error(
                    plugin_name=active.name,
                    error=error,
                    on_plugin_error=on_plugin_error,
                    result=result,
                )
                if result.blocked:
                    return result
                continue

            action = self._apply_action_controls(
                active=active,
                action=normalized["action"],
                result=result,
                connector_capabilities=connector_capabilities,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            self._record_telemetry(
                services,
                plugin_name=active.name,
                hook_name="pre_request",
                action=action,
                duration_ms=duration_ms,
                errored=False,
            )
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
        services: Optional[Dict[str, Any]] = None,
        connector_capabilities: Optional[Dict[str, bool]] = None,
    ) -> HookPipelineResult:
        result = HookPipelineResult(body=copy.deepcopy(response_body), headers=dict(response_headers))

        for active in reversed(list(active_plugins)):
            if "post_response" not in active.supported_hooks:
                continue
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
                "services": services or {},
            }

            start = time.perf_counter()
            try:
                payload = active.runtime.invoke("post_response", hook_input)
                normalized = self._normalize_hook_result(active.name, payload)
            except Exception as error:
                duration_ms = (time.perf_counter() - start) * 1000
                self._record_telemetry(
                    services,
                    plugin_name=active.name,
                    hook_name="post_response",
                    action="error",
                    duration_ms=duration_ms,
                    errored=True,
                )
                self._handle_plugin_error(
                    plugin_name=active.name,
                    error=error,
                    on_plugin_error=on_plugin_error,
                    result=result,
                )
                if result.blocked:
                    return result
                continue

            action = self._apply_action_controls(
                active=active,
                action=normalized["action"],
                result=result,
                connector_capabilities=connector_capabilities,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            self._record_telemetry(
                services,
                plugin_name=active.name,
                hook_name="post_response",
                action=action,
                duration_ms=duration_ms,
                errored=False,
            )
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
        services: Optional[Dict[str, Any]] = None,
        connector_capabilities: Optional[Dict[str, bool]] = None,
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
            services=services,
            hook_name="post_stream_start",
            blocked_message_suffix="stream",
            connector_capabilities=connector_capabilities,
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
        services: Optional[Dict[str, Any]] = None,
        connector_capabilities: Optional[Dict[str, bool]] = None,
    ) -> StreamEventPipelineResult:
        result = StreamEventPipelineResult(event=copy.deepcopy(event))

        for active in reversed(list(active_plugins)):
            if "post_stream_event" not in active.supported_hooks:
                continue
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
                "services": services or {},
            }

            start = time.perf_counter()
            try:
                payload = active.runtime.invoke("post_stream_event", hook_input)
                normalized = self._normalize_stream_hook_result(payload)
            except Exception as error:
                duration_ms = (time.perf_counter() - start) * 1000
                self._record_telemetry(
                    services,
                    plugin_name=active.name,
                    hook_name="post_stream_event",
                    action="error",
                    duration_ms=duration_ms,
                    errored=True,
                )
                self._handle_plugin_error(
                    plugin_name=active.name,
                    error=error,
                    on_plugin_error=on_plugin_error,
                    result=result,
                )
                if result.blocked:
                    return result
                continue

            action = self._apply_action_controls(
                active=active,
                action=normalized["action"],
                result=result,
                connector_capabilities=connector_capabilities,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            self._record_telemetry(
                services,
                plugin_name=active.name,
                hook_name="post_stream_event",
                action=action,
                duration_ms=duration_ms,
                errored=False,
            )
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
        services: Optional[Dict[str, Any]] = None,
        connector_capabilities: Optional[Dict[str, bool]] = None,
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
            services=services,
            hook_name="post_stream_end",
            blocked_message_suffix="stream end",
            connector_capabilities=connector_capabilities,
        )
