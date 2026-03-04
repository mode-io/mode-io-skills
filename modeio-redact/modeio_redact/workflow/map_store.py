#!/usr/bin/env python3
"""
Local mapping storage utilities for modeio-redact modules.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAP_DIR_ENV = "MODEIO_REDACT_MAP_DIR"
DEFAULT_MAP_DIR = Path.home() / ".modeio" / "redact" / "maps"
SCHEMA_VERSION = "1"
MAP_FILE_SUFFIX = ".json"
MAP_TTL_DAYS = 7


class MapStoreError(RuntimeError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        return


def get_map_dir() -> Path:
    override = os.environ.get(MAP_DIR_ENV, "").strip()
    map_dir = Path(override).expanduser() if override else DEFAULT_MAP_DIR
    map_dir.mkdir(parents=True, exist_ok=True)
    _safe_chmod(map_dir, 0o700)
    return map_dir


def _normalize_entry(raw: Dict[str, Any]) -> Optional[Dict[str, str]]:
    if not isinstance(raw, dict):
        return None

    placeholder = raw.get("placeholder") or raw.get("anonymized") or raw.get("maskedValue")
    original = raw.get("original")
    if original is None:
        original = raw.get("value")

    if not isinstance(placeholder, str) or not isinstance(original, str):
        return None

    placeholder = placeholder.strip()
    original = original.strip()
    if not placeholder or not original:
        return None

    entity_type = raw.get("type")
    if not isinstance(entity_type, str) or not entity_type.strip():
        entity_type = "unknown"

    return {
        "placeholder": placeholder,
        "original": original,
        "type": entity_type,
    }


def normalize_mapping_entries(data: Dict[str, Any]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    seen_placeholders = set()

    local_detection = data.get("localDetection")
    if isinstance(local_detection, dict):
        local_items = local_detection.get("items")
        if isinstance(local_items, list):
            for item in local_items:
                normalized = _normalize_entry(item)
                if not normalized:
                    continue
                placeholder = normalized["placeholder"]
                if placeholder in seen_placeholders:
                    continue
                seen_placeholders.add(placeholder)
                entries.append(normalized)

    mapping_items = data.get("mapping")
    if isinstance(mapping_items, list):
        for item in mapping_items:
            normalized = _normalize_entry(item)
            if not normalized:
                continue
            placeholder = normalized["placeholder"]
            if placeholder in seen_placeholders:
                continue
            seen_placeholders.add(placeholder)
            entries.append(normalized)

    return entries


def _prune_old_maps(map_dir: Path) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAP_TTL_DAYS)
    cutoff_timestamp = cutoff.timestamp()
    for candidate in map_dir.glob(f"*{MAP_FILE_SUFFIX}"):
        try:
            if candidate.stat().st_mtime < cutoff_timestamp:
                candidate.unlink()
        except OSError:
            continue


def _new_map_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand = uuid.uuid4().hex[:8]
    return f"{ts}-{rand}"


def save_map(
    raw_input: str,
    anonymized_content: str,
    entries: List[Dict[str, str]],
    level: str,
    source_mode: str,
) -> Dict[str, Any]:
    if not entries:
        raise MapStoreError("cannot save map: no mapping entries found")

    map_dir = get_map_dir()
    _prune_old_maps(map_dir)

    map_id = _new_map_id()
    path = map_dir / f"{map_id}{MAP_FILE_SUFFIX}"

    record: Dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "mapId": map_id,
        "createdAt": _utc_now_iso(),
        "level": level,
        "sourceMode": source_mode,
        "inputHash": hash_text(raw_input),
        "anonymizedHash": hash_text(anonymized_content),
        "entryCount": len(entries),
        "entries": entries,
    }

    temp_name = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f"{map_id}-", suffix=".tmp", dir=str(map_dir))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
        temp_path = Path(temp_name)
        _safe_chmod(temp_path, 0o600)
        os.replace(temp_path, path)
        _safe_chmod(path, 0o600)
    except OSError as exc:
        if temp_name:
            try:
                Path(temp_name).unlink()
            except OSError:
                pass
        raise MapStoreError(f"failed to persist local map file: {exc}") from exc

    return {
        "mapId": map_id,
        "mapPath": str(path),
        "entryCount": len(entries),
    }


def _resolve_map_path(map_ref: Optional[str]) -> Path:
    map_dir = get_map_dir()

    if map_ref:
        direct_path = Path(map_ref).expanduser()
        if direct_path.is_file():
            return direct_path

        ref = map_ref.strip()
        if ref.endswith(MAP_FILE_SUFFIX):
            ref = ref[: -len(MAP_FILE_SUFFIX)]
        id_path = map_dir / f"{ref}{MAP_FILE_SUFFIX}"
        if id_path.is_file():
            return id_path
        raise MapStoreError(f"mapping file not found for reference: {map_ref}")

    candidates = [p for p in map_dir.glob(f"*{MAP_FILE_SUFFIX}") if p.is_file()]
    if not candidates:
        raise MapStoreError("no local map files found; run anonymize first")

    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0]


def _validate_record(raw: Dict[str, Any], fallback_map_id: str) -> Dict[str, Any]:
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list):
        raise MapStoreError("invalid map file: missing entries array")

    entries: List[Dict[str, str]] = []
    for item in entries_raw:
        normalized = _normalize_entry(item)
        if normalized:
            entries.append(normalized)

    if not entries:
        raise MapStoreError("invalid map file: entries are empty or malformed")

    map_id = raw.get("mapId")
    if not isinstance(map_id, str) or not map_id.strip():
        map_id = fallback_map_id

    cleaned = {
        "schemaVersion": str(raw.get("schemaVersion") or SCHEMA_VERSION),
        "mapId": map_id,
        "createdAt": str(raw.get("createdAt") or ""),
        "level": str(raw.get("level") or ""),
        "sourceMode": str(raw.get("sourceMode") or ""),
        "inputHash": str(raw.get("inputHash") or ""),
        "anonymizedHash": str(raw.get("anonymizedHash") or ""),
        "entryCount": len(entries),
        "entries": entries,
    }
    return cleaned


def load_map(map_ref: Optional[str]) -> Tuple[Dict[str, Any], Path]:
    path = _resolve_map_path(map_ref)
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except OSError as exc:
        raise MapStoreError(f"failed to read map file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MapStoreError(f"map file is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise MapStoreError("invalid map file: root must be an object")

    record = _validate_record(raw, fallback_map_id=path.stem)
    return record, path
