#!/usr/bin/env python3
"""
Modeio AI Anonymization Skill.

- `lite` level runs local regex anonymization (no network call).
- Other levels call the Modeio anonymization API.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict

import requests

from detect_local import detect_sensitive_local

# Backend API URL, overridable via ANONYMIZE_API_URL environment variable
URL = os.environ.get("ANONYMIZE_API_URL", "https://safety-cf.modeio.ai/api/cf/anonymize")

HEADERS = {"Content-Type": "application/json"}

VALID_LEVELS = ("lite", "dynamic", "strict", "crossborder")

TOOL_NAME = "modeio-anonymization"


def anonymize(
    raw_input: str,
    level: str = "crossborder",
    sender_code: str = None,
    recipient_code: str = None,
) -> dict:
    if level == "lite":
        local_result = detect_sensitive_local(raw_input)
        return {
            "success": True,
            "data": {
                "anonymizedContent": local_result.get("sanitizedText", ""),
                "hasPII": bool(local_result.get("items")),
                "mode": "local-regex",
                "localDetection": local_result,
            },
        }

    payload = {
        "input": raw_input,
        "inputType": "text",
        "level": level,
    }
    if sender_code:
        payload["senderCode"] = sender_code
    if recipient_code:
        payload["recipientCode"] = recipient_code
    resp = requests.post(URL, headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _success_envelope(level: str, mode: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "success": True,
        "tool": TOOL_NAME,
        "mode": mode,
        "level": level,
        "data": data,
    }


def _error_envelope(
    level: str,
    mode: str,
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
        "mode": mode,
        "level": level,
        "error": error,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Anonymize text or JSON. `lite` runs locally; other levels call the Modeio API."
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        required=True,
        help="Raw content to anonymize (text or JSON string).",
    )
    parser.add_argument(
        "--level",
        type=str,
        default="crossborder",
        choices=VALID_LEVELS,
        help="Anonymization level (default: crossborder). `lite` runs local regex with no network call.",
    )
    parser.add_argument(
        "--sender-code",
        type=str,
        default=None,
        help="Sender jurisdiction code, required for crossborder level (example: CN SHA).",
    )
    parser.add_argument(
        "--recipient-code",
        type=str,
        default=None,
        help="Recipient jurisdiction code, required for crossborder level (example: US NYC).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output unified JSON contract for machine consumption.",
    )
    args = parser.parse_args()

    raw_input = (args.input or "").strip()

    if not raw_input:
        print("Error: --input must not be empty.", file=sys.stderr)
        sys.exit(2)

    if args.level == "crossborder":
        sender_code = (args.sender_code or "").strip()
        recipient_code = (args.recipient_code or "").strip()
        if not sender_code or not recipient_code:
            msg = "--sender-code and --recipient-code are required when --level is crossborder."
            if args.json:
                print(json.dumps(
                    _error_envelope(
                        level=args.level,
                        mode="api",
                        error_type="validation_error",
                        message=msg,
                    ),
                    ensure_ascii=False,
                ))
            else:
                print(f"Error: {msg}", file=sys.stderr)
            sys.exit(2)
    else:
        sender_code = None
        recipient_code = None

    mode = "local-regex" if args.level == "lite" else "api"

    try:
        result = anonymize(
            raw_input,
            level=args.level,
            sender_code=sender_code,
            recipient_code=recipient_code,
        )
    except requests.RequestException as e:
        response = getattr(e, "response", None)
        status_code = getattr(response, "status_code", None)
        if args.json:
            print(json.dumps(
                _error_envelope(
                    level=args.level,
                    mode=mode,
                    error_type="network_error",
                    message=f"anonymization request failed: {type(e).__name__}",
                    status_code=status_code,
                ),
                ensure_ascii=False,
            ))
        else:
            print(f"Error: anonymization request failed. url={URL}", file=sys.stderr)
            if status_code is not None:
                print(f"Error: status_code={status_code}", file=sys.stderr)
            print(f"Error: exception={type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    if not result.get("success"):
        if args.json:
            print(json.dumps(
                _error_envelope(
                    level=args.level,
                    mode=mode,
                    error_type="api_error",
                    message="anonymization backend returned success=false",
                    details=result,
                ),
                ensure_ascii=False,
            ))
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    data = result.get("data", {})
    anonymized = data.get("anonymizedContent", "")
    has_pii = data.get("hasPII", None)

    if args.json:
        print(json.dumps(_success_envelope(level=args.level, mode=mode, data=data), ensure_ascii=False))
        return

    print("Status: success", file=sys.stderr)
    if mode == "local-regex":
        print("mode: local-regex", file=sys.stderr)
    print("hasPII:", has_pii, file=sys.stderr)
    print(anonymized)


if __name__ == "__main__":
    main()
