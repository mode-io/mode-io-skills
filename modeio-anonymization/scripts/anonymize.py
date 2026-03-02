#!/usr/bin/env python3
"""
Modeio AI Anonymization Skill - API-backed PII anonymization.
Calls the Modeio anonymization endpoint to mask PII in text or JSON.
"""

import argparse
import json
import os
import sys

import requests

# Backend API URL, overridable via ANONYMIZE_API_URL environment variable
URL = os.environ.get("ANONYMIZE_API_URL", "https://safety-cf.modeio.ai/api/cf/anonymize")

HEADERS = {"Content-Type": "application/json"}

VALID_LEVELS = ("lite", "dynamic", "strict", "crossborder")
VALID_INPUT_TYPES = ("text", "file")


def anonymize(
    raw_input: str,
    input_type: str = "text",
    level: str = "crossborder",
    sender_code: str = None,
    recipient_code: str = None,
) -> dict:
    payload = {
        "input": raw_input,
        "inputType": input_type,
        "level": level,
    }
    if sender_code:
        payload["senderCode"] = sender_code
    if recipient_code:
        payload["recipientCode"] = recipient_code
    resp = requests.post(URL, headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(
        description="Anonymize text or JSON via the Modeio anonymization API."
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
        help="Anonymization level (default: crossborder).",
    )
    parser.add_argument(
        "--input-type",
        type=str,
        default="text",
        choices=VALID_INPUT_TYPES,
        help="Input content type (default: text).",
    )
    parser.add_argument(
        "--sender-code",
        type=str,
        default="CN SHA",
        help="Sender jurisdiction code, required for crossborder level (default: CN SHA).",
    )
    parser.add_argument(
        "--recipient-code",
        type=str,
        default="US NYC",
        help="Recipient jurisdiction code, required for crossborder level (default: US NYC).",
    )
    args = parser.parse_args()

    raw_input = (args.input or "").strip()

    if not raw_input:
        print("Error: --input must not be empty.", file=sys.stderr)
        sys.exit(2)

    if args.level == "crossborder" and (not args.sender_code or not args.recipient_code):
        print("Error: --sender-code and --recipient-code are required when --level is crossborder.", file=sys.stderr)
        sys.exit(2)

    try:
        result = anonymize(
            raw_input,
            input_type=args.input_type,
            level=args.level,
            sender_code=args.sender_code if args.level == "crossborder" else None,
            recipient_code=args.recipient_code if args.level == "crossborder" else None,
        )
    except requests.RequestException as e:
        response = getattr(e, "response", None)
        status_code = getattr(response, "status_code", None)
        print(f"Error: anonymization request failed. url={URL}", file=sys.stderr)
        if status_code is not None:
            print(f"Error: status_code={status_code}", file=sys.stderr)
        print(f"Error: exception={type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    if not result.get("success"):

        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    data = result.get("data", {})
    anonymized = data.get("anonymizedContent", "")
    has_pii = data.get("hasPII", None)


    print("Status: success", file=sys.stderr)
    print("hasPII:", has_pii, file=sys.stderr)
    print(anonymized)


if __name__ == "__main__":
    main()
