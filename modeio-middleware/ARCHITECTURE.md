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
  config/presets/
    guardrail.json
  scripts/
    middleware_gateway.py
    new_plugin.py
    setup_middleware_gateway.py
  modeio_middleware/
    cli/
      gateway.py
      setup.py
    core/
      config_resolver.py
      context_extractor.py
      contracts.py
      decision.py
      engine.py
      errors.py
      http_contract.py
      plugin_manager.py
      profiles.py
      services/
        defer_queue.py
        telemetry.py
    plugins/
      base.py
      guardrail.py
      guardrail_impl/
        plugin.py
        policy.py
        client.py
        presets.py
      redact.py
  tests/
    test_config_resolver.py
    test_guardrail_plugin_preset.py
    test_gateway_contract.py
    test_smoke_opencode_flow.py
    test_setup_gateway.py
    test_plugin_manager.py
    test_profile_policy.py
```

## Runtime data flow

1. Gateway receives `POST /v1/chat/completions`
2. Core validates request and parses `modeio` metadata
3. Config resolver computes final plugin config (defaults + preset + profile override + request override)
4. Plugin manager runs pre-request hooks
5. Core forwards request to upstream provider
6. Plugin manager runs post-response hooks
7. Gateway returns provider-compatible JSON + middleware headers

## Integration boundaries

- `plugins/base.py` defines plugin contract
- Plugins can return dict payloads or typed `HookDecision`
- Plugins can `allow`, `modify`, `warn`, `defer`, or `block`
- Existing skills integrate as optional plugin modules
- Core does not hardcode guardrail/redact decisions
- Presets are registry-driven (`config/presets/*.json`)
- Runtime shared services are injected via `hook_input["services"]`

## Compatibility and safety

- v1 supports non-streaming and streaming passthrough
- setup script supports safe OpenCode patch/unpatch with backup
- Codex integration is environment-based (`OPENAI_BASE_URL`)
