# Middleware Test Suite

This suite is organized by confidence layer, even though some files still live in a flat directory.

## Support Layer

- `helpers/gateway_harness.py`
  - shared upstream/gateway harness plus reusable HTTP request helpers
- `helpers/plugin_modules.py`
  - dynamic plugin-module registration for in-process test plugins
- `fixtures/`
  - reusable stdio protocol plugin fixtures

## Unit-Style Coverage

These tests should pin one module or one narrow contract at a time:

- `test_config_resolver.py`
- `test_new_plugin_cli.py`
- `test_packaging_resources.py`
- `test_plugin_manager.py`
- `test_plugin_overrides_validation.py`
- `test_profile_policy.py`
- `test_protocol_manifest.py`
- `test_protocol_registry.py`
- `test_redact_utils.py`
- `test_runtime_manager.py`
- `test_setup_gateway.py`
- `test_sse.py`
- `test_stdio_supervisor.py`
- `test_upstream_client.py`

## Integration Coverage

These tests exercise multiple middleware layers together:

- `test_gateway_contract.py`
- `test_claude_hook_connector.py`
- `test_protocol_stdio_runtime.py`

## Smoke Coverage

These tests validate operator flows and repo tooling:

- `test_protocol_example_plugin.py`
- `test_smoke_agent_matrix_support.py`
- `test_smoke_opencode_flow.py`

## Rules

- Prefer adding direct unit tests before expanding large gateway happy-path files.
- Reuse helpers from `tests/helpers/` instead of adding inline HTTP clients or plugin registration code.
- Add new black-box gateway tests only when the behavior truly crosses module boundaries.
