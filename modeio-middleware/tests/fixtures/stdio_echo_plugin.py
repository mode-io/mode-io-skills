#!/usr/bin/env python3

from __future__ import annotations

import json
import sys


def _write_response(request_id, result=None, error=None):
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


def _decision_for_invoke(params):
    hook = str(params.get("hook", "")).strip()
    hook_input = params.get("input", {})
    plugin_config = hook_input.get("plugin_config", {})
    behavior = str(plugin_config.get("behavior", "patch")).strip().lower()

    if hook != "pre.request":
        return {
            "decision": {
                "action": "pass",
            }
        }

    if behavior == "block":
        return {
            "decision": {
                "action": "block",
                "message": "blocked by stdio fixture",
            }
        }

    if behavior == "annotate":
        return {
            "decision": {
                "action": "annotate",
                "message": "stdio fixture annotation",
                "findings": [
                    {
                        "class": "external_policy",
                        "severity": "low",
                        "confidence": 1.0,
                        "reason": "annotation from stdio fixture",
                        "evidence": [],
                    }
                ],
            }
        }

    replacement = str(plugin_config.get("rewrite_to", "patched-by-stdio"))
    return {
        "decision": {
            "action": "patch",
            "patch_target": "request_body",
            "patches": [
                {
                    "op": "replace",
                    "path": "/messages/0/content",
                    "value": replacement,
                }
            ],
            "message": "stdio fixture requested patch",
        }
    }


def main():
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
            _write_response(
                request_id,
                result={
                    "protocol_version": "1.0",
                    "name": "tests/stdio-echo-plugin",
                },
            )
            continue

        if method == "modeio.invoke":
            _write_response(request_id, result=_decision_for_invoke(params))
            continue

        if method == "modeio.shutdown":
            _write_response(request_id, result={"ok": True})
            return 0

        _write_response(
            request_id,
            error={
                "code": -32601,
                "message": f"unsupported method: {method}",
            },
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
