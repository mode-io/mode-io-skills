#!/usr/bin/env python3
"""
Modeio local de-anonymization script.

Restores placeholders back to original values using local map files.
No network call is performed.
"""

import argparse
import json
import sys
from typing import Any, Dict, List

from map_store import MapStoreError, hash_text, load_map

TOOL_NAME = "modeio-redact"


def _success_envelope(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "success": True,
        "tool": TOOL_NAME,
        "mode": "local-map",
        "data": data,
    }


def _error_envelope(error_type: str, message: str, details: Dict[str, Any] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "success": False,
        "tool": TOOL_NAME,
        "mode": "local-map",
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def _apply_mapping(text: str, entries: List[Dict[str, str]]) -> Dict[str, Any]:
    restored = text
    replacements_by_type: Dict[str, int] = {}
    total_replacements = 0

    sorted_entries = sorted(entries, key=lambda item: len(item["placeholder"]), reverse=True)
    for item in sorted_entries:
        placeholder = item["placeholder"]
        original = item["original"]
        entity_type = item.get("type", "unknown")

        count = restored.count(placeholder)
        if count <= 0:
            continue

        restored = restored.replace(placeholder, original)
        total_replacements += count
        replacements_by_type[entity_type] = replacements_by_type.get(entity_type, 0) + count

    return {
        "deanonymizedContent": restored,
        "totalReplacements": total_replacements,
        "replacementsByType": replacements_by_type,
    }


def deanonymize(raw_input: str, map_ref: str = None) -> Dict[str, Any]:
    record, path = load_map(map_ref)

    replacement_result = _apply_mapping(raw_input, record["entries"])

    warnings = []
    expected_hash = record.get("anonymizedHash", "")
    if expected_hash and expected_hash != hash_text(raw_input):
        warnings.append(
            {
                "code": "input_hash_mismatch",
                "message": "input content hash does not match map anonymizedHash; replacements were still applied",
            }
        )

    payload = {
        "deanonymizedContent": replacement_result["deanonymizedContent"],
        "replacementSummary": {
            "totalReplacements": replacement_result["totalReplacements"],
            "replacementsByType": replacement_result["replacementsByType"],
        },
        "mapRef": {
            "mapId": record["mapId"],
            "mapPath": str(path),
            "entryCount": record["entryCount"],
        },
        "warnings": warnings,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore placeholders with local map file. Defaults to latest map in local store."
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        required=True,
        help="Anonymized content to restore.",
    )
    parser.add_argument(
        "--map",
        type=str,
        default=None,
        help="Map ID or map file path. Defaults to latest local map.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output unified JSON contract for machine consumption.",
    )
    args = parser.parse_args()

    raw_input = (args.input or "").strip()
    if not raw_input:
        message = "--input must not be empty."
        if args.json:
            print(json.dumps(_error_envelope("validation_error", message), ensure_ascii=False))
        else:
            print(f"Error: {message}", file=sys.stderr)
        sys.exit(2)

    try:
        result = deanonymize(raw_input, map_ref=args.map)
    except MapStoreError as error:
        if args.json:
            print(json.dumps(_error_envelope("map_error", str(error)), ensure_ascii=False))
        else:
            print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        if args.json:
            print(json.dumps(_error_envelope("runtime_error", str(error)), ensure_ascii=False))
        else:
            print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(_success_envelope(result), ensure_ascii=False))
        return

    print("Status: success", file=sys.stderr)
    print(f"mapId: {result['mapRef']['mapId']}", file=sys.stderr)
    print(f"totalReplacements: {result['replacementSummary']['totalReplacements']}", file=sys.stderr)
    for warning in result.get("warnings", []):
        print(f"Warning: {warning['code']}: {warning['message']}", file=sys.stderr)
    print(result["deanonymizedContent"])


if __name__ == "__main__":
    main()
