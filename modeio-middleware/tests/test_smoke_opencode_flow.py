#!/usr/bin/env python3

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request as urllib_request

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"
HELPERS_DIR = REPO_ROOT / "modeio-middleware" / "tests" / "helpers"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(HELPERS_DIR))

import setup_middleware_gateway as setup_gateway  # noqa: E402
from gateway_harness import UpstreamStub, completion_payload, responses_payload  # noqa: E402
from gateway_harness import GatewayStub  # noqa: E402


def _post_json(base_url: str, path: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        f"{base_url}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib_request.urlopen(req, timeout=10) as resp:
        data = resp.read().decode("utf-8")
        return resp.status, dict(resp.headers.items()), json.loads(data)


def _post_stream(base_url: str, path: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        f"{base_url}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib_request.urlopen(req, timeout=10) as resp:
        lines = []
        for _ in range(30):
            line = resp.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace")
            lines.append(decoded)
            if "[DONE]" in decoded:
                break
        return resp.status, dict(resp.headers.items()), "".join(lines)


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

        upstream = UpstreamStub(response_factory=response_factory, stream_factory=stream_factory)
        gateway = None
        upstream.start()
        try:
            gateway = GatewayStub(upstream.base_url)
            gateway.start()

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

                chat_status, chat_headers, chat_payload = _post_json(
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

                responses_status, responses_headers, responses_payload_data = _post_json(
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

                stream_status, stream_headers, stream_text = _post_stream(
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
            upstream.stop()


if __name__ == "__main__":
    unittest.main()
