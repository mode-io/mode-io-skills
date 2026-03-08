#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    message = (
        "modeio-guardrail no longer provides repository scanning.\n"
        "Use modeio-skill-audit instead:\n"
        "  python modeio-skill-audit/scripts/skill_safety_assessment.py evaluate --target-repo /path/to/repo --json\n"
    )
    sys.stderr.write(message)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
