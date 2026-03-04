#!/usr/bin/env python3
"""OpenAI-compatible middleware gateway for request/response hooks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from modeio_middleware.core.engine import GatewayRuntimeConfig, MiddlewareEngine
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
DEFAULT_UPSTREAM_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = 60
DEFAULT_UPSTREAM_API_KEY_ENV = "MODEIO_GATEWAY_UPSTREAM_API_KEY"


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
    config_payload = _load_runtime_file(Path(args.config).expanduser())
    profiles = config_payload.get("profiles", {})
    plugins = config_payload.get("plugins", {})

    if not isinstance(profiles, dict):
        raise MiddlewareError(500, "MODEIO_CONFIG_ERROR", "config.profiles must be an object")
    if not isinstance(plugins, dict):
        raise MiddlewareError(500, "MODEIO_CONFIG_ERROR", "config.plugins must be an object")

    return GatewayRuntimeConfig(
        upstream_url=args.upstream_url,
        upstream_timeout_seconds=args.upstream_timeout,
        upstream_api_key_env=args.upstream_api_key_env,
        default_profile=normalize_profile_name(args.default_profile, default_profile=DEFAULT_PROFILE),
        profiles=profiles,
        plugins=plugins,
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

            if self.path != "/v1/chat/completions":
                headers = contract_headers(
                    request_id,
                    profile=engine.config.default_profile,
                    pre_actions=[],
                    post_actions=[],
                    degraded=[],
                    upstream_called=False,
                )
                payload = error_payload(
                    request_id,
                    "MODEIO_ROUTE_NOT_FOUND",
                    "route not found",
                    retryable=False,
                )
                self._send_json(404, payload, headers)
                return

            try:
                body = _read_json_body(self)
            except MiddlewareError as error:
                headers = contract_headers(
                    request_id,
                    profile=engine.config.default_profile,
                    pre_actions=[],
                    post_actions=[],
                    degraded=[],
                    upstream_called=False,
                )
                payload = error_payload(
                    request_id,
                    error.code,
                    error.message,
                    retryable=error.retryable,
                    details=error.details,
                )
                self._send_json(error.status, payload, headers)
                return

            result = engine.process_chat_request(
                request_id=request_id,
                request_body=body,
                incoming_headers=dict(self.headers.items()),
            )
            self._send_json(result.status, result.payload, result.headers)

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
            "Contract: POST /v1/chat/completions (stream=false), GET /healthz"
        )
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Listen host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Listen port (default: {DEFAULT_PORT})")
    parser.add_argument(
        "--upstream-url",
        default=os.environ.get("MODEIO_MIDDLEWARE_UPSTREAM_URL", DEFAULT_UPSTREAM_URL),
        help=(
            "Upstream OpenAI-compatible chat completions endpoint "
            f"(default env MODEIO_MIDDLEWARE_UPSTREAM_URL or {DEFAULT_UPSTREAM_URL})"
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
        f"modeio-middleware listening on http://{listen_host}:{listen_port} "
        f"-> upstream {config.upstream_url}",
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
