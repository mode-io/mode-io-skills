#!/usr/bin/env python3

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "modeio-middleware"
HELPERS_DIR = REPO_ROOT / "modeio-middleware" / "tests" / "helpers"
sys.path.insert(0, str(PACKAGE_DIR))
sys.path.insert(0, str(HELPERS_DIR))

from modeio_middleware.cli import setup as setup_gateway  # noqa: E402
from gateway_harness import (  # noqa: E402
    completion_payload,
    post_json,
    post_stream,
    responses_payload,
    start_gateway_pair,
)


def _run_setup_json(args):
    out = io.StringIO()
    with redirect_stdout(out):
        code = setup_gateway.main(args)
    return code, json.loads(out.getvalue())


class TestSmokeOpenCodeFlow(unittest.TestCase):
    def test_opencode_setup_apply_route_and_uninstall(self):
        def response_factory(path, payload):
            if path.endswith("/v1/chat/completions"):
                content = ""
                if isinstance(payload.get("messages"), list) and payload["messages"]:
                    first = payload["messages"][0]
                    if isinstance(first, dict):
                        content = str(first.get("content", ""))
                return completion_payload(content)

            if path.endswith("/v1/responses"):
                content = payload.get("input")
                if not isinstance(content, str):
                    content = "responses-ok"
                return responses_payload(content)

            return {"ok": True}

        def stream_factory(path, payload):
            if not path.endswith("/v1/chat/completions"):
                return ["[DONE]"]

            content = "stream"
            if isinstance(payload.get("messages"), list) and payload["messages"]:
                first = payload["messages"][0]
                if isinstance(first, dict) and isinstance(first.get("content"), str):
                    content = first["content"]

            return [
                {
                    "id": "evt1",
                    "object": "chat.completion.chunk",
                    "choices": [{"delta": {"content": content[:4]}}],
                },
                "[DONE]",
            ]

        upstream = None
        gateway = None
        try:
            upstream, gateway = start_gateway_pair(response_factory, stream_factory=stream_factory)

            with TemporaryDirectory() as temp_dir:
                opencode_config = Path(temp_dir) / "opencode.json"
                gateway_base_url = f"{gateway.base_url}/v1"

                apply_code, apply_payload = _run_setup_json(
                    [
                        "--apply-opencode",
                        "--create-opencode-config",
                        "--gateway-base-url",
                        gateway_base_url,
                        "--opencode-config-path",
                        str(opencode_config),
                        "--health-check",
                        "--json",
                    ]
                )
                self.assertEqual(apply_code, 0)
                self.assertTrue(apply_payload["success"])
                self.assertTrue(apply_payload["gateway"]["health"]["ok"])

                config_payload = json.loads(opencode_config.read_text(encoding="utf-8"))
                self.assertEqual(
                    config_payload["provider"]["openai"]["options"]["baseURL"],
                    gateway_base_url,
                )

                chat_status, chat_headers, chat_payload = post_json(
                    gateway.base_url,
                    "/v1/chat/completions",
                    {
                        "model": "gpt-test",
                        "messages": [{"role": "user", "content": "smoke-chat"}],
                        "modeio": {"profile": "dev"},
                    },
                )
                self.assertEqual(chat_status, 200)
                self.assertEqual(chat_payload["choices"][0]["message"]["content"], "smoke-chat")
                self.assertIn("x-modeio-request-id", {k.lower(): v for k, v in chat_headers.items()})

                responses_status, responses_headers, responses_payload_data = post_json(
                    gateway.base_url,
                    "/v1/responses",
                    {
                        "model": "gpt-test",
                        "input": "smoke-responses",
                        "modeio": {"profile": "dev"},
                    },
                )
                self.assertEqual(responses_status, 200)
                self.assertEqual(responses_payload_data["output_text"], "smoke-responses")
                self.assertIn("x-modeio-request-id", {k.lower(): v for k, v in responses_headers.items()})

                stream_status, stream_headers, stream_text = post_stream(
                    gateway.base_url,
                    "/v1/chat/completions",
                    {
                        "model": "gpt-test",
                        "stream": True,
                        "messages": [{"role": "user", "content": "stream-smoke"}],
                        "modeio": {"profile": "dev"},
                    },
                )
                self.assertEqual(stream_status, 200)
                self.assertEqual(
                    {k.lower(): v for k, v in stream_headers.items()}.get("x-modeio-streaming"),
                    "true",
                )
                self.assertIn("[DONE]", stream_text)

                for received in upstream.requests:
                    body = received.get("body")
                    if isinstance(body, dict):
                        self.assertNotIn("modeio", body)

                uninstall_code, uninstall_payload = _run_setup_json(
                    [
                        "--apply-opencode",
                        "--uninstall",
                        "--force-remove-opencode-base-url",
                        "--gateway-base-url",
                        gateway_base_url,
                        "--opencode-config-path",
                        str(opencode_config),
                        "--json",
                    ]
                )
                self.assertEqual(uninstall_code, 0)
                self.assertTrue(uninstall_payload["success"])

                config_after = json.loads(opencode_config.read_text(encoding="utf-8"))
                self.assertNotIn("baseURL", config_after["provider"]["openai"]["options"])
        finally:
            if gateway is not None:
                gateway.stop()
            if upstream is not None:
                upstream.stop()


if __name__ == "__main__":
    unittest.main()
