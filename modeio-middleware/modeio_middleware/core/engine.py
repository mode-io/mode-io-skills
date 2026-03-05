#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Union

from modeio_middleware.core.contracts import (
    normalize_modeio_options,
    validate_endpoint_payload,
)
from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.core.http_contract import contract_headers, error_payload
from modeio_middleware.core.plugin_manager import ActivePlugin, PluginManager
from modeio_middleware.core.profiles import (
    DEFAULT_PROFILE,
    normalize_profile_name,
    resolve_plugin_error_policy,
    resolve_profile_plugin_overrides,
    resolve_profile,
    resolve_profile_plugins,
)
from modeio_middleware.core.services.defer_queue import DeferredActionQueue
from modeio_middleware.core.services.telemetry import PluginTelemetry
from modeio_middleware.core.stream_relay import iter_transformed_sse_stream
from modeio_middleware.core.upstream_client import forward_upstream_json, forward_upstream_stream


@dataclass(frozen=True)
class GatewayRuntimeConfig:
    upstream_chat_completions_url: str
    upstream_responses_url: str
    upstream_timeout_seconds: int
    upstream_api_key_env: str
    default_profile: str = DEFAULT_PROFILE
    profiles: Dict[str, Any] = None  # type: ignore[assignment]
    plugins: Dict[str, Any] = None  # type: ignore[assignment]
    preset_registry: Dict[str, Any] = None  # type: ignore[assignment]
    service_config: Dict[str, Any] = None  # type: ignore[assignment]


@dataclass
class ProcessResult:
    status: int
    payload: Dict[str, Any]
    headers: Dict[str, str]


@dataclass
class StreamProcessResult:
    status: int
    headers: Dict[str, str]
    stream: Optional[Iterable[bytes]] = None
    payload: Optional[Dict[str, Any]] = None


def _build_runtime_services(service_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = service_config if isinstance(service_config, dict) else {}

    defer_cfg = cfg.get("defer_queue", {})
    defer_path: Optional[str] = None
    if isinstance(defer_cfg, dict):
        candidate = defer_cfg.get("path")
        if isinstance(candidate, str) and candidate.strip():
            defer_path = candidate.strip()

    return {
        "defer_queue": DeferredActionQueue(path=defer_path),
        "telemetry": PluginTelemetry(),
    }


class MiddlewareEngine:
    def __init__(self, runtime_config: GatewayRuntimeConfig):
        self.config = runtime_config
        self.plugin_manager = PluginManager(
            runtime_config.plugins or {},
            preset_registry=runtime_config.preset_registry or {},
        )
        self.services = _build_runtime_services(runtime_config.service_config)

    def _resolve_plugin_runtime(
        self,
        *,
        profile: str,
        on_plugin_error_override: Optional[str],
        plugin_overrides: Dict[str, Dict[str, Any]],
    ) -> tuple[str, List[ActivePlugin]]:
        profile_config = resolve_profile(self.config.profiles or {}, profile)
        on_plugin_error = resolve_plugin_error_policy(profile_config, on_plugin_error_override)
        plugin_order = resolve_profile_plugins(profile_config)
        profile_overrides = resolve_profile_plugin_overrides(profile_config)
        active_plugins = self.plugin_manager.resolve_active_plugins(
            plugin_order,
            request_plugin_overrides=plugin_overrides,
            profile_plugin_overrides=profile_overrides,
        )
        return on_plugin_error, active_plugins

    def _error_process_result(
        self,
        *,
        request_id: str,
        profile: str,
        pre_actions: List[str],
        post_actions: List[str],
        degraded: List[str],
        upstream_called: bool,
        error: MiddlewareError,
    ) -> ProcessResult:
        payload = error_payload(
            request_id,
            error.code,
            error.message,
            retryable=error.retryable,
            details=error.details,
        )
        headers = contract_headers(
            request_id,
            profile=profile,
            pre_actions=pre_actions,
            post_actions=post_actions,
            degraded=degraded,
            upstream_called=upstream_called,
        )
        return ProcessResult(status=error.status, payload=payload, headers=headers)

    def process_request(
        self,
        *,
        endpoint_kind: str,
        request_id: str,
        request_body: Dict[str, Any],
        incoming_headers: Dict[str, str],
    ) -> Union[ProcessResult, StreamProcessResult]:
        upstream_called = False
        pre_actions: List[str] = []
        post_actions: List[str] = []
        degraded: List[str] = []
        profile = self.config.default_profile

        try:
            stream_enabled = validate_endpoint_payload(endpoint_kind, request_body)

            options = normalize_modeio_options(
                request_body,
                default_profile=self.config.default_profile,
            )
            profile = normalize_profile_name(options.profile, default_profile=self.config.default_profile)

            on_plugin_error, active_plugins = self._resolve_plugin_runtime(
                profile=profile,
                on_plugin_error_override=options.on_plugin_error,
                plugin_overrides=options.plugin_overrides,
            )

            shared_state: Dict[str, Any] = {}
            request_context = {
                "endpoint_kind": endpoint_kind,
                "upstream_chat_completions_url": self.config.upstream_chat_completions_url,
                "upstream_responses_url": self.config.upstream_responses_url,
                "default_profile": self.config.default_profile,
            }

            pre_result = self.plugin_manager.apply_pre_request(
                active_plugins,
                request_id=request_id,
                endpoint_kind=endpoint_kind,
                profile=profile,
                request_body=request_body,
                request_headers=incoming_headers,
                context=request_context,
                shared_state=shared_state,
                on_plugin_error=on_plugin_error,
                services=self.services,
            )
            pre_actions = pre_result.actions
            degraded.extend(pre_result.degraded)
            if pre_result.blocked:
                raise MiddlewareError(
                    403,
                    "MODEIO_PLUGIN_BLOCKED",
                    pre_result.block_message,
                    retryable=False,
                    details={"phase": "pre_request"},
                )

            if stream_enabled:
                return self._process_stream_request(
                    endpoint_kind=endpoint_kind,
                    request_id=request_id,
                    profile=profile,
                    on_plugin_error=on_plugin_error,
                    active_plugins=active_plugins,
                    shared_state=shared_state,
                    request_context={
                        **request_context,
                        "preFindings": pre_result.findings,
                    },
                    upstream_payload=pre_result.body,
                    upstream_headers=pre_result.headers,
                    pre_actions=pre_actions,
                    degraded=degraded,
                )

            upstream_called = True
            upstream_payload = forward_upstream_json(
                config=self.config,
                endpoint_kind=endpoint_kind,
                payload=pre_result.body,
                incoming_headers=pre_result.headers,
            )

            post_result = self.plugin_manager.apply_post_response(
                active_plugins,
                request_id=request_id,
                endpoint_kind=endpoint_kind,
                profile=profile,
                request_context={
                    **request_context,
                    "preFindings": pre_result.findings,
                },
                response_body=upstream_payload,
                response_headers={},
                shared_state=shared_state,
                on_plugin_error=on_plugin_error,
                services=self.services,
            )
            post_actions = post_result.actions
            degraded.extend(post_result.degraded)
            if post_result.blocked:
                raise MiddlewareError(
                    403,
                    "MODEIO_PLUGIN_BLOCKED",
                    post_result.block_message,
                    retryable=False,
                    details={"phase": "post_response"},
                )

            headers = contract_headers(
                request_id,
                profile=profile,
                pre_actions=pre_actions,
                post_actions=post_actions,
                degraded=degraded,
                upstream_called=upstream_called,
            )
            return ProcessResult(status=200, payload=post_result.body, headers=headers)

        except MiddlewareError as error:
            return self._error_process_result(
                request_id=request_id,
                profile=profile,
                pre_actions=pre_actions,
                post_actions=post_actions,
                degraded=degraded,
                upstream_called=upstream_called,
                error=error,
            )
        except Exception:
            error = MiddlewareError(
                503,
                "MODEIO_INTERNAL_ERROR",
                "unexpected internal error",
                retryable=False,
            )
            return self._error_process_result(
                request_id=request_id,
                profile=profile,
                pre_actions=pre_actions,
                post_actions=post_actions,
                degraded=degraded,
                upstream_called=upstream_called,
                error=error,
            )

    def _process_stream_request(
        self,
        *,
        endpoint_kind: str,
        request_id: str,
        profile: str,
        on_plugin_error: str,
        active_plugins: List[ActivePlugin],
        shared_state: Dict[str, Any],
        request_context: Dict[str, Any],
        upstream_payload: Dict[str, Any],
        upstream_headers: Dict[str, str],
        pre_actions: List[str],
        degraded: List[str],
    ) -> Union[ProcessResult, StreamProcessResult]:
        upstream_response = forward_upstream_stream(
            config=self.config,
            endpoint_kind=endpoint_kind,
            payload=upstream_payload,
            incoming_headers=upstream_headers,
        )

        post_start_result = self.plugin_manager.apply_post_stream_start(
            active_plugins,
            request_id=request_id,
            endpoint_kind=endpoint_kind,
            profile=profile,
            request_context=request_context,
            response_context={},
            shared_state=shared_state,
            on_plugin_error=on_plugin_error,
            services=self.services,
        )
        degraded.extend(post_start_result.degraded)

        if post_start_result.blocked:
            upstream_response.close()
            return self._error_process_result(
                request_id=request_id,
                profile=profile,
                pre_actions=pre_actions,
                post_actions=post_start_result.actions,
                degraded=degraded,
                upstream_called=True,
                error=MiddlewareError(
                    403,
                    "MODEIO_PLUGIN_BLOCKED",
                    post_start_result.block_message,
                    retryable=False,
                    details={"phase": "post_stream_start"},
                ),
            )

        post_actions_seed = list(post_start_result.actions)
        headers = contract_headers(
            request_id,
            profile=profile,
            pre_actions=pre_actions,
            post_actions=post_actions_seed or ["stream"],
            degraded=degraded,
            upstream_called=True,
        )
        headers["Content-Type"] = upstream_response.headers.get("Content-Type", "text/event-stream")
        headers["Cache-Control"] = "no-cache"
        headers["x-modeio-streaming"] = "true"

        return StreamProcessResult(
            status=200,
            headers=headers,
            stream=iter_transformed_sse_stream(
                upstream_response=upstream_response,
                plugin_manager=self.plugin_manager,
                active_plugins=active_plugins,
                request_id=request_id,
                endpoint_kind=endpoint_kind,
                profile=profile,
                request_context=request_context,
                shared_state=shared_state,
                on_plugin_error=on_plugin_error,
                degraded=degraded,
                services=self.services,
            ),
            payload=None,
        )
