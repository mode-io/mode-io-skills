---
name: modeio-middleware
description: >-
  Installs, starts, and routes agent traffic through the standalone
  `modeio-middleware` product repo. Use this thin skill wrapper to connect
  Codex, OpenCode, OpenClaw, and Claude Code to the local policy gateway.
---

# Run standalone middleware gateway for Codex, Claude Code, OpenCode, and OpenClaw

Use this skill when you want an agent to install, start, verify, or wire up the standalone `modeio-middleware` runtime from `https://github.com/mode-io/mode-io-middleware`.

## What this skill wraps

- Standalone product repo: `https://github.com/mode-io/mode-io-middleware`
- Product quickstart: `https://github.com/mode-io/mode-io-middleware/blob/main/QUICKSTART.md`
- Architecture: `https://github.com/mode-io/mode-io-middleware/blob/main/ARCHITECTURE.md`
- Plugin contract: `https://github.com/mode-io/mode-io-middleware/blob/main/MODEIO_PLUGIN_PROTOCOL.md`

## Core routes

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /connectors/claude/hooks`
- `GET /healthz`

## Recommended operator flow

### 1) Install the standalone runtime

From GitHub:

```bash
python -m pip install git+https://github.com/mode-io/mode-io-middleware
```

From a local checkout:

```bash
python -m pip install /path/to/mode-io-middleware
```

### 2) Start the gateway

```bash
export MODEIO_GATEWAY_UPSTREAM_API_KEY="<your-upstream-key>"

modeio-middleware-gateway \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-chat-url "https://api.openai.com/v1/chat/completions" \
  --upstream-responses-url "https://api.openai.com/v1/responses"
```

### 3) Route each supported client through middleware

```bash
modeio-middleware-setup --health-check
```

Codex CLI:

```bash
export OPENAI_BASE_URL="http://127.0.0.1:8787/v1"
```

OpenCode:

```bash
modeio-middleware-setup --apply-opencode --create-opencode-config
```

OpenClaw:

```bash
modeio-middleware-setup --apply-openclaw --create-openclaw-config
```

Claude Code:

```bash
modeio-middleware-setup --apply-claude --create-claude-settings
```

### 4) Validate health

```bash
curl -s http://127.0.0.1:8787/healthz
```

### 5) Author or validate an external plugin

```bash
modeio-middleware-new-plugin my-policy
modeio-middleware-validate-plugin /path/to/manifest.json
modeio-middleware-plugin-conformance /path/to/manifest.json python3 /path/to/plugin.py
```

### 6) Roll back local routing

```bash
unset OPENAI_BASE_URL
modeio-middleware-setup --uninstall --apply-opencode --apply-openclaw --apply-claude
```

## Behavior notes

- The standalone product repo is the runtime and packaging source of truth.
- This skill is intentionally thin: it gives agents reliable install/setup/health-check guidance instead of shipping the product implementation.
- Public external plugins use `stdio-jsonrpc`; `legacy_inprocess` remains internal-only in the product repo.
- The bundled default config starts with no active plugins enabled.

## When not to use

- You only need direct upstream API calls and do not want a local gateway process.
- You are editing the middleware product itself; use the standalone repo directly instead.
- You want browser traffic visualization work; that belongs in the standalone product repo, not this skill wrapper.

## References in this repo

- `references/standalone-product.md` — standalone repo handoff, install commands, and operator notes
