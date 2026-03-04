#!/usr/bin/env python3
"""Residual leak scanning utilities."""

from __future__ import annotations

from typing import Dict, List, Sequence

from modeio_redact.core.models import ResidualFinding


def scan_for_residuals(
    text: str,
    mapping_entries: Sequence[Dict[str, str]],
    *,
    part_id: str,
) -> List[ResidualFinding]:
    """Return residual findings when original values remain in output text."""
    findings: List[ResidualFinding] = []
    seen = set()
    for entry in mapping_entries:
        original = (entry.get("original") or "").strip()
        if not original or original in seen:
            continue
        seen.add(original)
        if original in text:
            findings.append(
                ResidualFinding(
                    part_id=part_id,
                    text=original,
                    evidence="original value still present in output",
                )
            )
    return findings
