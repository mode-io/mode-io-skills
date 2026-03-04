#!/usr/bin/env python3
"""Build shared redaction plan objects from mapping entries."""

from __future__ import annotations

from typing import Dict, Sequence

from modeio_redact.core.models import RedactionPlan
from modeio_redact.planning.resolver import resolve_plan_spans


def build_redaction_plan(canonical_text: str, mapping_entries: Sequence[Dict[str, str]]) -> RedactionPlan:
    """Build canonical redaction plan from normalized map entries."""
    spans = resolve_plan_spans(canonical_text=canonical_text, mapping_entries=mapping_entries)
    warnings = []
    if mapping_entries and not spans:
        warnings.append("No canonical spans resolved from mapping entries.")
    return RedactionPlan(spans=spans, mapping_entries=list(mapping_entries), warnings=warnings)
