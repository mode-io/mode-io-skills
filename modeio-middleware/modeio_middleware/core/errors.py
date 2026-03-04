#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict, Optional


class MiddlewareError(RuntimeError):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.status = int(status)
        self.code = str(code)
        self.message = str(message)
        self.retryable = bool(retryable)
        self.details = details
