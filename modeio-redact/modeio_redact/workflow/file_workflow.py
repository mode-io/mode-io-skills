#!/usr/bin/env python3
"""
File output and map-linkage helpers for modeio-redact modules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

MAP_MARKER_PREFIX = "modeio-redact-map-id"
MARKER_PATTERN_MD = re.compile(r"^\s*<!--\s*modeio-redact-map-id:\s*([^\s]+)\s*-->\s*$")
MARKER_PATTERN_TXT = re.compile(r"^\s*#\s*modeio-redact-map-id:\s*([^\s]+)\s*$")


def _expand_path(path_value: str) -> Path:
    return Path(path_value).expanduser()


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}.{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def resolve_output_path(
    input_path: Optional[str],
    output_path: Optional[str],
    in_place: bool,
    output_tag: str,
) -> Optional[Path]:
    """Resolve output file path for text/file workflows."""
    if in_place:
        if output_path:
            raise ValueError("--in-place cannot be used together with --output.")
        if not input_path:
            raise ValueError("--in-place requires file-path input.")
        return _expand_path(input_path)

    if output_path:
        resolved = _expand_path(output_path)
        parent = resolved.parent
        if not parent.exists() or not parent.is_dir():
            raise ValueError(f"Output directory does not exist: {parent}")
        return resolved

    if not input_path:
        return None

    source = _expand_path(input_path)
    candidate = source.with_name(f"{source.stem}.{output_tag}{source.suffix}")
    return _next_available_path(candidate)


def write_output_file(path: Path, content: str) -> None:
    parent = path.parent
    if not parent.exists() or not parent.is_dir():
        raise ValueError(f"Output directory does not exist: {parent}")
    path.write_text(content, encoding="utf-8")


def _match_map_marker(line: str) -> Optional[str]:
    md_match = MARKER_PATTERN_MD.match(line)
    if md_match:
        return md_match.group(1)
    txt_match = MARKER_PATTERN_TXT.match(line)
    if txt_match:
        return txt_match.group(1)
    return None


def extract_embedded_map_id(content: str) -> Optional[str]:
    """Extract embedded map id from the first few lines."""
    lines = content.splitlines()
    for line in lines[:5]:
        map_id = _match_map_marker(line)
        if map_id:
            return map_id
    return None


def strip_embedded_map_marker(content: str) -> str:
    """Strip top map marker line if present."""
    lines = content.splitlines(keepends=True)
    if not lines:
        return content

    first = lines[0].strip()
    if _match_map_marker(first):
        return "".join(lines[1:])
    return content


def embed_map_marker(content: str, map_id: str, suffix: str) -> str:
    """Embed map id marker for txt/md output files."""
    clean_content = strip_embedded_map_marker(content)
    normalized_suffix = suffix.lower()
    if normalized_suffix == ".md":
        marker = f"<!-- {MAP_MARKER_PREFIX}: {map_id} -->"
        return f"{marker}\n{clean_content}"
    if normalized_suffix == ".txt":
        marker = f"# {MAP_MARKER_PREFIX}: {map_id}"
        return f"{marker}\n{clean_content}"
    return clean_content


def sidecar_map_path_for(content_path: Path) -> Path:
    return content_path.with_suffix(".map.json")


def write_sidecar_map(content_path: Path, map_ref: Dict[str, str]) -> Path:
    sidecar_path = sidecar_map_path_for(content_path)
    payload = {
        "schemaVersion": "1",
        "mapId": map_ref.get("mapId", ""),
        "mapPath": map_ref.get("mapPath", ""),
        "entryCount": map_ref.get("entryCount", 0),
    }
    sidecar_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar_path


def read_sidecar_map_reference(content_path: Path) -> Tuple[Optional[str], Optional[Path]]:
    sidecar_path = sidecar_map_path_for(content_path)
    if not sidecar_path.exists() or not sidecar_path.is_file():
        return None, None

    try:
        raw = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Sidecar map file is invalid JSON: {sidecar_path}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Sidecar map file must be an object: {sidecar_path}")

    map_path = raw.get("mapPath")
    if isinstance(map_path, str) and map_path.strip():
        return map_path.strip(), sidecar_path

    map_id = raw.get("mapId")
    if isinstance(map_id, str) and map_id.strip():
        return map_id.strip(), sidecar_path

    raise ValueError(f"Sidecar map file missing mapId/mapPath: {sidecar_path}")
