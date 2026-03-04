#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from modeio_middleware.plugins.base import MiddlewarePlugin

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
GUARDRAIL_PACKAGE_ROOT = REPO_ROOT / "modeio-guardrail"
if str(GUARDRAIL_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(GUARDRAIL_PACKAGE_ROOT))

TEXT_PART_TYPES = {"text", "input_text", "output_text"}


def _collect_message_texts(messages: Any) -> List[str]:
    if not isinstance(messages, list):
        return []

    segments: List[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            segments.append(content)
            continue
        if not isinstance(content, list):
            continue

        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") not in TEXT_PART_TYPES:
                continue
            part_text = part.get("text")
            if isinstance(part_text, str) and part_text.strip():
                segments.append(part_text)
    return segments


def _normalize_risk_level(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return "unknown"
    return value


class Plugin(MiddlewarePlugin):
    name = "guardrail"
    version = "0.1.0"

    def pre_request(self, hook_input: Dict[str, Any]) -> Dict[str, Any]:
        from modeio_guardrail.cli import safety as guardrail_safety

        request_body = hook_input["request_body"]
        plugin_config = hook_input.get("plugin_config", {})

        segments = _collect_message_texts(request_body.get("messages"))
        if not segments:
            return {"action": "allow"}

        instruction = "\n\n".join(segments).strip()
        if not instruction:
            return {"action": "allow"}

        context = plugin_config.get("context")
        target = plugin_config.get("target")

        assessment = guardrail_safety.detect_safety(
            instruction=instruction,
            context=context if isinstance(context, str) else None,
            target=target if isinstance(target, str) else None,
        )

        approved = assessment.get("approved")
        risk_level = _normalize_risk_level(assessment.get("risk_level"))
        concerns = assessment.get("concerns")
        recommendation = assessment.get("recommendation")

        evidence: List[str] = []
        if isinstance(concerns, list):
            for concern in concerns:
                if isinstance(concern, str) and concern.strip():
                    evidence.append(concern.strip())

        finding = {
            "class": "instruction_safety",
            "severity": risk_level,
            "confidence": 0.8,
            "reason": "guardrail assessment from modeio-guardrail plugin",
            "evidence": evidence,
        }

        message = recommendation if isinstance(recommendation, str) else None

        if approved is False and risk_level in {"high", "critical"}:
            return {
                "action": "block",
                "findings": [finding],
                "message": message or "guardrail plugin blocked high-risk instruction",
            }

        if approved is False:
            return {
                "action": "warn",
                "findings": [finding],
                "message": message,
            }

        if risk_level in {"medium", "high", "critical"}:
            return {
                "action": "warn",
                "findings": [finding],
                "message": message,
            }

        return {"action": "allow", "findings": [finding]}
