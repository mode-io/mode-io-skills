---
name: modeio-middleware
description: >-
  Runs a local request/response middleware gateway for OpenAI-compatible chat
  completions. Designed for Codex CLI and OpenCode routing where prompts pass
  through middleware before provider calls and responses pass through middleware
  before returning to users. Core is plugin-driven and decoupled; guardrail and
  redact integration are optional plugins.
---

# Run middleware gateway for Codex/OpenCode

Use this skill when you want pre-request and post-response control in one local gateway.

## Core routes

- `POST /v1/chat/completions` (v1 non-streaming only)
- `GET /healthz`

## Scripts

### `scripts/middleware_gateway.py`

Starts gateway runtime.

```bash
python modeio-middleware/scripts/middleware_gateway.py \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-url "https://api.openai.com/v1/chat/completions"
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

## Contract highlights

- Required response headers:
  - `x-modeio-contract-version`
  - `x-modeio-request-id`
  - `x-modeio-profile`
  - `x-modeio-pre-actions`
  - `x-modeio-post-actions`
  - `x-modeio-degraded`
  - `x-modeio-upstream-called`

- Middleware extension field: top-level `modeio` object in request body.
- `modeio` metadata is stripped before upstream forwarding.

## Resources

- `CONTRACT_AND_IMPLEMENTATION_PLAN.md`
- `ARCHITECTURE.md`
- `QUICKSTART.md`
