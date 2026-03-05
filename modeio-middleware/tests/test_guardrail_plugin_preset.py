#!/usr/bin/env python3

import sys
import types
import unittest
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "modeio-middleware" / "scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

from modeio_middleware.core.contracts import ENDPOINT_CHAT_COMPLETIONS  # noqa: E402
from modeio_middleware.plugins.guardrail import Plugin  # noqa: E402


def _hook_input(*, plugin_config=None):
    return {
        "endpoint_kind": ENDPOINT_CHAT_COMPLETIONS,
        "request_body": {
            "model": "gpt-test",
            "messages": [
                {
                    "role": "user",
                    "content": "delete production table users",
                }
            ],
        },
        "plugin_config": plugin_config or {},
    }


def _action_of(result):
    if isinstance(result, dict):
        return result.get("action")
    return getattr(result, "action", None)


@contextmanager
def _patch_guardrail_assessment(assessment):
    module = types.ModuleType("modeio_guardrail.cli.safety")

    def _detect_safety(instruction, context=None, target=None):
        _ = (instruction, context, target)
        return assessment

    module.detect_safety = _detect_safety
    cli_package = import_module("modeio_guardrail.cli")
    prior = getattr(cli_package, "safety", None)

    with patch.dict(sys.modules, {"modeio_guardrail.cli.safety": module}):
        setattr(cli_package, "safety", module)
        try:
            yield
        finally:
            if prior is not None:
                setattr(cli_package, "safety", prior)
            elif hasattr(cli_package, "safety"):
                delattr(cli_package, "safety")


class TestGuardrailPluginPreset(unittest.TestCase):
    def test_interactive_blocks_high_unapproved(self):
        assessment = {
            "approved": False,
            "risk_level": "high",
            "concerns": ["high risk operation"],
            "recommendation": "stop",
        }

        with _patch_guardrail_assessment(assessment):
            result = Plugin().pre_request(_hook_input())
        self.assertEqual(_action_of(result), "block")

    def test_quiet_warns_high_reversible(self):
        assessment = {
            "approved": False,
            "risk_level": "high",
            "is_destructive": True,
            "is_reversible": True,
            "concerns": ["destructive but reversible"],
        }

        with _patch_guardrail_assessment(assessment):
            result = Plugin().pre_request(_hook_input(plugin_config={"preset": "quiet"}))
        self.assertEqual(_action_of(result), "warn")

    def test_quiet_blocks_high_irreversible(self):
        assessment = {
            "approved": False,
            "risk_level": "high",
            "is_destructive": True,
            "is_reversible": False,
            "concerns": ["irreversible destructive operation"],
        }

        with _patch_guardrail_assessment(assessment):
            result = Plugin().pre_request(_hook_input(plugin_config={"preset": "quiet"}))
        self.assertEqual(_action_of(result), "block")

    def test_quiet_blocks_critical_even_if_approved(self):
        assessment = {
            "approved": True,
            "risk_level": "critical",
            "concerns": ["critical risk"],
        }

        with _patch_guardrail_assessment(assessment):
            result = Plugin().pre_request(_hook_input(plugin_config={"preset": "quiet"}))
        self.assertEqual(_action_of(result), "block")


if __name__ == "__main__":
    unittest.main()
