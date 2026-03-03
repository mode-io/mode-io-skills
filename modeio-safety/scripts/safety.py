#!/usr/bin/env python3
"""
Modeio AI Safety Skill - instruction risk analysis.
Evaluates instructions for destructive operations, prompt injection,
irreversible actions, and compliance violations via the Modeio safety API.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict

import requests

# Backend API URL, overridable via SAFETY_API_URL environment variable
URL = os.environ.get("SAFETY_API_URL", "https://safety-cf.modeio.ai/api/cf/safety")

TOOL_NAME = "modeio-safety"

MAX_RETRIES = 2
RETRY_BACKOFF = 1.0  # seconds; doubles each retry


def _post_with_retry(url, json_payload, timeout=60):
    """POST with simple exponential-backoff retry on transient failures."""
    last_exc = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.post(url, json=json_payload, timeout=timeout)
            if resp.status_code in (502, 503, 504) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (2 ** attempt))
                continue
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (2 ** attempt))
                continue
            raise
    # Should not reach here, but raise last exception if it does
    raise last_exc  # type: ignore[misc]


def detect_safety(instruction: str, context: str = None, target: str = None) -> dict:
    """
    Call the Modeio safety backend and return the full response JSON.
    Response includes: approved, risk_level, risk_types, concerns, recommendation, etc.
    """
    payload = {"instruction": instruction}
    if context:
        payload["context"] = context
    if target:
        payload["target"] = target
    resp = _post_with_retry(URL, json_payload=payload)
    return resp.json()


def _success_envelope(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "success": True,
        "tool": TOOL_NAME,
        "mode": "api",
        "data": data,
    }


def _error_envelope(
    error_type: str,
    message: str,
    status_code: int = None,
    details: Dict[str, Any] = None,
) -> Dict[str, Any]:
    error: Dict[str, Any] = {
        "type": error_type,
        "message": message,
    }
    if status_code is not None:
        error["status_code"] = status_code
    if details is not None:
        error["details"] = details
    return {
        "success": False,
        "tool": TOOL_NAME,
        "mode": "api",
        "error": error,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate instructions for safety risks (destructive ops, risk level, reversibility, etc.)"
    )
    parser.add_argument("-i", "--input", type=str, required=True, help="Instruction or operation description to evaluate")
    parser.add_argument("-c", "--context", type=str, default=None, help="Execution context (optional)")
    parser.add_argument("-t", "--target", type=str, default=None, help="Operation target such as file path, table name, or service (optional)")
    parser.add_argument("--json", action="store_true", help="Output unified JSON contract for machine consumption.")
    args = parser.parse_args()

    raw_input = args.input

    if not raw_input or not raw_input.strip():
        msg = "--input must not be empty."
        if args.json:
            print(json.dumps(_error_envelope(error_type="validation_error", message=msg), ensure_ascii=False))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)

    try:
        result = detect_safety(
            instruction=raw_input,
            context=args.context,
            target=args.target,
        )
    except requests.RequestException as e:
        response = getattr(e, "response", None)
        status_code = getattr(response, "status_code", None)
        if args.json:
            print(json.dumps(
                _error_envelope(
                    error_type="network_error",
                    message=f"safety request failed: {type(e).__name__}",
                    status_code=status_code,
                ),
                ensure_ascii=False,
            ))
        else:
            print(f"Error: safety request failed. url={URL}", file=sys.stderr)
            if status_code is not None:
                print(f"Error: status_code={status_code}", file=sys.stderr)
            print(f"Error: exception={type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    if result.get("error"):
        if args.json:
            print(json.dumps(
                _error_envelope(
                    error_type="api_error",
                    message=str(result.get("error")),
                    details=result,
                ),
                ensure_ascii=False,
            ))
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
            print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(_success_envelope(result), ensure_ascii=False))
        return

    print("Status: success", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
