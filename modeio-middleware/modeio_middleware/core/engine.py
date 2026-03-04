#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List

try:
    import requests
except ModuleNotFoundError:
    class _ShimResponse:
        def __init__(self, status_code: int, body: bytes):
            self.status_code = status_code
            self._body = body

        def json(self) -> Any:
            return json.loads(self._body.decode("utf-8"))

    class _RequestsShim:
        class RequestException(Exception):
            pass

        class ConnectionError(RequestException):
            pass

        class Timeout(RequestException):
            pass

        @staticmethod
        def post(
            url: str,
            *,
            headers: Dict[str, str],
            json: Dict[str, Any],
            timeout: int,
        ):
            payload = json_module.dumps(json).encode("utf-8")
            request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return _ShimResponse(response.status, response.read())
            except urllib.error.HTTPError as error:
                try:
                    body = error.read()
                    return _ShimResponse(error.code, body)
                finally:
                    error.close()
            except urllib.error.URLError as error:
                raise _RequestsShim.RequestException(str(error)) from error

    json_module = json
    requests = _RequestsShim()

from modeio_middleware.core.contracts import normalize_modeio_options, validate_chat_payload
from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.core.http_contract import contract_headers, error_payload
from modeio_middleware.core.plugin_manager import PluginManager
from modeio_middleware.core.profiles import (
    DEFAULT_PROFILE,
    normalize_profile_name,
    resolve_plugin_error_policy,
    resolve_profile,
    resolve_profile_plugins,
)

MAX_RETRIES = 2
RETRY_BACKOFF = 1.0


@dataclass(frozen=True)
class GatewayRuntimeConfig:
    upstream_url: str
    upstream_timeout_seconds: int
    upstream_api_key_env: str
    default_profile: str = DEFAULT_PROFILE
    profiles: Dict[str, Any] = None  # type: ignore[assignment]
    plugins: Dict[str, Any] = None  # type: ignore[assignment]


@dataclass
class ProcessResult:
    status: int
    payload: Dict[str, Any]
    headers: Dict[str, str]


def _post_with_retry(
    *,
    url: str,
    headers: Dict[str, str],
    json_payload: Dict[str, Any],
    timeout: int,
):
    last_exception = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=json_payload,
                timeout=timeout,
            )
            if response.status_code in (502, 503, 504) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (2 ** attempt))
                continue
            return response
        except requests.RequestException as error:
            last_exception = error
            if isinstance(error, (requests.ConnectionError, requests.Timeout)) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (2 ** attempt))
                continue
            raise
    raise last_exception  # type: ignore[misc]


def _build_upstream_headers(
    incoming_headers: Dict[str, str],
    *,
    upstream_api_key_env: str,
) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    authorization = incoming_headers.get("authorization") or incoming_headers.get("Authorization")
    if not authorization:
        fallback_key = os.environ.get(upstream_api_key_env, "").strip()
        if fallback_key:
            authorization = f"Bearer {fallback_key}"
    if authorization:
        headers["Authorization"] = authorization
    return headers


def _forward_upstream(
    *,
    config: GatewayRuntimeConfig,
    payload: Dict[str, Any],
    incoming_headers: Dict[str, str],
) -> Dict[str, Any]:
    headers = _build_upstream_headers(
        incoming_headers,
        upstream_api_key_env=config.upstream_api_key_env,
    )
    try:
        response = _post_with_retry(
            url=config.upstream_url,
            headers=headers,
            json_payload=payload,
            timeout=config.upstream_timeout_seconds,
        )
    except requests.RequestException as error:
        raise MiddlewareError(
            502,
            "MODEIO_UPSTREAM_TIMEOUT",
            f"upstream request failed: {type(error).__name__}",
            retryable=True,
        ) from error

    if response.status_code >= 400:
        retryable = response.status_code >= 500
        mapped_status = response.status_code if response.status_code < 500 else 502
        raise MiddlewareError(
            mapped_status,
            "MODEIO_UPSTREAM_ERROR",
            f"upstream returned status {response.status_code}",
            retryable=retryable,
            details={"upstreamStatus": response.status_code},
        )

    try:
        response_payload = response.json()
    except ValueError as error:
        raise MiddlewareError(
            502,
            "MODEIO_UPSTREAM_INVALID_JSON",
            "upstream response is not valid JSON",
            retryable=False,
        ) from error

    if not isinstance(response_payload, dict):
        raise MiddlewareError(
            502,
            "MODEIO_UPSTREAM_INVALID_JSON",
            "upstream response root must be an object",
            retryable=False,
        )

    return response_payload


class MiddlewareEngine:
    def __init__(self, runtime_config: GatewayRuntimeConfig):
        self.config = runtime_config
        self.plugin_manager = PluginManager(runtime_config.plugins or {})

    def process_chat_request(
        self,
        *,
        request_id: str,
        request_body: Dict[str, Any],
        incoming_headers: Dict[str, str],
    ) -> ProcessResult:
        upstream_called = False
        pre_actions: List[str] = []
        post_actions: List[str] = []
        degraded: List[str] = []
        profile = self.config.default_profile

        try:
            validate_chat_payload(request_body)

            options = normalize_modeio_options(
                request_body,
                default_profile=self.config.default_profile,
            )
            profile = normalize_profile_name(options.profile, default_profile=self.config.default_profile)

            profile_config = resolve_profile(self.config.profiles or {}, profile)
            on_plugin_error = resolve_plugin_error_policy(profile_config, options.on_plugin_error)
            plugin_order = resolve_profile_plugins(profile_config)
            active_plugins = self.plugin_manager.resolve_active_plugins(plugin_order, options.plugin_overrides)

            shared_state: Dict[str, Any] = {}
            request_context = {
                "upstream_url": self.config.upstream_url,
                "default_profile": self.config.default_profile,
            }

            pre_result = self.plugin_manager.apply_pre_request(
                active_plugins,
                request_id=request_id,
                profile=profile,
                request_body=request_body,
                request_headers=incoming_headers,
                context=request_context,
                shared_state=shared_state,
                on_plugin_error=on_plugin_error,
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

            upstream_called = True
            upstream_payload = _forward_upstream(
                config=self.config,
                payload=pre_result.body,
                incoming_headers=pre_result.headers,
            )

            post_result = self.plugin_manager.apply_post_response(
                active_plugins,
                request_id=request_id,
                profile=profile,
                request_context={
                    **request_context,
                    "preFindings": pre_result.findings,
                },
                response_body=upstream_payload,
                response_headers={},
                shared_state=shared_state,
                on_plugin_error=on_plugin_error,
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
        except Exception:
            payload = error_payload(
                request_id,
                "MODEIO_INTERNAL_ERROR",
                "unexpected internal error",
                retryable=False,
            )
            headers = contract_headers(
                request_id,
                profile=profile,
                pre_actions=pre_actions,
                post_actions=post_actions,
                degraded=degraded,
                upstream_called=upstream_called,
            )
            return ProcessResult(status=503, payload=payload, headers=headers)
