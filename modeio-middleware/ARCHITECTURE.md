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
  MODEIO_PLUGIN_PROTOCOL.md
  MODEIO_PLUGIN_MANIFEST.schema.json
  MODEIO_PLUGIN_MESSAGE.schema.json
  PROTOCOL_IMPLEMENTATION_PLAN.md
  scripts/
    middleware_gateway.py
    new_plugin.py
    run_plugin_conformance.py
    setup_middleware_gateway.py
    validate_plugin_manifest.py
  modeio_middleware/
    cli/
      gateway.py
      setup.py
      setup_lib/
        common.py
        opencode.py
        claude.py
    connectors/
      base.py
      claude_hooks.py
    core/
      config_resolver.py
      contracts.py
      decision.py
      engine.py
      errors.py
      http_contract.py
      pipeline_session.py
      plugin_manager.py
      profiles.py
      services/
        defer_queue.py
        telemetry.py
    protocol/
      versions.py
      messages.py
      manifest.py
      validator.py
      jsonpatch.py
    registry/
      resolver.py
      loader.py
    runtime/
      base.py
      legacy_inprocess.py
      stdio_jsonrpc.py
      supervisor.py
    plugins/
      base.py
      redact.py
  tests/
    test_claude_hook_connector.py
    test_config_resolver.py
    test_gateway_contract.py
    test_protocol_manifest.py
    test_protocol_registry.py
    test_protocol_stdio_runtime.py
    test_smoke_opencode_flow.py
    test_setup_gateway.py
    test_plugin_manager.py
    test_profile_policy.py
```

## Runtime data flow

1. Gateway receives `POST /v1/chat/completions`
2. Core validates request and parses `modeio` metadata
3. Config resolver computes final plugin config (defaults + preset + profile override + request override)
4. Registry resolves runtime spec (mode, capabilities, transport)
5. Plugin manager runs pre-request hooks through runtime adapters
6. Core forwards request to upstream provider
7. Plugin manager runs post-response/stream hooks through runtime adapters
8. Gateway returns provider-compatible JSON + middleware headers

Claude hook connector flow:

1. Gateway receives `POST /connectors/claude/hooks`
2. Connector normalizes Claude hook payload into canonical middleware hook input
3. Core resolves profile/plugin runtime and executes plugin pipeline
4. Connector maps policy decision back to Claude hook output contract
5. Gateway returns JSON decision + middleware headers

## Integration boundaries

- `plugins/base.py` defines plugin contract
- Plugins can return dict payloads or typed `HookDecision`
- Plugins can `allow`, `modify`, `warn`, `defer`, or `block`
- In-process plugins run via `runtime/legacy_inprocess.py`
- External plugins run via `runtime/stdio_jsonrpc.py` using MPP v1
- Core does not hardcode plugin-specific policy decisions
- Presets are registry-driven when provided (`config/presets/*.json`)
- Runtime shared services are injected via `hook_input["services"]`
- Mode controls (`observe`, `assist`, `enforce`) keep external plugins non-intrusive by default

## Compatibility and safety

- v1 supports non-streaming and streaming passthrough
- setup script supports safe OpenCode patch/unpatch with backup
- Codex integration is environment-based (`OPENAI_BASE_URL`)
- Claude integration uses native hooks transport (`/connectors/claude/hooks`) while preserving the same plugin protocol and policy runtime
