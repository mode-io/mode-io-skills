#!/usr/bin/env python3

from __future__ import annotations

import gzip
import json
import socket
import threading
import zlib
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from modeio_middleware.core.engine import GatewayRuntimeConfig, MiddlewareEngine, ProcessResult, StreamProcessResult
from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.core.http_contract import (
    CONTRACT_VERSION,
    contract_headers,
    error_payload,
    new_request_id,
    safe_json_dumps,
)

try:  # Python 3.14+
    from compression import zstd as _zstd_codec
except Exception:  # pragma: no cover
    _zstd_codec = None

CLAUDE_HOOK_CONNECTOR_PATH = "/connectors/claude/hooks"


def _decode_content_encoded_body(body_bytes: bytes, content_encoding: str) -> bytes:
    decoded = body_bytes
    encodings = [item.strip().lower() for item in content_encoding.split(",") if item.strip()]
    if not encodings:
        return decoded

    for encoding in reversed(encodings):
        if encoding == "identity":
            continue

        try:
            if encoding in {"gzip", "x-gzip"}:
                decoded = gzip.decompress(decoded)
            elif encoding == "deflate":
                try:
                    decoded = zlib.decompress(decoded)
                except zlib.error:
                    decoded = zlib.decompress(decoded, -zlib.MAX_WBITS)
            elif encoding in {"zstd", "x-zstd"}:
                if _zstd_codec is None:
                    raise MiddlewareError(
                        400,
                        "MODEIO_VALIDATION_ERROR",
                        "content encoding 'zstd' is not supported in this Python runtime",
                    )
                decoded = _zstd_codec.decompress(decoded)
            else:
                raise MiddlewareError(
                    400,
                    "MODEIO_VALIDATION_ERROR",
                    f"unsupported Content-Encoding '{encoding}'",
                )
        except MiddlewareError:
            raise
        except Exception as error:
            raise MiddlewareError(
                400,
                "MODEIO_VALIDATION_ERROR",
                f"failed to decode request body with Content-Encoding '{encoding}'",
            ) from error

    return decoded


async def _read_json_body(request: Request) -> Dict[str, Any]:
    body_bytes = await request.body()
    if not body_bytes:
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "request body must not be empty")

    content_encoding = str(request.headers.get("Content-Encoding", "")).strip()
    if content_encoding:
        body_bytes = _decode_content_encoded_body(body_bytes, content_encoding)

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "request body must be valid JSON") from error

    if not isinstance(payload, dict):
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "request body must be a JSON object")
    return payload


def _json_response(
    status: int,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
) -> Response:
    response = Response(
        content=safe_json_dumps(payload),
        status_code=status,
        media_type="application/json; charset=utf-8",
    )
    if headers:
        for key, value in headers.items():
            response.headers[key] = str(value)
    return response


def _default_contract_headers(engine: MiddlewareEngine, request_id: str) -> Dict[str, str]:
    return contract_headers(
        request_id,
        profile=engine.config.default_profile,
        pre_actions=[],
        post_actions=[],
        degraded=[],
        upstream_called=False,
    )


def _contract_error_response(
    engine: MiddlewareEngine,
    request_id: str,
    *,
    status: int,
    code: str,
    message: str,
    retryable: bool,
    details: Optional[Dict[str, Any]] = None,
) -> Response:
    return _json_response(
        status,
        error_payload(
            request_id,
            code,
            message,
            retryable=retryable,
            details=details,
        ),
        _default_contract_headers(engine, request_id),
    )


def _render_engine_result(
    engine: MiddlewareEngine,
    request_id: str,
    result: ProcessResult | StreamProcessResult,
) -> Response:
    if isinstance(result, StreamProcessResult):
        if result.stream is not None:
            return StreamingResponse(
                result.stream,
                status_code=result.status,
                headers=result.headers,
            )

        payload = result.payload or error_payload(
            request_id,
            "MODEIO_INTERNAL_ERROR",
            "stream result missing payload",
            retryable=False,
        )
        return _json_response(result.status, payload, result.headers)

    if isinstance(result, ProcessResult):
        return _json_response(result.status, result.payload, result.headers)

    return _json_response(
        500,
        error_payload(
            request_id,
            "MODEIO_INTERNAL_ERROR",
            "unexpected result type from middleware engine",
            retryable=False,
        ),
        _default_contract_headers(engine, request_id),
    )


def create_app(config: GatewayRuntimeConfig) -> Starlette:
    engine = MiddlewareEngine(config)

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        try:
            yield
        finally:
            engine.shutdown()

    async def healthz(_request: Request) -> Response:
        payload = {
            "ok": True,
            "service": "modeio-middleware",
            "version": CONTRACT_VERSION,
            "profiles": sorted(list((engine.config.profiles or {}).keys())),
        }
        return _json_response(200, payload)

    async def _process_post_request(request: Request) -> Response:
        request_id = new_request_id()
        try:
            body = await _read_json_body(request)
        except MiddlewareError as error:
            return _contract_error_response(
                engine,
                request_id,
                status=error.status,
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                details=error.details,
            )

        try:
            result = await run_in_threadpool(
                engine.process_http_request,
                path=str(request.url.path),
                request_id=request_id,
                payload=body,
                incoming_headers=dict(request.headers.items()),
            )
        except MiddlewareError as error:
            return _contract_error_response(
                engine,
                request_id,
                status=error.status,
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                details=error.details,
            )
        return _render_engine_result(engine, request_id, result)

    async def unknown_post(_request: Request) -> Response:
        request_id = new_request_id()
        return _contract_error_response(
            engine,
            request_id,
            status=404,
            code="MODEIO_ROUTE_NOT_FOUND",
            message="route not found",
            retryable=False,
        )

    app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route(CLAUDE_HOOK_CONNECTOR_PATH, _process_post_request, methods=["POST"]),
            Route("/v1/chat/completions", _process_post_request, methods=["POST"]),
            Route("/v1/responses", _process_post_request, methods=["POST"]),
            Route("/{rest:path}", unknown_post, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
    app.state.engine = engine
    return app


class GatewayServer:
    def __init__(self, host: str, port: int, app: Starlette):
        self._app = app
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((host, port))
        self._socket.listen(128)
        self._socket.setblocking(False)
        self.server_address = self._socket.getsockname()
        self._server: uvicorn.Server | None = None
        self._closed = False
        self._serve_done = threading.Event()

    def _finalize(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._socket.close()
        except Exception:
            pass

    def serve_forever(self) -> None:
        config = uvicorn.Config(
            self._app,
            host=str(self.server_address[0]),
            port=int(self.server_address[1]),
            log_config=None,
            access_log=False,
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None
        self._server = server
        try:
            server.run(sockets=[self._socket])
        finally:
            self._finalize()
            self._serve_done.set()

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.should_exit = True

    def server_close(self) -> None:
        self.shutdown()
        self._serve_done.wait(timeout=5)
        self._finalize()


def create_server(host: str, port: int, config: GatewayRuntimeConfig) -> GatewayServer:
    return GatewayServer(host, port, create_app(config))
