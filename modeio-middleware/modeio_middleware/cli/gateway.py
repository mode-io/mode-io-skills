#!/usr/bin/env python3
"""OpenAI-compatible middleware gateway for request/response hooks."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from urllib.parse import urlsplit

try:  # Python 3.14+
    from compression import zstd as _zstd_codec
except Exception:  # pragma: no cover
    _zstd_codec = None

from modeio_middleware.connectors.claude_hooks import CLAUDE_HOOK_CONNECTOR_PATH
from modeio_middleware.core.config_resolver import load_preset_registry
from modeio_middleware.core.contracts import ENDPOINT_CHAT_COMPLETIONS, ENDPOINT_RESPONSES
from modeio_middleware.core.engine import GatewayRuntimeConfig, MiddlewareEngine, ProcessResult, StreamProcessResult
from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.core.http_contract import (
    CONTRACT_VERSION,
    contract_headers,
    error_payload,
    new_request_id,
    safe_json_dumps,
)
from modeio_middleware.core.profiles import DEFAULT_PROFILE, normalize_profile_name

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_UPSTREAM_CHAT_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_UPSTREAM_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = 60
DEFAULT_UPSTREAM_API_KEY_ENV = "MODEIO_GATEWAY_UPSTREAM_API_KEY"

PATH_TO_ENDPOINT_KIND = {
    "/v1/chat/completions": ENDPOINT_CHAT_COMPLETIONS,
    "/v1/responses": ENDPOINT_RESPONSES,
}


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


def _read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    raw_length = handler.headers.get("Content-Length")
    if raw_length is None:
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "missing Content-Length header")

    try:
        length = int(raw_length)
    except ValueError as error:
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "invalid Content-Length header") from error

    if length <= 0:
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "request body must not be empty")

    body_bytes = handler.rfile.read(length)
    content_encoding = str(handler.headers.get("Content-Encoding", "")).strip()
    if content_encoding:
        body_bytes = _decode_content_encoded_body(body_bytes, content_encoding)

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "request body must be valid JSON") from error

    if not isinstance(payload, dict):
        raise MiddlewareError(400, "MODEIO_VALIDATION_ERROR", "request body must be a JSON object")
    return payload


def _default_config_path() -> Path:
    current = Path(__file__).resolve()
    return current.parents[2] / "config" / "default.json"


def _load_runtime_file(path: Path) -> Dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MiddlewareError(500, "MODEIO_CONFIG_ERROR", f"failed to read config file: {path}") from error

    try:
        payload = json.loads(content)
    except ValueError as error:
        raise MiddlewareError(500, "MODEIO_CONFIG_ERROR", f"invalid JSON config: {path}") from error

    if not isinstance(payload, dict):
        raise MiddlewareError(500, "MODEIO_CONFIG_ERROR", "middleware config root must be an object")
    return payload


def load_runtime_config(args: argparse.Namespace) -> GatewayRuntimeConfig:
    config_path = Path(args.config).expanduser()
    config_payload = _load_runtime_file(config_path)
    profiles = config_payload.get("profiles", {})
    plugins = config_payload.get("plugins", {})
    services = config_payload.get("services", {})
    preset_registry = load_preset_registry(config_payload, config_file_path=config_path)

    if not isinstance(profiles, dict):
        raise MiddlewareError(500, "MODEIO_CONFIG_ERROR", "config.profiles must be an object")
    if not isinstance(plugins, dict):
        raise MiddlewareError(500, "MODEIO_CONFIG_ERROR", "config.plugins must be an object")
    if not isinstance(services, dict):
        raise MiddlewareError(500, "MODEIO_CONFIG_ERROR", "config.services must be an object")

    return GatewayRuntimeConfig(
        upstream_chat_completions_url=args.upstream_chat_url,
        upstream_responses_url=args.upstream_responses_url,
        upstream_timeout_seconds=args.upstream_timeout,
        upstream_api_key_env=args.upstream_api_key_env,
        default_profile=normalize_profile_name(args.default_profile, default_profile=DEFAULT_PROFILE),
        profiles=profiles,
        plugins=plugins,
        preset_registry=preset_registry,
        service_config=services,
        config_base_dir=str(config_path.parent),
    )


def build_handler(engine: MiddlewareEngine):
    class MiddlewareHandler(BaseHTTPRequestHandler):
        server_version = "ModeioMiddleware/0.1"
        protocol_version = "HTTP/1.1"

        def _send_json(self, status: int, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> None:
            body = safe_json_dumps(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if headers:
                for key, value in headers.items():
                    self.send_header(key, str(value))
            self.end_headers()
            self.wfile.write(body)

        def _default_contract_headers(self, request_id: str) -> Dict[str, str]:
            return contract_headers(
                request_id,
                profile=engine.config.default_profile,
                pre_actions=[],
                post_actions=[],
                degraded=[],
                upstream_called=False,
            )

        def _send_contract_error(
            self,
            request_id: str,
            *,
            status: int,
            code: str,
            message: str,
            retryable: bool,
            details: Optional[Dict[str, Any]] = None,
        ) -> None:
            self._send_json(
                status,
                error_payload(
                    request_id,
                    code,
                    message,
                    retryable=retryable,
                    details=details,
                ),
                self._default_contract_headers(request_id),
            )

        def _read_json_body_or_send_error(self, request_id: str) -> Optional[Dict[str, Any]]:
            try:
                return _read_json_body(self)
            except MiddlewareError as error:
                self._send_contract_error(
                    request_id,
                    status=error.status,
                    code=error.code,
                    message=error.message,
                    retryable=error.retryable,
                    details=error.details,
                )
                return None

        def _send_stream(self, status: int, stream: Sequence[bytes] | Any, headers: Dict[str, str]) -> None:
            self.send_response(status)
            has_connection_header = False
            for key, value in headers.items():
                if key.lower() == "connection":
                    has_connection_header = True
                self.send_header(key, str(value))
            if not has_connection_header:
                self.send_header("Connection", "close")
            self.end_headers()

            try:
                for chunk in stream:
                    if not isinstance(chunk, (bytes, bytearray)):
                        continue
                    self.wfile.write(bytes(chunk))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            finally:
                self.close_connection = True

        def do_GET(self) -> None:
            if self.path != "/healthz":
                self._send_json(404, {"error": {"message": "not found"}})
                return

            payload = {
                "ok": True,
                "service": "modeio-middleware",
                "version": CONTRACT_VERSION,
                "profiles": sorted(list((engine.config.profiles or {}).keys())),
            }
            self._send_json(200, payload)

        def do_POST(self) -> None:
            request_id = new_request_id()
            request_path = urlsplit(self.path).path

            if request_path == CLAUDE_HOOK_CONNECTOR_PATH:
                body = self._read_json_body_or_send_error(request_id)
                if body is None:
                    return

                result = engine.process_claude_hook(
                    request_id=request_id,
                    payload=body,
                    incoming_headers=dict(self.headers.items()),
                )
                self._send_json(result.status, result.payload, result.headers)
                return

            endpoint_kind = PATH_TO_ENDPOINT_KIND.get(request_path)

            if endpoint_kind is None:
                self._send_contract_error(
                    request_id,
                    status=404,
                    code="MODEIO_ROUTE_NOT_FOUND",
                    message="route not found",
                    retryable=False,
                )
                return

            body = self._read_json_body_or_send_error(request_id)
            if body is None:
                return

            result = engine.process_request(
                endpoint_kind=endpoint_kind,
                request_id=request_id,
                request_body=body,
                incoming_headers=dict(self.headers.items()),
            )
            if isinstance(result, StreamProcessResult):
                if result.stream is not None:
                    self._send_stream(result.status, result.stream, result.headers)
                    return

                payload = result.payload or error_payload(
                    request_id,
                    "MODEIO_INTERNAL_ERROR",
                    "stream result missing payload",
                    retryable=False,
                )
                self._send_json(result.status, payload, result.headers)
                return

            if isinstance(result, ProcessResult):
                self._send_json(result.status, result.payload, result.headers)
                return

            self._send_json(
                500,
                error_payload(
                    request_id,
                    "MODEIO_INTERNAL_ERROR",
                    "unexpected result type from middleware engine",
                    retryable=False,
                ),
                contract_headers(
                    request_id,
                    profile=engine.config.default_profile,
                    pre_actions=[],
                    post_actions=[],
                    degraded=[],
                    upstream_called=False,
                ),
            )

        def log_message(self, format: str, *args: Any) -> None:
            message = format % args
            sys.stderr.write(f"[modeio-middleware] {self.address_string()} {message}\n")

    return MiddlewareHandler


def create_server(host: str, port: int, config: GatewayRuntimeConfig) -> ThreadingHTTPServer:
    engine = MiddlewareEngine(config)
    handler = build_handler(engine)
    return ThreadingHTTPServer((host, port), handler)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run local modeio-middleware gateway for Codex/OpenCode provider routing. "
            "Contract: POST /v1/chat/completions, /v1/responses, /connectors/claude/hooks, GET /healthz"
        )
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Listen host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Listen port (default: {DEFAULT_PORT})")
    parser.add_argument(
        "--upstream-chat-url",
        default=os.environ.get("MODEIO_MIDDLEWARE_UPSTREAM_CHAT_URL", DEFAULT_UPSTREAM_CHAT_URL),
        help=(
            "Upstream OpenAI-compatible chat completions endpoint "
            f"(default env MODEIO_MIDDLEWARE_UPSTREAM_CHAT_URL or {DEFAULT_UPSTREAM_CHAT_URL})"
        ),
    )
    parser.add_argument(
        "--upstream-responses-url",
        default=os.environ.get("MODEIO_MIDDLEWARE_UPSTREAM_RESPONSES_URL", DEFAULT_UPSTREAM_RESPONSES_URL),
        help=(
            "Upstream OpenAI-compatible responses endpoint "
            f"(default env MODEIO_MIDDLEWARE_UPSTREAM_RESPONSES_URL or {DEFAULT_UPSTREAM_RESPONSES_URL})"
        ),
    )
    parser.add_argument(
        "--upstream-timeout",
        type=int,
        default=DEFAULT_UPSTREAM_TIMEOUT_SECONDS,
        help=f"Upstream timeout seconds (default: {DEFAULT_UPSTREAM_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--upstream-api-key-env",
        default=DEFAULT_UPSTREAM_API_KEY_ENV,
        help=(
            "Environment variable name containing upstream API key when incoming request "
            "has no Authorization header"
        ),
    )
    parser.add_argument(
        "--config",
        default=str(_default_config_path()),
        help="Middleware config JSON path",
    )
    parser.add_argument(
        "--default-profile",
        default=DEFAULT_PROFILE,
        help=f"Default middleware profile when request has no modeio.profile (default: {DEFAULT_PROFILE})",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        config = load_runtime_config(args)
    except MiddlewareError as error:
        print(f"Failed to load middleware config: {error.message}", file=sys.stderr)
        return 1

    server = create_server(args.host, args.port, config)
    listen_host, listen_port = server.server_address
    print(
        (
            f"modeio-middleware listening on http://{listen_host}:{listen_port} "
            f"-> chat upstream {config.upstream_chat_completions_url} "
            f"-> responses upstream {config.upstream_responses_url}"
        ),
        file=sys.stderr,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down middleware...", file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
