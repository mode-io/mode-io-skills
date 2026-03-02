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

import requests

# Backend API URL, overridable via SAFETY_API_URL environment variable
URL = os.environ.get("SAFETY_API_URL", "https://safety-cf.modeio.ai/api/cf/safety")


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
    resp = requests.post(URL, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate instructions for safety risks (destructive ops, risk level, reversibility, etc.)"
    )
    parser.add_argument("-i", "--input", type=str, required=True, help="Instruction or operation description to evaluate")
    parser.add_argument("-c", "--context", type=str, default=None, help="Execution context (optional)")
    parser.add_argument("-t", "--target", type=str, default=None, help="Operation target such as file path, table name, or service (optional)")
    args = parser.parse_args()

    raw_input = args.input

    if not raw_input or not raw_input.strip():
        print("Error: --input must not be empty.", file=sys.stderr)
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
        print(f"Error: safety request failed. url={URL}", file=sys.stderr)
        if status_code is not None:
            print(f"Error: status_code={status_code}", file=sys.stderr)
        print(f"Error: exception={type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    if result.get("error"):
        print(f"Error: {result['error']}", file=sys.stderr)
        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    print("Status: success", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
