#!/usr/bin/env python3

from __future__ import annotations

from typing import Dict

JSONRPC_VERSION = "2.0"

METHOD_INITIALIZE = "modeio.initialize"
METHOD_INVOKE = "modeio.invoke"
METHOD_SHUTDOWN = "modeio.shutdown"

HOOK_PRE_REQUEST = "pre.request"
HOOK_POST_RESPONSE = "post.response"
HOOK_POST_STREAM_START = "post.stream.start"
HOOK_POST_STREAM_EVENT = "post.stream.event"
HOOK_POST_STREAM_END = "post.stream.end"

VALID_PROTOCOL_HOOKS = {
    HOOK_PRE_REQUEST,
    HOOK_POST_RESPONSE,
    HOOK_POST_STREAM_START,
    HOOK_POST_STREAM_EVENT,
    HOOK_POST_STREAM_END,
}

INTERNAL_TO_PROTOCOL_HOOK: Dict[str, str] = {
    "pre_request": HOOK_PRE_REQUEST,
    "post_response": HOOK_POST_RESPONSE,
    "post_stream_start": HOOK_POST_STREAM_START,
    "post_stream_event": HOOK_POST_STREAM_EVENT,
    "post_stream_end": HOOK_POST_STREAM_END,
}

PROTOCOL_ACTION_PASS = "pass"
PROTOCOL_ACTION_ANNOTATE = "annotate"
PROTOCOL_ACTION_PATCH = "patch"
PROTOCOL_ACTION_DEFER = "defer"
PROTOCOL_ACTION_BLOCK = "block"

VALID_PROTOCOL_ACTIONS = {
    PROTOCOL_ACTION_PASS,
    PROTOCOL_ACTION_ANNOTATE,
    PROTOCOL_ACTION_PATCH,
    PROTOCOL_ACTION_DEFER,
    PROTOCOL_ACTION_BLOCK,
}

PROTOCOL_TO_INTERNAL_ACTION: Dict[str, str] = {
    PROTOCOL_ACTION_PASS: "allow",
    PROTOCOL_ACTION_ANNOTATE: "warn",
    PROTOCOL_ACTION_PATCH: "modify",
    PROTOCOL_ACTION_DEFER: "defer",
    PROTOCOL_ACTION_BLOCK: "block",
}


def to_protocol_hook_name(internal_hook_name: str) -> str:
    hook = INTERNAL_TO_PROTOCOL_HOOK.get(internal_hook_name)
    if hook is None:
        raise ValueError(f"unsupported internal hook '{internal_hook_name}'")
    return hook
