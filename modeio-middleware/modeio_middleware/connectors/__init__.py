#!/usr/bin/env python3

from modeio_middleware.connectors.base import (
    CanonicalInvocation,
    ConnectorAdapter,
    ConnectorCapabilities,
)
from modeio_middleware.connectors.claude_hooks import (
    CLAUDE_HOOK_CONNECTOR_PATH,
    ClaudeHookConnector,
    build_claude_hook_response,
    parse_claude_hook_invocation,
)
from modeio_middleware.connectors.openai_http import OpenAIHttpConnector

# Backward-compatible aliases for the pre-refactor export surface.
ConnectorEvent = CanonicalInvocation
ClaudeHookInvocation = CanonicalInvocation

__all__ = [
    "CanonicalInvocation",
    "ConnectorAdapter",
    "ConnectorCapabilities",
    "ConnectorEvent",
    "CLAUDE_HOOK_CONNECTOR_PATH",
    "ClaudeHookConnector",
    "ClaudeHookInvocation",
    "OpenAIHttpConnector",
    "build_claude_hook_response",
    "parse_claude_hook_invocation",
]
