---
name: modeio-middleware
description: >-
  Runs a local OpenAI-compatible middleware gateway for
  Codex/OpenCode/OpenClaw/ClaudeCode routing.
  Supports `/v1/chat/completions` and `/v1/responses` with
  streaming pass-through, request body decoding, and
  plugin-based pre/post policy hooks.
---

# Run middleware gateway for Codex/OpenCode/OpenClaw/ClaudeCode

Use this skill to run a local policy gateway in front of an OpenAI-compatible upstream for Codex, OpenCode, OpenClaw, or Claude Code.

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

Setup/unsetup helper for Codex/OpenCode/OpenClaw/ClaudeCode routing.

```bash
python modeio-middleware/scripts/setup_middleware_gateway.py --health-check

python modeio-middleware/scripts/setup_middleware_gateway.py \
  --apply-opencode \
  --create-opencode-config

python modeio-middleware/scripts/setup_middleware_gateway.py \
  --apply-openclaw \
  --create-openclaw-config

python modeio-middleware/scripts/setup_middleware_gateway.py \
  --apply-claude \
  --create-claude-settings

python modeio-middleware/scripts/setup_middleware_gateway.py \
  --uninstall \
  --apply-opencode \
  --apply-openclaw \
  --apply-claude
```

### `scripts/smoke_e2e.sh`

Runs deterministic smoke checks.

```bash
# Offline matrix
modeio-middleware/scripts/smoke_e2e.sh

# Live gateway check
modeio-middleware/scripts/smoke_e2e.sh --live

# Live Codex/OpenCode/OpenClaw matrix via middleware
modeio-middleware/scripts/smoke_e2e.sh --live-agents
```

Claude Code support is hook-based (`/connectors/claude/hooks`) and validated via connector tests.

### `scripts/smoke_agent_matrix.py`

Runs host-sandboxed live agent matrix with tap-proxy evidence output.

```bash
python modeio-middleware/scripts/smoke_agent_matrix.py \
  --upstream-base-url "https://zenmux.ai/api/v1" \
  --model "openai/gpt-5.3-codex"
```

### `scripts/new_plugin.py`

Scaffold a new plugin and a matching test.

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

- Plugin chain is config-driven (`config/default.json`); a bundled `redact` plugin exists but is disabled by default (`"enabled": false`).
- External plugins use `stdio-jsonrpc` with ModeIO Plugin Protocol v1.
- Runtime modes: `observe`, `assist`, `enforce` (external plugins default to `observe`).
- Requests accept plain JSON or `Content-Encoding` `gzip`/`deflate`/`zstd`.
- Claude integration uses hook transport (`/connectors/claude/hooks`), not `OPENAI_BASE_URL` routing.
- Top-level `modeio` metadata in request body is stripped before upstream forwarding.

## Output contract

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
- Middleware-generated failures use structured `modeio_error` payloads with stable error codes and `request_id`.

## When not to use

- PII anonymization or de-anonymization (`modeio-redact`)
- Command safety analysis or skill repo scanning (`modeio-guardrail`)
- Direct upstream API calls without local policy control

## Resources

- `scripts/middleware_gateway.py` — CLI entry point for gateway runtime
- `scripts/setup_middleware_gateway.py` — CLI entry point for setup/uninstall
- `scripts/smoke_e2e.sh` — deterministic smoke test runner
- `scripts/smoke_agent_matrix.py` — live agent matrix with tap-proxy evidence
- `QUICKSTART.md` — setup and usage guide
- `ARCHITECTURE.md` — design and extension points
- `MODEIO_PLUGIN_PROTOCOL.md` — external plugin protocol reference
- `MODEIO_GATEWAY_UPSTREAM_API_KEY` env var — upstream API key for gateway routing
