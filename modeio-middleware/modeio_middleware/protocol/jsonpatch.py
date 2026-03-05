#!/usr/bin/env python3

from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple


def _decode_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _split_pointer(path: str) -> List[str]:
    if path == "":
        return []
    if not path.startswith("/"):
        raise ValueError("json patch path must start with '/'")
    return [_decode_pointer_token(token) for token in path[1:].split("/")]


def _resolve_parent(document: Any, tokens: List[str]) -> Tuple[Any, str]:
    if not tokens:
        raise ValueError("json patch path points to document root")

    current = document
    for token in tokens[:-1]:
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"path segment '{token}' not found")
            current = current[token]
            continue

        if isinstance(current, list):
            if token == "-":
                raise ValueError("'-' cannot be used in intermediate path segments")
            try:
                index = int(token)
            except ValueError as error:
                raise ValueError(f"list index must be numeric: '{token}'") from error
            if index < 0 or index >= len(current):
                raise ValueError(f"list index out of range: {index}")
            current = current[index]
            continue

        raise ValueError("path traverses non-container value")

    return current, tokens[-1]


def _apply_add(parent: Any, token: str, value: Any) -> None:
    if isinstance(parent, dict):
        parent[token] = value
        return

    if isinstance(parent, list):
        if token == "-":
            parent.append(value)
            return
        try:
            index = int(token)
        except ValueError as error:
            raise ValueError(f"list index must be numeric: '{token}'") from error
        if index < 0 or index > len(parent):
            raise ValueError(f"list index out of range for add: {index}")
        parent.insert(index, value)
        return

    raise ValueError("add operation parent must be object or array")


def _apply_replace(parent: Any, token: str, value: Any) -> None:
    if isinstance(parent, dict):
        if token not in parent:
            raise ValueError(f"replace target key not found: '{token}'")
        parent[token] = value
        return

    if isinstance(parent, list):
        try:
            index = int(token)
        except ValueError as error:
            raise ValueError(f"list index must be numeric: '{token}'") from error
        if index < 0 or index >= len(parent):
            raise ValueError(f"list index out of range for replace: {index}")
        parent[index] = value
        return

    raise ValueError("replace operation parent must be object or array")


def _apply_remove(parent: Any, token: str) -> None:
    if isinstance(parent, dict):
        if token not in parent:
            raise ValueError(f"remove target key not found: '{token}'")
        del parent[token]
        return

    if isinstance(parent, list):
        try:
            index = int(token)
        except ValueError as error:
            raise ValueError(f"list index must be numeric: '{token}'") from error
        if index < 0 or index >= len(parent):
            raise ValueError(f"list index out of range for remove: {index}")
        del parent[index]
        return

    raise ValueError("remove operation parent must be object or array")


def apply_json_patch(document: Any, operations: List[Dict[str, Any]]) -> Any:
    if not isinstance(operations, list):
        raise ValueError("patch operations must be an array")

    patched = copy.deepcopy(document)
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValueError(f"patch operation #{index} must be an object")

        op = str(operation.get("op", "")).strip().lower()
        path = operation.get("path")
        if not isinstance(path, str):
            raise ValueError(f"patch operation #{index} path must be a string")
        tokens = _split_pointer(path)

        if op == "replace" and not tokens:
            patched = copy.deepcopy(operation.get("value"))
            continue

        parent, token = _resolve_parent(patched, tokens)

        if op == "add":
            _apply_add(parent, token, copy.deepcopy(operation.get("value")))
            continue

        if op == "replace":
            _apply_replace(parent, token, copy.deepcopy(operation.get("value")))
            continue

        if op == "remove":
            _apply_remove(parent, token)
            continue

        raise ValueError(f"unsupported patch operation '{op}' in operation #{index}")

    return patched
