# Middleware Test Suite

This suite is physically split by confidence layer:

- `tests/unit/`
- `tests/integration/`
- `tests/smoke/`

## Support Layer

- `helpers/gateway_harness.py`
  - shared upstream/gateway harness plus reusable HTTP request helpers
- `helpers/plugin_modules.py`
  - dynamic plugin-module registration for in-process test plugins
- `fixtures/`
  - reusable stdio protocol plugin fixtures

## Unit-Style Coverage

These tests should pin one module or one narrow contract at a time:

- `unit/test_config_resolver.py`
- `unit/test_http_transport.py`
- `unit/test_new_plugin_cli.py`
- `unit/test_packaging_resources.py`
- `unit/test_plugin_manager.py`
- `unit/test_plugin_overrides_validation.py`
- `unit/test_profile_policy.py`
- `unit/test_protocol_manifest.py`
- `unit/test_protocol_registry.py`
- `unit/test_redact_utils.py`
- `unit/test_runtime_manager.py`
- `unit/test_setup_gateway.py`
- `unit/test_sse.py`
- `unit/test_stdio_supervisor.py`
- `unit/test_upstream_client.py`

## Integration Coverage

These tests exercise multiple middleware layers together:

- `integration/test_gateway_contract.py`
- `integration/test_claude_hook_connector.py`
- `integration/test_protocol_stdio_runtime.py`

## Smoke Coverage

These tests validate operator flows and repo tooling:

- `smoke/test_protocol_example_plugin.py`
- `smoke/test_smoke_agent_matrix_support.py`
- `smoke/test_smoke_opencode_flow.py`

## Rules

- Prefer adding direct unit tests before expanding large gateway happy-path files.
- Reuse helpers from `tests/helpers/` instead of adding inline HTTP clients or plugin registration code.
- Add new black-box gateway tests only when the behavior truly crosses module boundaries.
