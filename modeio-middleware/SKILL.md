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

Setup/unsetup assistant for Codex/OpenCode routing.

```bash
python modeio-middleware/scripts/setup_middleware_gateway.py --client both

python modeio-middleware/scripts/setup_middleware_gateway.py \
  --client opencode \
  --apply-opencode \
  --create-opencode-config

python modeio-middleware/scripts/setup_middleware_gateway.py \
  --client both \
  --uninstall \
  --apply-opencode
```

## Behavior notes

- Core middleware is generic; plugin chain is config-driven (`config/default.json`).
- Default plugin definitions include `guardrail` and `redact`, both disabled by default.
- Profile policy controls plugin-error behavior (`fail_open`, `warn`, `fail_safe`).
- Stream pipeline supports `post_stream_start`, `post_stream_event`, and `post_stream_end` hooks.

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
