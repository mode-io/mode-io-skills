# modeio-middleware Architecture

## Goal

Provide a simple local middleware layer around provider calls:

- pre-request hooks before upstream call
- post-response hooks before client response

Core runtime remains generic and plugin-based.

## Layout

```text
modeio-middleware/
  config/default.json
  scripts/
    middleware_gateway.py
    setup_middleware_gateway.py
  modeio_middleware/
    cli/
      gateway.py
      setup.py
    core/
      contracts.py
      engine.py
      errors.py
      http_contract.py
      plugin_manager.py
      profiles.py
    plugins/
      base.py
      guardrail.py
      redact.py
  tests/
    test_gateway_contract.py
    test_setup_gateway.py
    test_plugin_manager.py
    test_profile_policy.py
```

## Runtime data flow

1. Gateway receives `POST /v1/chat/completions`
2. Core validates request and parses `modeio` metadata
3. Plugin manager runs pre-request hooks
4. Core forwards request to upstream provider
5. Plugin manager runs post-response hooks
6. Gateway returns provider-compatible JSON + middleware headers

## Integration boundaries

- `plugins/base.py` defines plugin contract
- Plugins can `allow`, `modify`, `warn`, or `block`
- Existing skills integrate as optional plugin modules
- Core does not hardcode guardrail/redact decisions

## Compatibility and safety

- v1 supports non-streaming requests only
- setup script supports safe OpenCode patch/unpatch with backup
- Codex integration is environment-based (`OPENAI_BASE_URL`)
