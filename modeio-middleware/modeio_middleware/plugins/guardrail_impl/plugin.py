#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict

from modeio_middleware.core.context_extractor import extract_request_intent
from modeio_middleware.core.contracts import ENDPOINT_CHAT_COMPLETIONS
from modeio_middleware.core.decision import HookDecision
from modeio_middleware.plugins.base import MiddlewarePlugin
from modeio_middleware.plugins.guardrail_impl.client import request_guardrail_assessment
from modeio_middleware.plugins.guardrail_impl.policy import evaluate_guardrail_assessment
from modeio_middleware.plugins.guardrail_impl.presets import DEFAULT_PRESET, normalize_preset


class Plugin(MiddlewarePlugin):
    name = "guardrail"
    version = "0.2.0"

    def pre_request(self, hook_input: Dict[str, Any]) -> HookDecision:
        endpoint_kind = hook_input.get("endpoint_kind", ENDPOINT_CHAT_COMPLETIONS)
        request_body = hook_input["request_body"]
        plugin_config = hook_input.get("plugin_config", {})

        intent = extract_request_intent(endpoint_kind, request_body)
        if not intent.instruction:
            return HookDecision(action="allow")

        context = plugin_config.get("context")
        target = plugin_config.get("target")
        preset = normalize_preset(
            plugin_config.get("interaction_mode")
            if isinstance(plugin_config.get("interaction_mode"), str)
            else plugin_config.get("preset"),
            default=DEFAULT_PRESET,
        )

        assessment = request_guardrail_assessment(
            instruction=intent.instruction,
            context=context if isinstance(context, str) else None,
            target=target if isinstance(target, str) else None,
        )

        return evaluate_guardrail_assessment(
            assessment=assessment,
            preset=preset,
            config=plugin_config,
        )
