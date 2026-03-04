#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, Optional, TYPE_CHECKING, Union

try:
    import requests
except ModuleNotFoundError:
    class _ShimResponse:
        def __init__(self, status_code: int, body: bytes, headers: Optional[Dict[str, str]] = None):
            self.status_code = status_code
            self._body = body
            self.headers = headers or {}

        def json(self) -> Any:
            return json.loads(self._body.decode("utf-8"))

        def iter_lines(
            self,
            chunk_size: int = 512,
            decode_unicode: bool = False,
        ) -> Iterator[Union[str, bytes]]:
            del chunk_size
            for line in self._body.splitlines():
                if decode_unicode:
                    yield line.decode("utf-8", errors="replace")
                else:
                    yield line

        def close(self) -> None:
            return

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
            stream: bool = False,
        ):
            del stream
            payload = json_module.dumps(json).encode("utf-8")
            request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    body = response.read()
                    response_headers = {k: v for k, v in response.headers.items()}
                    return _ShimResponse(response.status, body, response_headers)
            except urllib.error.HTTPError as error:
                try:
                    body = error.read()
                    response_headers = {k: v for k, v in error.headers.items()}
                    return _ShimResponse(error.code, body, response_headers)
                finally:
                    error.close()
            except urllib.error.URLError as error:
                raise _RequestsShim.RequestException(str(error)) from error

    json_module = json
    requests = _RequestsShim()

from modeio_middleware.core.contracts import ENDPOINT_CHAT_COMPLETIONS, ENDPOINT_RESPONSES
from modeio_middleware.core.errors import MiddlewareError

if TYPE_CHECKING:
    from modeio_middleware.core.engine import GatewayRuntimeConfig

MAX_RETRIES = 2
RETRY_BACKOFF = 1.0


def _post_with_retry(
    *,
    url: str,
    headers: Dict[str, str],
    json_payload: Dict[str, Any],
    timeout: int,
    stream: bool,
):
    last_exception = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=json_payload,
                timeout=timeout,
                stream=stream,
            )
            if response.status_code in (502, 503, 504) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (2**attempt))
                continue
            return response
        except requests.RequestException as error:
            last_exception = error
            if isinstance(error, (requests.ConnectionError, requests.Timeout)) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (2**attempt))
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


def _resolve_upstream_url(config: "GatewayRuntimeConfig", endpoint_kind: str) -> str:
    if endpoint_kind == ENDPOINT_CHAT_COMPLETIONS:
        return config.upstream_chat_completions_url
    if endpoint_kind == ENDPOINT_RESPONSES:
        return config.upstream_responses_url
    raise MiddlewareError(
        500,
        "MODEIO_INTERNAL_ERROR",
        f"unsupported endpoint kind '{endpoint_kind}'",
        retryable=False,
    )


def forward_upstream_json(
    *,
    config: "GatewayRuntimeConfig",
    endpoint_kind: str,
    payload: Dict[str, Any],
    incoming_headers: Dict[str, str],
) -> Dict[str, Any]:
    headers = _build_upstream_headers(
        incoming_headers,
        upstream_api_key_env=config.upstream_api_key_env,
    )
    upstream_url = _resolve_upstream_url(config, endpoint_kind)

    try:
        response = _post_with_retry(
            url=upstream_url,
            headers=headers,
            json_payload=payload,
            timeout=config.upstream_timeout_seconds,
            stream=False,
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


def forward_upstream_stream(
    *,
    config: "GatewayRuntimeConfig",
    endpoint_kind: str,
    payload: Dict[str, Any],
    incoming_headers: Dict[str, str],
):
    headers = _build_upstream_headers(
        incoming_headers,
        upstream_api_key_env=config.upstream_api_key_env,
    )
    headers["Accept"] = "text/event-stream"
    upstream_url = _resolve_upstream_url(config, endpoint_kind)

    try:
        response = _post_with_retry(
            url=upstream_url,
            headers=headers,
            json_payload=payload,
            timeout=config.upstream_timeout_seconds,
            stream=True,
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
        response.close()
        raise MiddlewareError(
            mapped_status,
            "MODEIO_UPSTREAM_ERROR",
            f"upstream returned status {response.status_code}",
            retryable=retryable,
            details={"upstreamStatus": response.status_code},
        )

    return response
