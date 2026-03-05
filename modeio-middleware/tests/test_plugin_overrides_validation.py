#!/usr/bin/env python3

import unittest

from modeio_middleware.core.errors import MiddlewareError
from modeio_middleware.core.plugin_overrides import validate_plugin_overrides


class TestPluginOverridesValidation(unittest.TestCase):
    def test_allow_none_true_returns_empty_mapping(self):
        overrides = validate_plugin_overrides(
            None,
            path_prefix="profile.plugin_overrides",
            object_error_message="profile.plugin_overrides must be an object",
            error_status=500,
            error_code="MODEIO_CONFIG_ERROR",
            allow_none=True,
        )
        self.assertEqual(overrides, {})

    def test_allow_none_false_raises(self):
        with self.assertRaises(MiddlewareError) as ctx:
            validate_plugin_overrides(
                None,
                path_prefix="modeio.plugins",
                object_error_message="field 'modeio.plugins' must be an object",
                error_status=400,
                error_code="MODEIO_VALIDATION_ERROR",
                allow_none=False,
            )

        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.code, "MODEIO_VALIDATION_ERROR")

    def test_invalid_enabled_flag_raises(self):
        with self.assertRaises(MiddlewareError):
            validate_plugin_overrides(
                {"example": {"enabled": "yes"}},
                path_prefix="profile.plugin_overrides",
                object_error_message="profile.plugin_overrides must be an object",
                error_status=500,
                error_code="MODEIO_CONFIG_ERROR",
                allow_none=True,
            )

    def test_valid_override_mapping_is_normalized(self):
        overrides = validate_plugin_overrides(
            {
                " example ": {
                    "enabled": True,
                    "timeout_ms": {"pre.request": 120},
                }
            },
            path_prefix="modeio.plugins",
            object_error_message="field 'modeio.plugins' must be an object",
            error_status=400,
            error_code="MODEIO_VALIDATION_ERROR",
            allow_none=False,
        )
        self.assertIn("example", overrides)
        self.assertTrue(overrides["example"]["enabled"])


if __name__ == "__main__":
    unittest.main()
