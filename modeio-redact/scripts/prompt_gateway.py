#!/usr/bin/env python3
"""
Local prompt shield gateway for OpenAI-compatible chat completions.

This gateway is intended for Codex CLI and OpenCode local routing:
  client -> localhost gateway -> shield -> upstream LLM -> unshield -> client

v1 scope:
- Endpoint: POST /v1/chat/completions
- Non-streaming requests only
- Text content shielding/unshielding for OpenAI-style message payloads
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Sequence, Tuple

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

        @staticmethod
        def post(url: str, headers: Optional[Dict[str, str]] = None, json: Optional[Dict[str, Any]] = None, timeout: int = 60):
            payload = b""
            if json is not None:
                payload = json_module.dumps(json).encode("utf-8")
            request = urllib.request.Request(url, data=payload, headers=headers or {}, method="POST")

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

from detect_local import detect_sensitive_local
from map_store import MapStoreError, save_map

CONTRACT_VERSION = "1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_UPSTREAM_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = 60
DEFAULT_UPSTREAM_API_KEY_ENV = "MODEIO_GATEWAY_UPSTREAM_API_KEY"
DEFAULT_POLICY = "strict"
TEXT_PART_TYPES = {"text", "input_text", "output_text"}


class GatewayError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class GatewayConfig:
    upstream_url: str
    upstream_timeout_seconds: int = DEFAULT_UPSTREAM_TIMEOUT_SECONDS
    upstream_api_key_env: str = DEFAULT_UPSTREAM_API_KEY_ENV
    default_policy: str = DEFAULT_POLICY


@dataclass
class ModeioOptions:
    policy: str
    allow_degraded_unshield: bool


@dataclass
class ShieldResult:
    payload: Dict[str, Any]
    entries: List[Dict[str, str]]
    redaction_count: int
    raw_segments: List[str]
    shielded_segments: List[str]


def _new_request_id() -> str:
    return f"req_{secrets.token_hex(8)}"


def _bool_to_header(value: bool) -> str:
    return "true" if value else "false"


def _contract_headers(
    request_id: str,
    *,
    shielded: bool,
    redaction_count: int,
    degraded: str,
    upstream_called: bool,
) -> Dict[str, str]:
    return {
        "x-modeio-contract-version": CONTRACT_VERSION,
        "x-modeio-request-id": request_id,
        "x-modeio-shielded": _bool_to_header(shielded),
        "x-modeio-redaction-count": str(max(0, int(redaction_count))),
        "x-modeio-degraded": degraded,
        "x-modeio-upstream-called": _bool_to_header(upstream_called),
    }


def _error_payload(request_id: str, code: str, message: str, retryable: bool) -> Dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": "modeio_error",
            "code": code,
            "request_id": request_id,
            "retryable": bool(retryable),
        }
    }


def _safe_json_dumps(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _normalize_modeio_options(body: Dict[str, Any]) -> ModeioOptions:
    raw = body.pop("modeio", None)
    if raw is None:
        return ModeioOptions(policy=DEFAULT_POLICY, allow_degraded_unshield=True)
    if not isinstance(raw, dict):
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "field 'modeio' must be an object")

    policy = str(raw.get("policy", DEFAULT_POLICY)).strip().lower()
    if policy != "strict":
        raise GatewayError(
            400,
            "MODEIO_POLICY_UNSUPPORTED",
            "only modeio.policy='strict' is supported in v1",
        )

    allow_degraded = raw.get("allow_degraded_unshield", True)
    if not isinstance(allow_degraded, bool):
        raise GatewayError(
            400,
            "MODEIO_VALIDATION_ERROR",
            "field 'modeio.allow_degraded_unshield' must be boolean",
        )
    return ModeioOptions(policy=policy, allow_degraded_unshield=allow_degraded)


def _normalize_entity_type(raw: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "_", (raw or "UNKNOWN").upper())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "UNKNOWN"


def _make_signed_token(
    *,
    secret: bytes,
    request_id: str,
    entity_type: str,
    index: int,
    original: str,
) -> str:
    entity_tag = _normalize_entity_type(entity_type)
    digest_source = f"{request_id}|{entity_tag}|{index}|{original}".encode("utf-8")
    signature = hmac.new(secret, digest_source, hashlib.sha256).hexdigest()[:10].upper()
    return f"__MIO_{entity_tag}_{index}_{signature}__"


def _replace_with_entries(text: str, entries: Sequence[Dict[str, str]]) -> Tuple[str, int]:
    restored = text
    replaced = 0
    sorted_entries = sorted(entries, key=lambda item: len(item["placeholder"]), reverse=True)
    for item in sorted_entries:
        placeholder = item["placeholder"]
        original = item["original"]
        if not placeholder:
            continue
        count = restored.count(placeholder)
        if count <= 0:
            continue
        restored = restored.replace(placeholder, original)
        replaced += count
    return restored, replaced


def _shield_text(
    *,
    text: str,
    request_id: str,
    secret: bytes,
    entries_by_identity: Dict[Tuple[str, str], str],
    entries: List[Dict[str, str]],
    type_counters: Dict[str, int],
) -> Tuple[str, int]:
    detection = detect_sensitive_local(text)
    sanitized = detection.get("sanitizedText", text)
    if not isinstance(sanitized, str):
        raise GatewayError(
            424,
            "MODEIO_SHIELD_FAILED",
            "shielding failed: detector produced non-string sanitizedText",
        )

    items = detection.get("items", [])
    if not isinstance(items, list) or not items:
        return sanitized, 0

    placeholder_to_token: Dict[str, str] = {}
    replaced_occurrences = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        source_placeholder = item.get("maskedValue")
        original = item.get("value")
        if not isinstance(source_placeholder, str) or not source_placeholder:
            continue
        if not isinstance(original, str) or not original:
            continue

        entity_type = _normalize_entity_type(str(item.get("type", "UNKNOWN")))
        identity_key = (entity_type, original)
        token = entries_by_identity.get(identity_key)
        if token is None:
            index = type_counters.get(entity_type, 0) + 1
            type_counters[entity_type] = index
            token = _make_signed_token(
                secret=secret,
                request_id=request_id,
                entity_type=entity_type,
                index=index,
                original=original,
            )
            entries_by_identity[identity_key] = token
            entries.append(
                {
                    "placeholder": token,
                    "original": original,
                    "type": entity_type,
                }
            )
        placeholder_to_token[source_placeholder] = token

    for source_placeholder in sorted(placeholder_to_token.keys(), key=len, reverse=True):
        token = placeholder_to_token[source_placeholder]
        count = sanitized.count(source_placeholder)
        if count <= 0:
            continue
        sanitized = sanitized.replace(source_placeholder, token)
        replaced_occurrences += count

    return sanitized, replaced_occurrences


def _validate_and_shield_payload(
    body: Dict[str, Any],
    *,
    request_id: str,
    secret: bytes,
) -> ShieldResult:
    if not isinstance(body, dict):
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "request body must be a JSON object")

    model = body.get("model")
    if not isinstance(model, str) or not model.strip():
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "field 'model' must be a non-empty string")

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "field 'messages' must be a non-empty array")

    stream_flag = body.get("stream", False)
    if stream_flag is True:
        raise GatewayError(
            400,
            "MODEIO_STREAM_UNSUPPORTED",
            "stream=true is not supported by modeio prompt gateway v1",
        )

    sanitized_payload = copy.deepcopy(body)
    sanitized_messages = sanitized_payload.get("messages")
    if not isinstance(sanitized_messages, list):
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "field 'messages' must be an array")

    entries_by_identity: Dict[Tuple[str, str], str] = {}
    entries: List[Dict[str, str]] = []
    type_counters: Dict[str, int] = {}
    redaction_count = 0
    raw_segments: List[str] = []
    shielded_segments: List[str] = []

    for idx, message in enumerate(sanitized_messages):
        if not isinstance(message, dict):
            raise GatewayError(
                422,
                "MODEIO_UNSUPPORTED_MESSAGE_CONTENT",
                f"messages[{idx}] must be an object",
            )

        content = message.get("content")
        if content is None:
            continue

        if isinstance(content, str):
            raw_segments.append(content)
            sanitized_text, replaced = _shield_text(
                text=content,
                request_id=request_id,
                secret=secret,
                entries_by_identity=entries_by_identity,
                entries=entries,
                type_counters=type_counters,
            )
            message["content"] = sanitized_text
            shielded_segments.append(sanitized_text)
            redaction_count += replaced
            continue

        if isinstance(content, list):
            for part_idx, part in enumerate(content):
                if not isinstance(part, dict):
                    raise GatewayError(
                        422,
                        "MODEIO_UNSUPPORTED_MESSAGE_CONTENT",
                        f"messages[{idx}].content[{part_idx}] must be an object",
                    )
                part_type = part.get("type")
                if part_type not in TEXT_PART_TYPES:
                    continue
                part_text = part.get("text")
                if not isinstance(part_text, str):
                    raise GatewayError(
                        422,
                        "MODEIO_UNSUPPORTED_MESSAGE_CONTENT",
                        f"messages[{idx}].content[{part_idx}].text must be a string",
                    )

                raw_segments.append(part_text)
                sanitized_text, replaced = _shield_text(
                    text=part_text,
                    request_id=request_id,
                    secret=secret,
                    entries_by_identity=entries_by_identity,
                    entries=entries,
                    type_counters=type_counters,
                )
                part["text"] = sanitized_text
                shielded_segments.append(sanitized_text)
                redaction_count += replaced
            continue

        raise GatewayError(
            422,
            "MODEIO_UNSUPPORTED_MESSAGE_CONTENT",
            f"messages[{idx}].content must be string, list, or null",
        )

    return ShieldResult(
        payload=sanitized_payload,
        entries=entries,
        redaction_count=redaction_count,
        raw_segments=raw_segments,
        shielded_segments=shielded_segments,
    )


def _persist_map_if_available(result: ShieldResult) -> Optional[Dict[str, Any]]:
    if not result.entries:
        return None

    raw_joined = "\n\n".join(result.raw_segments)
    shielded_joined = "\n\n".join(result.shielded_segments)
    if not raw_joined.strip() or not shielded_joined.strip():
        return None

    try:
        return save_map(
            raw_input=raw_joined,
            anonymized_content=shielded_joined,
            entries=result.entries,
            level="lite",
            source_mode="gateway-local",
        )
    except MapStoreError:
        return None


def _unshield_content(content: Any, entries: Sequence[Dict[str, str]]) -> Tuple[Any, int]:
    if content is None:
        return content, 0
    if isinstance(content, str):
        return _replace_with_entries(content, entries)
    if isinstance(content, list):
        updated = copy.deepcopy(content)
        total = 0
        for idx, part in enumerate(updated):
            if not isinstance(part, dict):
                raise ValueError(f"response content part at index {idx} must be an object")
            if part.get("type") not in TEXT_PART_TYPES:
                continue
            text = part.get("text")
            if not isinstance(text, str):
                raise ValueError(f"response content part text at index {idx} must be a string")
            restored, count = _replace_with_entries(text, entries)
            part["text"] = restored
            total += count
        return updated, total
    raise ValueError("response message content must be string, list, or null")


def _unshield_chat_response(
    payload: Dict[str, Any], entries: Sequence[Dict[str, str]]
) -> Tuple[Dict[str, Any], int]:
    if not entries:
        return payload, 0
    if not isinstance(payload, dict):
        raise ValueError("upstream response body must be an object")

    result = copy.deepcopy(payload)
    choices = result.get("choices")
    if choices is None:
        return result, 0
    if not isinstance(choices, list):
        raise ValueError("upstream response field 'choices' must be an array")

    total = 0
    for idx, choice in enumerate(choices):
        if not isinstance(choice, dict):
            raise ValueError(f"upstream response choices[{idx}] must be an object")
        message = choice.get("message")
        if message is None:
            continue
        if not isinstance(message, dict):
            raise ValueError(f"upstream response choices[{idx}].message must be an object")
        content = message.get("content")
        restored, replaced = _unshield_content(content, entries)
        message["content"] = restored
        total += replaced

    return result, total


def _build_upstream_headers(
    incoming_headers: Dict[str, str],
    *,
    upstream_api_key_env: str,
) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    authorization = incoming_headers.get("authorization") or incoming_headers.get("Authorization")
    if not authorization:
        env_key = os.environ.get(upstream_api_key_env, "").strip()
        if env_key:
            authorization = f"Bearer {env_key}"
    if authorization:
        headers["Authorization"] = authorization
    return headers


def _forward_upstream(
    config: GatewayConfig,
    payload: Dict[str, Any],
    incoming_headers: Dict[str, str],
) -> Dict[str, Any]:
    headers = _build_upstream_headers(
        incoming_headers,
        upstream_api_key_env=config.upstream_api_key_env,
    )

    try:
        response = requests.post(
            config.upstream_url,
            headers=headers,
            json=payload,
            timeout=config.upstream_timeout_seconds,
        )
    except requests.RequestException as error:
        raise GatewayError(
            502,
            "MODEIO_UPSTREAM_REQUEST_FAILED",
            f"upstream request failed: {type(error).__name__}",
            retryable=True,
        ) from error

    if response.status_code >= 400:
        retryable = response.status_code >= 500
        raise GatewayError(
            502,
            "MODEIO_UPSTREAM_ERROR",
            f"upstream returned status {response.status_code}",
            retryable=retryable,
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise GatewayError(
            502,
            "MODEIO_UPSTREAM_INVALID_JSON",
            "upstream response is not valid JSON",
            retryable=False,
        ) from error

    if not isinstance(payload, dict):
        raise GatewayError(
            502,
            "MODEIO_UPSTREAM_INVALID_JSON",
            "upstream response root must be an object",
            retryable=False,
        )
    return payload


def _read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    raw_length = handler.headers.get("Content-Length")
    if raw_length is None:
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "missing Content-Length header")

    try:
        length = int(raw_length)
    except ValueError as error:
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "invalid Content-Length header") from error

    if length <= 0:
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "request body must not be empty")

    body_bytes = handler.rfile.read(length)
    try:
        parsed = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "request body must be valid JSON") from error

    if not isinstance(parsed, dict):
        raise GatewayError(400, "MODEIO_VALIDATION_ERROR", "request body must be a JSON object")
    return parsed


def build_handler(config: GatewayConfig, *, hmac_secret: bytes):
    class PromptGatewayHandler(BaseHTTPRequestHandler):
        server_version = "ModeioPromptGateway/1.0"
        protocol_version = "HTTP/1.1"

        def _send_json(self, status: int, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> None:
            body = _safe_json_dumps(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if headers:
                for name, value in headers.items():
                    self.send_header(name, str(value))
            self.end_headers()
            self.wfile.write(body)

        def _send_gateway_error(
            self,
            request_id: str,
            error: GatewayError,
            *,
            upstream_called: bool,
            shielded: bool,
            redaction_count: int,
            degraded: str,
        ) -> None:
            payload = _error_payload(
                request_id=request_id,
                code=error.code,
                message=error.message,
                retryable=error.retryable,
            )
            headers = _contract_headers(
                request_id,
                shielded=shielded,
                redaction_count=redaction_count,
                degraded=degraded,
                upstream_called=upstream_called,
            )
            self._send_json(error.status, payload, headers)

        def do_GET(self) -> None:
            if self.path != "/healthz":
                self._send_json(404, {"error": {"message": "not found"}})
                return

            payload = {
                "ok": True,
                "service": "modeio-redact-prompt-gateway",
                "version": CONTRACT_VERSION,
                "upstream": {"configured": bool(config.upstream_url)},
                "policy": config.default_policy,
            }
            self._send_json(200, payload)

        def do_POST(self) -> None:
            request_id = _new_request_id()
            upstream_called = False
            shielded = False
            redaction_count = 0
            degraded = "none"

            if self.path != "/v1/chat/completions":
                error = GatewayError(404, "MODEIO_ROUTE_NOT_FOUND", "route not found")
                self._send_gateway_error(
                    request_id,
                    error,
                    upstream_called=upstream_called,
                    shielded=shielded,
                    redaction_count=redaction_count,
                    degraded=degraded,
                )
                return

            try:
                body = _read_json_body(self)
                options = _normalize_modeio_options(body)
                if options.policy != "strict":
                    raise GatewayError(
                        400,
                        "MODEIO_POLICY_UNSUPPORTED",
                        "only modeio.policy='strict' is supported in v1",
                    )

                shield_result = _validate_and_shield_payload(
                    body,
                    request_id=request_id,
                    secret=hmac_secret,
                )
                shielded = bool(shield_result.entries)
                redaction_count = shield_result.redaction_count

                map_ref = _persist_map_if_available(shield_result)
                upstream_payload = shield_result.payload

                upstream_response = _forward_upstream(
                    config,
                    payload=upstream_payload,
                    incoming_headers=dict(self.headers.items()),
                )
                upstream_called = True

                try:
                    response_payload, _ = _unshield_chat_response(upstream_response, shield_result.entries)
                except ValueError as error:
                    if options.allow_degraded_unshield:
                        degraded = "unshield_failed"
                        response_payload = upstream_response
                    else:
                        raise GatewayError(
                            502,
                            "MODEIO_UNSHIELD_FAILED",
                            f"failed to unshield upstream response: {error}",
                            retryable=False,
                        ) from error

                headers = _contract_headers(
                    request_id,
                    shielded=shielded,
                    redaction_count=redaction_count,
                    degraded=degraded,
                    upstream_called=upstream_called,
                )
                if map_ref:
                    headers["x-modeio-map-id"] = map_ref["mapId"]
                self._send_json(200, response_payload, headers)
            except GatewayError as error:
                self._send_gateway_error(
                    request_id,
                    error,
                    upstream_called=upstream_called,
                    shielded=shielded,
                    redaction_count=redaction_count,
                    degraded=degraded,
                )
            except Exception:
                error = GatewayError(
                    503,
                    "MODEIO_INTERNAL_ERROR",
                    "unexpected internal error",
                    retryable=False,
                )
                self._send_gateway_error(
                    request_id,
                    error,
                    upstream_called=upstream_called,
                    shielded=shielded,
                    redaction_count=redaction_count,
                    degraded=degraded,
                )

        def log_message(self, format: str, *args: Any) -> None:
            message = format % args
            sys.stderr.write(f"[modeio-gateway] {self.address_string()} {message}\n")

    return PromptGatewayHandler


def create_server(host: str, port: int, config: GatewayConfig) -> ThreadingHTTPServer:
    secret_value = os.environ.get("MODEIO_GATEWAY_HMAC_KEY", "").strip()
    if secret_value:
        hmac_secret = secret_value.encode("utf-8")
    else:
        hmac_secret = secrets.token_hex(32).encode("utf-8")

    handler = build_handler(config, hmac_secret=hmac_secret)
    return ThreadingHTTPServer((host, port), handler)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local prompt shield gateway for OpenAI-compatible chat completions. "
            "Recommended for Codex CLI and OpenCode base-url routing."
        )
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Listen host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Listen port (default: {DEFAULT_PORT})")
    parser.add_argument(
        "--upstream-url",
        default=os.environ.get("MODEIO_GATEWAY_UPSTREAM_URL", DEFAULT_UPSTREAM_URL),
        help=(
            "Upstream OpenAI-compatible chat completions endpoint "
            f"(default env MODEIO_GATEWAY_UPSTREAM_URL or {DEFAULT_UPSTREAM_URL})"
        ),
    )
    parser.add_argument(
        "--upstream-timeout",
        type=int,
        default=DEFAULT_UPSTREAM_TIMEOUT_SECONDS,
        help=f"Upstream request timeout in seconds (default: {DEFAULT_UPSTREAM_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--upstream-api-key-env",
        default=DEFAULT_UPSTREAM_API_KEY_ENV,
        help=(
            "Environment variable name containing upstream API key when incoming request has "
            "no Authorization header"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    config = GatewayConfig(
        upstream_url=args.upstream_url,
        upstream_timeout_seconds=args.upstream_timeout,
        upstream_api_key_env=args.upstream_api_key_env,
    )
    server = create_server(args.host, args.port, config)

    listen_host, listen_port = server.server_address
    print(
        f"Modeio prompt gateway listening on http://{listen_host}:{listen_port} "
        f"-> upstream {config.upstream_url}",
        file=sys.stderr,
    )
    print(
        "Contract: POST /v1/chat/completions (stream=false only), GET /healthz",
        file=sys.stderr,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down gateway...", file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
