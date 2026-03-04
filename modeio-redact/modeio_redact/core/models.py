#!/usr/bin/env python3
"""Shared data contracts for the modular redaction pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


@dataclass(frozen=True)
class InputSource:
    """Normalized input source context for pipeline stages."""

    content: str
    input_type: str
    input_path: Optional[str]
    extension: Optional[str]
    handler_key: Optional[str]


@dataclass
class ExtractionBundle:
    """Adapter extraction output containing canonical text."""

    adapter_key: str
    canonical_text: str
    diagnostics: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlanSpan:
    """One canonical redaction span in normalized text coordinates."""

    start: int
    end: int
    original: str
    placeholder: str
    entity_type: str


@dataclass
class RedactionPlan:
    """Canonical plan derived from mapping entries."""

    spans: Sequence[PlanSpan]
    mapping_entries: Sequence[Dict[str, str]]
    warnings: List[str] = field(default_factory=list)

    @property
    def expected_count(self) -> int:
        return len(self.spans)


@dataclass
class ApplyReport:
    """Coverage report for apply stage."""

    expected_count: int
    found_count: int
    applied_count: int
    missed_spans: Sequence[PlanSpan] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResidualFinding:
    """Post-redaction residual detection evidence."""

    part_id: str
    text: str
    evidence: Optional[str] = None


@dataclass
class VerificationReport:
    """Verification stage output."""

    passed: bool
    skipped: bool
    residual_count: int
    residuals: Sequence[ResidualFinding] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @classmethod
    def skipped_report(cls) -> "VerificationReport":
        return cls(passed=True, skipped=True, residual_count=0, residuals=(), warnings=[])


@dataclass
class OutputPipelineResult:
    """End-to-end output of apply/verify/finalize pipeline."""

    output_path: Optional[str]
    sidecar_path: Optional[str]
    apply_report: ApplyReport
    verification_report: VerificationReport
