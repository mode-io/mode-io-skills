#!/usr/bin/env python3
"""
Central file-type registry for modeio-redact file workflows.

Adding support for a new text-like file type should only require one new
FileTypePolicy entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

MAP_MARKER_STYLE_NONE = "none"
MAP_MARKER_STYLE_HASH = "hash"
MAP_MARKER_STYLE_HTML_COMMENT = "html_comment"


@dataclass(frozen=True)
class FileTypePolicy:
    extension: str
    marker_style: str = MAP_MARKER_STYLE_NONE


_FILE_TYPE_POLICIES: Tuple[FileTypePolicy, ...] = (
    FileTypePolicy(extension=".txt", marker_style=MAP_MARKER_STYLE_HASH),
    FileTypePolicy(extension=".md", marker_style=MAP_MARKER_STYLE_HTML_COMMENT),
    FileTypePolicy(extension=".markdown", marker_style=MAP_MARKER_STYLE_HTML_COMMENT),
    FileTypePolicy(extension=".csv"),
    FileTypePolicy(extension=".tsv"),
    FileTypePolicy(extension=".json"),
    FileTypePolicy(extension=".jsonl"),
    FileTypePolicy(extension=".yaml"),
    FileTypePolicy(extension=".yml"),
    FileTypePolicy(extension=".xml"),
    FileTypePolicy(extension=".html"),
    FileTypePolicy(extension=".htm"),
    FileTypePolicy(extension=".rst"),
    FileTypePolicy(extension=".log"),
)


def _build_extension_map() -> Dict[str, FileTypePolicy]:
    mapping: Dict[str, FileTypePolicy] = {}
    for policy in _FILE_TYPE_POLICIES:
        normalized = normalize_extension(policy.extension)
        if not normalized.startswith("."):
            raise ValueError(f"File extension must start with '.': {policy.extension}")
        if normalized in mapping:
            raise ValueError(f"Duplicate file extension policy: {normalized}")
        mapping[normalized] = FileTypePolicy(
            extension=normalized,
            marker_style=policy.marker_style,
        )
    return mapping


def normalize_extension(extension: str) -> str:
    return (extension or "").strip().lower()


_EXTENSION_MAP = _build_extension_map()

SUPPORTED_FILE_EXTENSIONS: Tuple[str, ...] = tuple(_EXTENSION_MAP.keys())


def supported_extensions_for_display(separator: str = ", ") -> str:
    return separator.join(SUPPORTED_FILE_EXTENSIONS)


def is_supported_extension(extension: str) -> bool:
    return normalize_extension(extension) in _EXTENSION_MAP


def marker_style_for_extension(extension: str) -> str:
    normalized = normalize_extension(extension)
    policy = _EXTENSION_MAP.get(normalized)
    if policy is None:
        return MAP_MARKER_STYLE_NONE
    return policy.marker_style
