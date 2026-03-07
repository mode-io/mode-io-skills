#!/usr/bin/env python3

from __future__ import annotations

import copy
from typing import Any, Dict

from modeio_middleware.connectors.base import CanonicalInvocation, ConnectorAdapter, ConnectorCapabilities
from modeio_middleware.core.contracts import ModeioOptions, normalize_modeio_options
from modeio_middleware.core.errors import MiddlewareError

CLAUDE_HOOK_CONNECTOR_PATH = "/connectors/claude/hooks"

EVENT_USER_PROMPT_SUBMIT = "UserPromptSubmit"
EVENT_STOP = "Stop"

SUPPORTED_CLAUDE_EVENTS = {
    EVENT_USER_PROMPT_SUBMIT,
    EVENT_STOP,
}

PHASE_PRE_REQUEST = "pre_request"
PHASE_POST_RESPONSE = "post_response"

ENDPOINT_CLAUDE_USER_PROMPT = "claude_user_prompt"
ENDPOINT_CLAUDE_STOP = "claude_stop"


def _default_connector_capabilities() -> ConnectorCapabilities:
    return ConnectorCapabilities(
        can_patch=False,
        can_block=True,
    )


class ClaudeHookConnector(ConnectorAdapter):
    route_paths = (CLAUDE_HOOK_CONNECTOR_PATH,)

    def parse(
        self,
        *,
        request_id: str,
        payload: Dict[str, Any],
        incoming_headers: Dict[str, str],
        default_profile: str,
        path: str,
    ) -> CanonicalInvocation:
        del path
        return parse_claude_hook_invocation(
            request_id=request_id,
            payload=payload,
            incoming_headers=incoming_headers,
            default_profile=default_profile,
        )


def parse_claude_hook_invocation(
    *,
    request_id: str,
    payload: Dict[str, Any],
    incoming_headers: Dict[str, str],
    default_profile: str,
) -> CanonicalInvocation:
    if not isinstance(payload, dict):
        raise MiddlewareError(
            400,
            "MODEIO_VALIDATION_ERROR",
            "claude hook payload must be an object",
            retryable=False,
        )

    event_payload = copy.deepcopy(payload)
    modeio_options: ModeioOptions = normalize_modeio_options(
        event_payload,
        default_profile=default_profile,
    )

    raw_event_name = event_payload.get("hook_event_name")
    if not isinstance(raw_event_name, str) or not raw_event_name.strip():
        raise MiddlewareError(
            400,
            "MODEIO_VALIDATION_ERROR",
            "claude hook payload requires non-empty 'hook_event_name'",
            retryable=False,
        )
    event_name = raw_event_name.strip()

    if event_name not in SUPPORTED_CLAUDE_EVENTS:
        raise MiddlewareError(
            400,
            "MODEIO_VALIDATION_ERROR",
            f"unsupported claude hook event '{event_name}'",
            retryable=False,
            details={"hook_event_name": event_name},
        )

    connector_capabilities = _default_connector_capabilities()
    connector_context = {
        "source": "claude_hooks",
        "source_event": event_name,
        "surface_capabilities": connector_capabilities.as_dict(),
        "native_event": event_payload,
    }

    if event_name == EVENT_USER_PROMPT_SUBMIT:
        request_body = {
            "event": event_payload,
            "prompt": event_payload.get("prompt", ""),
        }
        return CanonicalInvocation(
            source="claude_hooks",
            source_event=event_name,
            phase=PHASE_PRE_REQUEST,
            endpoint_kind=ENDPOINT_CLAUDE_USER_PROMPT,
            request_id=request_id,
            profile=modeio_options.profile,
            on_plugin_error=modeio_options.on_plugin_error,
            plugin_overrides=modeio_options.plugin_overrides,
            incoming_headers=dict(incoming_headers),
            request_body=request_body,
            response_body={},
            connector_context=connector_context,
            connector_capabilities=connector_capabilities,
            stream=False,
        )

    response_body = {
        "event": event_payload,
    }
    if isinstance(event_payload.get("assistant_response"), str):
        response_body["assistant_response"] = event_payload["assistant_response"]
    if isinstance(event_payload.get("status"), str):
        response_body["status"] = event_payload["status"]

    return CanonicalInvocation(
        source="claude_hooks",
        source_event=event_name,
        phase=PHASE_POST_RESPONSE,
        endpoint_kind=ENDPOINT_CLAUDE_STOP,
        request_id=request_id,
        profile=modeio_options.profile,
        on_plugin_error=modeio_options.on_plugin_error,
        plugin_overrides=modeio_options.plugin_overrides,
        incoming_headers=dict(incoming_headers),
        request_body={},
        response_body=response_body,
        connector_context=connector_context,
        connector_capabilities=connector_capabilities,
        stream=False,
    )


def _summarize_findings(findings: Any) -> str:
    if not isinstance(findings, list) or not findings:
        return ""

    segments = []
    for item in findings[:3]:
        if not isinstance(item, dict):
            continue
        reason = item.get("reason")
        if isinstance(reason, str) and reason.strip():
            segments.append(reason.strip())

    if not segments:
        return ""
    return "modeio policy findings: " + " | ".join(segments)


def build_claude_hook_response(
    *,
    source_event: str,
    blocked: bool,
    block_message: str,
    findings: Any,
) -> Dict[str, Any]:
    if blocked:
        message = block_message.strip() if isinstance(block_message, str) and block_message.strip() else "blocked by modeio policy"
        return {
            "decision": "block",
            "reason": message,
        }

    summary = _summarize_findings(findings)
    if not summary:
        return {}

    response: Dict[str, Any] = {
        "systemMessage": summary,
    }
    if source_event == EVENT_USER_PROMPT_SUBMIT:
        response["hookSpecificOutput"] = {
            "hookEventName": EVENT_USER_PROMPT_SUBMIT,
            "additionalContext": summary,
        }
    return response
