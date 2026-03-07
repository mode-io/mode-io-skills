#!/usr/bin/env python3

from __future__ import annotations

import json
import sys


def _reply(request_id, *, result=None, error=None) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
    }
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result or {}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _invoke_decision(params: dict) -> dict:
    hook = str(params.get("hook", "")).strip()
    hook_input = params.get("input", {})

    if hook != "pre.request":
        return {
            "decision": {
                "action": "pass",
            }
        }

    request_body = hook_input.get("request_body", {})
    model = request_body.get("model", "unknown-model")
    return {
        "decision": {
            "action": "annotate",
            "message": f"example external policy observed request for model '{model}'",
            "findings": [
                {
                    "class": "example_external_policy",
                    "severity": "low",
                    "confidence": 1.0,
                    "reason": "shipped example plugin observed a request",
                    "evidence": [f"model={model}"],
                }
            ],
        }
    }


def main() -> int:
    for raw_line in sys.stdin:
        if not raw_line.strip():
            continue

        try:
            request = json.loads(raw_line)
        except ValueError:
            continue

        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}

        if method == "modeio.initialize":
            _reply(
                request_id,
                result={
                    "protocol_version": "1.0",
                    "name": "examples/hello-policy",
                },
            )
            continue

        if method == "modeio.invoke":
            _reply(request_id, result=_invoke_decision(params))
            continue

        if method == "modeio.shutdown":
            _reply(request_id, result={"ok": True})
            return 0

        _reply(
            request_id,
            error={
                "code": -32601,
                "message": f"unsupported method: {method}",
            },
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
