#!/usr/bin/env python3

from modeio_middleware.cli.setup_lib.claude import (
    CLAUDE_HOOK_EVENTS,
    apply_claude_hook_config,
    apply_claude_settings_file,
    default_claude_settings_path,
    derive_claude_hook_url,
    remove_claude_hook_config,
    uninstall_claude_settings_file,
)
from modeio_middleware.cli.setup_lib.common import (
    HealthCheckResult,
    SetupError,
    derive_health_url,
    normalize_gateway_base_url,
)
from modeio_middleware.cli.setup_lib.opencode import (
    apply_opencode_base_url,
    apply_opencode_config_file,
    remove_opencode_base_url,
    uninstall_opencode_config_file,
)

__all__ = [
    "CLAUDE_HOOK_EVENTS",
    "HealthCheckResult",
    "SetupError",
    "apply_claude_hook_config",
    "apply_claude_settings_file",
    "apply_opencode_base_url",
    "apply_opencode_config_file",
    "default_claude_settings_path",
    "derive_claude_hook_url",
    "derive_health_url",
    "normalize_gateway_base_url",
    "remove_claude_hook_config",
    "remove_opencode_base_url",
    "uninstall_claude_settings_file",
    "uninstall_opencode_config_file",
]
