#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from modeio_middleware.core.decision import HookDecision
from modeio_middleware.plugins.guardrail_impl.presets import PRESET_QUIET


def _normalize_risk_level(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return "unknown"
    return value


def _normalize_optional_bool(raw: Any) -> Optional[bool]:
    if isinstance(raw, bool):
        return raw
    return None


def _extract_evidence(concerns: Any) -> List[str]:
    evidence: List[str] = []
    if not isinstance(concerns, list):
        return evidence
    for concern in concerns:
        if isinstance(concern, str) and concern.strip():
            evidence.append(concern.strip())
    return evidence


def _resolve_warn_levels(config: Dict[str, Any], *, preset: str) -> Set[str]:
    raw = config.get("warn_risk_levels")
    if isinstance(raw, list):
        values = {
            str(item).strip().lower()
            for item in raw
            if str(item).strip()
        }
        if values:
            return values

    if preset == PRESET_QUIET:
        return {"medium", "high"}
    return {"medium", "high", "critical"}


def _should_block(
    *,
    block_rule: str,
    approved: Any,
    risk_level: str,
    is_destructive: Optional[bool],
    is_reversible: Optional[bool],
) -> bool:
    if block_rule == "critical_or_high_irreversible_destructive_unapproved":
        if risk_level == "critical":
            return True
        return (
            approved is False
            and risk_level == "high"
            and is_destructive is True
            and is_reversible is False
        )

    return approved is False and risk_level in {"high", "critical"}


def evaluate_guardrail_assessment(
    *,
    assessment: Dict[str, Any],
    preset: str,
    config: Dict[str, Any],
) -> HookDecision:
    approved = assessment.get("approved")
    risk_level = _normalize_risk_level(assessment.get("risk_level"))
    is_destructive = _normalize_optional_bool(assessment.get("is_destructive"))
    is_reversible = _normalize_optional_bool(assessment.get("is_reversible"))
    recommendation = assessment.get("recommendation")

    warn_levels = _resolve_warn_levels(config, preset=preset)
    default_block_rule = "high_or_critical_unapproved"
    if preset == PRESET_QUIET:
        default_block_rule = "critical_or_high_irreversible_destructive_unapproved"
    block_rule = str(config.get("block_rule", default_block_rule)).strip().lower()

    evidence = _extract_evidence(assessment.get("concerns"))
    finding = {
        "class": "instruction_safety",
        "severity": risk_level,
        "confidence": 0.8,
        "reason": "guardrail assessment from modeio-guardrail plugin",
        "evidence": evidence,
        "policy": {
            "preset": preset,
            "block_rule": block_rule,
            "approved": approved,
            "is_destructive": is_destructive,
            "is_reversible": is_reversible,
        },
    }

    message = recommendation if isinstance(recommendation, str) else None
    default_block_message = config.get("default_block_message")
    default_warn_message = config.get("default_warn_message")

    if _should_block(
        block_rule=block_rule,
        approved=approved,
        risk_level=risk_level,
        is_destructive=is_destructive,
        is_reversible=is_reversible,
    ):
        fallback: str
        if isinstance(default_block_message, str) and default_block_message.strip():
            fallback = default_block_message
        elif preset == PRESET_QUIET:
            fallback = "guardrail quiet preset requires explicit approval"
        else:
            fallback = "guardrail plugin blocked high-risk instruction"
        return HookDecision(
            action="block",
            findings=[finding],
            message=message or fallback,
        )

    should_warn = approved is False or risk_level in warn_levels
    if should_warn:
        fallback: Optional[str] = None
        if isinstance(default_warn_message, str) and default_warn_message.strip():
            fallback = default_warn_message
        elif preset == PRESET_QUIET and approved is False:
            fallback = "guardrail quiet preset flagged this instruction for review"
        return HookDecision(
            action="warn",
            findings=[finding],
            message=message or fallback,
        )

    return HookDecision(action="allow", findings=[finding])
