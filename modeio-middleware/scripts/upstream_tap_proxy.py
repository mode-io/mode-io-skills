#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _body_preview(body: bytes, *, limit: int) -> str:
    if not body:
        return ""
    text = body.decode("utf-8", errors="replace")
    if len(text) <= limit:
        return text
    return text[:limit]


def _body_sha256_hex(body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(body)
    return digest.hexdigest()


def _default_forward_url(target_base_url: str, request_path: str) -> str:
    base = target_base_url.rstrip("/")
    if not request_path.startswith("/"):
        request_path = f"/{request_path}"

    incoming = urlsplit(request_path)
    incoming_path = incoming.path or "/"

    parsed = urlsplit(base)
    base_path = parsed.path.rstrip("/")
    normalized_path = incoming_path
    if incoming_path.startswith("/v1/") and base_path.endswith("/v1"):
        normalized_path = incoming_path[len("/v1") :]

    merged_path = f"{base_path}{normalized_path}" if base_path else normalized_path
    query = incoming.query or parsed.query
    return urlunsplit((parsed.scheme, parsed.netloc, merged_path, query, parsed.fragment))


class JsonlLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, payload: Dict[str, object]) -> None:
        line = json.dumps(payload, ensure_ascii=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")


def _sanitize_headers_for_log(headers: Dict[str, str]) -> Dict[str, object]:
    auth_header = headers.get("authorization")
    return {
        "authorizationPresent": isinstance(auth_header, str) and bool(auth_header.strip()),
        "authorizationPrefix": auth_header.split(" ", 1)[0] if auth_header else None,
        "contentType": headers.get("content-type"),
        "accept": headers.get("accept"),
        "userAgent": headers.get("user-agent"),
    }


def _filtered_response_headers(headers: Iterable[Tuple[str, str]], body_len: int) -> List[Tuple[str, str]]:
    filtered: List[Tuple[str, str]] = []
    for key, value in headers:
        normalized = key.lower()
        if normalized in HOP_BY_HOP_HEADERS or normalized == "content-length":
            continue
        filtered.append((key, value))
    filtered.append(("Content-Length", str(body_len)))
    return filtered


def _build_handler(
    *,
    target_base_url: str,
    logger: JsonlLogger,
    api_key_env: str,
    upstream_timeout_seconds: int,
    body_preview_limit: int,
):
    class TapProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _handle_request(self) -> None:
            if self.command == "GET" and self.path == "/healthz":
                self._respond_healthz()
                return

            started = time.monotonic()
            request_id = hashlib.md5(f"{time.time_ns()}:{threading.get_ident()}".encode("utf-8")).hexdigest()

            content_length = int(self.headers.get("Content-Length", "0") or "0")
            request_body = self.rfile.read(content_length) if content_length > 0 else b""
            request_headers = {k.lower(): v for k, v in self.headers.items()}

            upstream_headers: Dict[str, str] = {}
            for key, value in self.headers.items():
                normalized = key.lower()
                if normalized in HOP_BY_HOP_HEADERS or normalized in {"host", "content-length"}:
                    continue
                upstream_headers[key] = value

            upstream_api_key = os.environ.get(api_key_env, "").strip()
            if upstream_api_key:
                upstream_headers["Authorization"] = f"Bearer {upstream_api_key}"

            upstream_url = _default_forward_url(target_base_url, self.path)
            upstream_req = urllib.request.Request(
                upstream_url,
                data=request_body,
                headers=upstream_headers,
                method=self.command,
            )

            upstream_status = 0
            upstream_response_headers: Sequence[Tuple[str, str]] = []
            upstream_response_body = b""
            upstream_error = None
            try:
                with urllib.request.urlopen(upstream_req, timeout=upstream_timeout_seconds) as response:
                    upstream_status = response.status
                    upstream_response_headers = list(response.headers.items())
                    upstream_response_body = response.read()
            except urllib.error.HTTPError as error:
                upstream_status = error.code
                upstream_response_headers = list(error.headers.items()) if error.headers else []
                upstream_response_body = error.read()
            except Exception as error:  # pragma: no cover - network/runtime dependent
                upstream_error = str(error)

            if upstream_error is not None:
                error_body = json.dumps(
                    {
                        "error": "tap_proxy_upstream_error",
                        "message": upstream_error,
                    }
                ).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(error_body)))
                self.end_headers()
                self.wfile.write(error_body)
                upstream_status = 502
                upstream_response_headers = [("Content-Type", "application/json")]
                upstream_response_body = error_body
            else:
                self.send_response(upstream_status)
                for key, value in _filtered_response_headers(
                    upstream_response_headers,
                    body_len=len(upstream_response_body),
                ):
                    self.send_header(key, value)
                self.end_headers()
                if upstream_response_body:
                    self.wfile.write(upstream_response_body)

            elapsed_ms = int((time.monotonic() - started) * 1000)
            logger.log(
                {
                    "ts": _utc_now_iso(),
                    "event": "exchange",
                    "requestId": request_id,
                    "request": {
                        "method": self.command,
                        "path": self.path,
                        "upstreamUrl": upstream_url,
                        "headers": _sanitize_headers_for_log(request_headers),
                        "bodySha256": _body_sha256_hex(request_body),
                        "bodyPreview": _body_preview(request_body, limit=body_preview_limit),
                    },
                    "response": {
                        "status": upstream_status,
                        "headers": {
                            "contentType": dict((k.lower(), v) for k, v in upstream_response_headers).get("content-type")
                        },
                        "bodySha256": _body_sha256_hex(upstream_response_body),
                        "bodyPreview": _body_preview(upstream_response_body, limit=body_preview_limit),
                    },
                    "durationMs": elapsed_ms,
                }
            )

        def _respond_healthz(self) -> None:
            body = b'{"ok":true,"service":"upstream-tap-proxy"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            self._handle_request()

        def do_POST(self) -> None:  # noqa: N802
            self._handle_request()

        def do_PUT(self) -> None:  # noqa: N802
            self._handle_request()

        def do_PATCH(self) -> None:  # noqa: N802
            self._handle_request()

        def do_DELETE(self) -> None:  # noqa: N802
            self._handle_request()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._handle_request()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return TapProxyHandler


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local tap proxy that forwards to a real upstream and logs request/response exchanges."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Listen host")
    parser.add_argument("--port", type=int, required=True, help="Listen port")
    parser.add_argument(
        "--target-base-url",
        required=True,
        help="Real upstream base URL (example: https://zenmux.ai/api/v1)",
    )
    parser.add_argument(
        "--log-jsonl",
        required=True,
        help="JSONL output file for tap exchanges",
    )
    parser.add_argument(
        "--api-key-env",
        default="MODEIO_TAP_UPSTREAM_API_KEY",
        help="Env var name used to inject Authorization Bearer token to upstream",
    )
    parser.add_argument(
        "--upstream-timeout-seconds",
        type=int,
        default=120,
        help="Upstream request timeout seconds",
    )
    parser.add_argument(
        "--body-preview-limit",
        type=int,
        default=4000,
        help="Max UTF-8 chars kept in JSONL bodyPreview fields",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logger = JsonlLogger(Path(args.log_jsonl).expanduser())
    handler = _build_handler(
        target_base_url=args.target_base_url,
        logger=logger,
        api_key_env=args.api_key_env,
        upstream_timeout_seconds=args.upstream_timeout_seconds,
        body_preview_limit=args.body_preview_limit,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    host, port = server.server_address
    print(
        f"upstream-tap-proxy listening on http://{host}:{port} -> {args.target_base_url}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
