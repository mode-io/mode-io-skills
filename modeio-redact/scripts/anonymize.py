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
import time
from typing import Any, Dict, Optional

try:
    import requests
except ModuleNotFoundError:
    class _RequestsShim:
        class RequestException(Exception):
            pass

        class ConnectionError(RequestException):
            pass

        class Timeout(RequestException):
            pass

        @staticmethod
        def post(*_args, **_kwargs):
            raise _RequestsShim.RequestException(
                "requests package is required for api-backed anonymization levels"
            )

    requests = _RequestsShim()

from detect_local import detect_sensitive_local
from input_source import resolve_input_source
from map_store import MapStoreError, normalize_mapping_entries, save_map

# Backend API URL, overridable via ANONYMIZE_API_URL environment variable
URL = os.environ.get("ANONYMIZE_API_URL", "https://safety-cf.modeio.ai/api/cf/anonymize")

HEADERS = {"Content-Type": "application/json"}

VALID_LEVELS = ("lite", "dynamic", "strict", "crossborder")

TOOL_NAME = "modeio-redact"

MAX_RETRIES = 2
RETRY_BACKOFF = 1.0  # seconds; doubles each retry


def _post_with_retry(url, headers, json_payload, timeout=60):
    """POST with simple exponential-backoff retry on transient failures."""
    last_exc = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            resp = requests.post(url, headers=headers, json=json_payload, timeout=timeout)
            if resp.status_code in (502, 503, 504) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (2 ** attempt))
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exc = e
            if isinstance(e, (requests.ConnectionError, requests.Timeout)) and attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (2 ** attempt))
                continue
            raise
    # Should not reach here, but raise last exception if it does
    raise last_exc  # type: ignore[misc]


def anonymize(
    raw_input: str,
    level: str = "dynamic",
    sender_code: str = None,
    recipient_code: str = None,
    input_type: str = "text",
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
        "inputType": input_type,
        "level": level,
    }
    if sender_code:
        payload["senderCode"] = sender_code
    if recipient_code:
        payload["recipientCode"] = recipient_code
    resp = _post_with_retry(URL, headers=HEADERS, json_payload=payload)
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


def _append_warning(data: Dict[str, Any], code: str, message: str) -> None:
    warnings = data.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
        data["warnings"] = warnings
    warnings.append({"code": code, "message": message})


def _maybe_save_map(
    raw_input: str,
    level: str,
    mode: str,
    data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    entries = normalize_mapping_entries(data)
    if not entries:
        return None

    anonymized_content = data.get("anonymizedContent")
    if not isinstance(anonymized_content, str):
        return None

    map_ref = save_map(
        raw_input=raw_input,
        anonymized_content=anonymized_content,
        entries=entries,
        level=level,
        source_mode=mode,
    )
    data["mapRef"] = map_ref
    return map_ref


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Anonymize text/JSON or a .txt/.md file path. "
            "`lite` runs locally; other levels call the Modeio API."
        )
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        required=True,
        help="Raw content to anonymize, or a .txt/.md file path.",
    )
    parser.add_argument(
        "--level",
        type=str,
        default="dynamic",
        choices=VALID_LEVELS,
        help="Anonymization level (default: dynamic). `lite` runs local regex with no network call.",
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

    mode = "local-regex" if args.level == "lite" else "api"

    try:
        raw_input, input_type = resolve_input_source(args.input)
    except ValueError as exc:
        if args.json:
            print(json.dumps(
                _error_envelope(
                    level=args.level,
                    mode=mode,
                    error_type="validation_error",
                    message=str(exc),
                ),
                ensure_ascii=False,
            ))
        else:
            print(f"Error: {exc}", file=sys.stderr)
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

    try:
        result = anonymize(
            raw_input,
            level=args.level,
            sender_code=sender_code,
            recipient_code=recipient_code,
            input_type=input_type,
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

    map_ref = None
    try:
        map_ref = _maybe_save_map(raw_input=raw_input, level=args.level, mode=mode, data=data)
    except MapStoreError as error:
        _append_warning(
            data,
            code="map_persist_failed",
            message=str(error),
        )

    if args.json:
        print(json.dumps(_success_envelope(level=args.level, mode=mode, data=data), ensure_ascii=False))
        return

    print("Status: success", file=sys.stderr)
    if mode == "local-regex":
        print("mode: local-regex", file=sys.stderr)
    print("hasPII:", has_pii, file=sys.stderr)
    if map_ref:
        print(f"mapId: {map_ref['mapId']}", file=sys.stderr)
    warnings = data.get("warnings")
    if isinstance(warnings, list):
        for warning in warnings:
            if isinstance(warning, dict):
                print(f"Warning: {warning.get('code', 'warning')}: {warning.get('message', '')}", file=sys.stderr)
    print(anonymized)


if __name__ == "__main__":
    main()
