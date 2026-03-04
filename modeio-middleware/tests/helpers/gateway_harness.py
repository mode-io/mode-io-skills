#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import middleware_gateway as gateway


def completion_payload(content: str) -> Dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
    }


def responses_payload(content: str) -> Dict[str, Any]:
    return {
        "id": "resp_test",
        "object": "response",
        "model": "test-model",
        "output_text": content,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content}],
            }
        ],
    }


class UpstreamStub:
    def __init__(self, response_factory, status: int = 200, stream_factory=None):
        self.response_factory = response_factory
        self.status = status
        self.stream_factory = stream_factory
        self.requests = []
        self._server = None
        self._thread = None
        self.base_url = ""

    def start(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                content_length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode("utf-8")) if body else {}
                owner.requests.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers.items()),
                        "body": payload,
                    }
                )

                if payload.get("stream") is True and owner.stream_factory is not None:
                    self.send_response(owner.status)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()

                    events = owner.stream_factory(self.path, payload)
                    for event in events:
                        if isinstance(event, bytes):
                            chunk = event
                        elif event == "[DONE]":
                            chunk = b"data: [DONE]\n\n"
                        elif isinstance(event, dict):
                            chunk = b"data: " + json.dumps(event).encode("utf-8") + b"\n\n"
                        else:
                            chunk = str(event).encode("utf-8")
                            if not chunk.endswith(b"\n\n"):
                                chunk += b"\n\n"

                        self.wfile.write(chunk)
                        self.wfile.flush()
                    return

                response_payload = owner.response_factory(self.path, payload)
                response_body = json.dumps(response_payload).encode("utf-8")

                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def log_message(self, _format, *_args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self._server.server_address
        self.base_url = f"http://{host}:{port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class GatewayStub:
    def __init__(self, upstream_base_url: str, *, plugins=None, profiles=None):
        self._server = None
        self._thread = None
        self.base_url = ""
        self.config = gateway.GatewayRuntimeConfig(
            upstream_chat_completions_url=f"{upstream_base_url}/v1/chat/completions",
            upstream_responses_url=f"{upstream_base_url}/v1/responses",
            upstream_timeout_seconds=5,
            upstream_api_key_env="MODEIO_GATEWAY_UPSTREAM_API_KEY",
            default_profile="dev",
            profiles=profiles
            or {
                "dev": {
                    "on_plugin_error": "warn",
                    "plugins": ["guardrail", "redact"],
                }
            },
            plugins=plugins
            or {
                "guardrail": {
                    "enabled": False,
                    "module": "modeio_middleware.plugins.guardrail",
                },
                "redact": {
                    "enabled": False,
                    "module": "modeio_middleware.plugins.redact",
                },
            },
        )

    def start(self):
        self._server = gateway.create_server("127.0.0.1", 0, self.config)
        host, port = self._server.server_address
        self.base_url = f"http://{host}:{port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
