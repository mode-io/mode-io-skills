#!/usr/bin/env python3
"""
Shared --input resolver for modeio-redact modules.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

SUPPORTED_FILE_EXTENSIONS = (".txt", ".md")


def resolve_input_source(input_value: str) -> Tuple[str, str]:
    """Resolve --input as literal text or supported file path."""
    content, input_type, _ = resolve_input_source_details(input_value)
    return content, input_type


def resolve_input_source_details(input_value: str) -> Tuple[str, str, Optional[str]]:
    """Resolve --input and preserve source path when input is a file."""
    raw_value = (input_value or "").strip()
    if not raw_value:
        raise ValueError("--input must not be empty.")

    expanded_path = os.path.expandvars(os.path.expanduser(raw_value))
    if os.path.isfile(expanded_path):
        extension = os.path.splitext(expanded_path)[1].lower()
        if extension not in SUPPORTED_FILE_EXTENSIONS:
            allowed = ", ".join(SUPPORTED_FILE_EXTENSIONS)
            raise ValueError(
                f"Unsupported file extension '{extension or '(none)'}'. "
                f"Supported file types: {allowed}."
            )

        try:
            with open(expanded_path, "r", encoding="utf-8") as input_file:
                content = input_file.read()
        except UnicodeDecodeError as exc:
            raise ValueError("Input file must be UTF-8 encoded.") from exc
        except OSError as exc:
            raise ValueError(f"Failed to read input file: {exc}") from exc

        if not content.strip():
            raise ValueError("Input file must not be empty.")

        return content, "file", expanded_path

    return raw_value, "text", None
