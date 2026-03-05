#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[4]
GUARDRAIL_PACKAGE_ROOT = REPO_ROOT / "modeio-guardrail"
if str(GUARDRAIL_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(GUARDRAIL_PACKAGE_ROOT))


def request_guardrail_assessment(
    *,
    instruction: str,
    context: Optional[str],
    target: Optional[str],
) -> Dict[str, Any]:
    from modeio_guardrail.cli import safety as guardrail_safety

    assessment = guardrail_safety.detect_safety(
        instruction=instruction,
        context=context,
        target=target,
    )
    if not isinstance(assessment, dict):
        return {}
    return assessment
