---
name: modeio-middleware
description: >-
  Runs a local OpenAI-compatible middleware gateway for Codex/OpenCode routing.
  Supports `/v1/chat/completions` and `/v1/responses`, including streaming pass-through,
  with plugin-based pre-request and post-response/post-stream hooks.
---

# Run middleware gateway for Codex/OpenCode

Use this skill when you need runtime request/response control in a local proxy.

## Core routes

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /connectors/claude/hooks`
- `GET /healthz`

## Scripts

### `scripts/middleware_gateway.py`

Starts gateway runtime.

```bash
python modeio-middleware/scripts/middleware_gateway.py \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-chat-url "https://api.openai.com/v1/chat/completions" \
  --upstream-responses-url "https://api.openai.com/v1/responses"
```

### `scripts/setup_middleware_gateway.py`

Setup/unsetup assistant for Codex/OpenCode/Claude routing.

```bash
python modeio-middleware/scripts/setup_middleware_gateway.py

python modeio-middleware/scripts/setup_middleware_gateway.py \
  --apply-opencode \
  --create-opencode-config

python modeio-middleware/scripts/setup_middleware_gateway.py \
  --apply-claude \
  --create-claude-settings

python modeio-middleware/scripts/setup_middleware_gateway.py \
  --uninstall \
  --apply-opencode \
  --apply-claude
```

### `scripts/new_plugin.py`

Scaffold a new plugin and a matching unit test.

```bash
python modeio-middleware/scripts/new_plugin.py my-plugin
python modeio-middleware/scripts/new_plugin.py my-protocol-plugin --runtime stdio_jsonrpc
```

### `scripts/validate_plugin_manifest.py`

Validate an external protocol plugin manifest.

```bash
python modeio-middleware/scripts/validate_plugin_manifest.py /path/to/manifest.json
```

### `scripts/run_plugin_conformance.py`

Run basic stdio protocol conformance checks.

```bash
python modeio-middleware/scripts/run_plugin_conformance.py /path/to/manifest.json python3 /path/to/plugin.py
```

## Behavior notes

- Core middleware is generic; plugin chain is config-driven (`config/default.json`).
- Default bundled plugin definition includes `redact` (disabled by default).
- Presets are optional and resolved in core when supplied by config.
- Profile policy controls plugin-error behavior (`fail_open`, `warn`, `fail_safe`).
- External plugins use `stdio-jsonrpc` with ModeIO Plugin Protocol v1.
- External runtime mode defaults to `observe` for non-intrusive behavior.
- Runtime modes: `observe`, `assist`, `enforce`.
- Plugins receive shared runtime services in `hook_input["services"]` (telemetry, defer queue).
- Stream pipeline supports `post_stream_start`, `post_stream_event`, and `post_stream_end` hooks.
- Claude hooks connector uses native Claude hook transport but maps decisions through the same plugin runtime/protocol.

## Contract highlights

- Required response headers:
  - `x-modeio-contract-version`
  - `x-modeio-request-id`
  - `x-modeio-profile`
  - `x-modeio-pre-actions`
  - `x-modeio-post-actions`
  - `x-modeio-degraded`
  - `x-modeio-upstream-called`
- Streaming responses also include:
  - `x-modeio-streaming: true`
- Middleware extension field: top-level `modeio` object in request body.
- `modeio` metadata is stripped before upstream forwarding.

## Resources

- `CONTRACT_AND_IMPLEMENTATION_PLAN.md`
- `ARCHITECTURE.md`
- `QUICKSTART.md`
- `MODEIO_PLUGIN_PROTOCOL.md`
- `PROTOCOL_IMPLEMENTATION_PLAN.md`
