#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modeio_middleware.cli.validate_plugin_manifest import main

if __name__ == "__main__":
    raise SystemExit(main())
