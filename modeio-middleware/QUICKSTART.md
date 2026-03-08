# modeio-middleware Quickstart

`modeio-middleware` now supports two distinct workflows:

1. Installed operator workflow: use the packaged console scripts.
2. Repo maintainer workflow: use the repo wrappers, smoke scripts, and local test tooling.

This file treats the installed workflow as the public default and calls out repo-only tooling explicitly.

## 1) Install the package

Until it is published, install from the local checkout:

```bash
python -m pip install /path/to/modeio-middleware
```

Repo maintainers can still use the repo-local environment:

```bash
python scripts/bootstrap_env.py
source .venv/bin/activate
python scripts/doctor_env.py
```

## 2) Start the gateway

The installed entry point now ships with a bundled default config.

```bash
export MODEIO_GATEWAY_UPSTREAM_API_KEY="<your-upstream-key>"

modeio-middleware-gateway \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-chat-url "https://api.openai.com/v1/chat/completions" \
  --upstream-responses-url "https://api.openai.com/v1/responses"
```

Repo wrapper equivalent:

```bash
python modeio-middleware/scripts/middleware_gateway.py
```

## 3) Configure client routing

### Codex CLI

```bash
modeio-middleware-setup --health-check --json
export OPENAI_BASE_URL="http://127.0.0.1:8787/v1"
```

### OpenCode

```bash
modeio-middleware-setup \
  --apply-opencode \
  --create-opencode-config
```

### OpenClaw

```bash
modeio-middleware-setup \
  --apply-openclaw \
  --create-openclaw-config
```

### Claude Code hooks

```bash
modeio-middleware-setup \
  --apply-claude \
  --create-claude-settings
```

This writes `~/.claude/settings.json` hook entries for `UserPromptSubmit` and `Stop`
to `POST http://127.0.0.1:8787/connectors/claude/hooks`.

## 4) Health check

```bash
curl -s http://127.0.0.1:8787/healthz
```

Expected shape:

```json
{
  "ok": true,
  "service": "modeio-middleware",
  "version": "0.1.0"
}
```

## 5) Send one request through middleware

```bash
curl -i http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "hello"}
    ],
    "modeio": {
      "profile": "dev"
    }
  }'
```

Check these middleware headers in the response:

- `x-modeio-request-id`
- `x-modeio-profile`
- `x-modeio-pre-actions`
- `x-modeio-post-actions`
- `x-modeio-degraded`

## 6) Author or validate an external plugin

Public external plugins use `stdio-jsonrpc`.

Scaffold a new plugin into the current directory:

```bash
mkdir my-plugin-work
cd my-plugin-work
modeio-middleware-new-plugin my-policy
```

This creates:

- `./plugins_external/my_policy/plugin.py`
- `./plugins_external/my_policy/manifest.json`
- `./tests/test_protocol_plugin_my_policy.py`

Validate and run conformance:

```bash
modeio-middleware-validate-plugin ./plugins_external/my_policy/manifest.json
modeio-middleware-plugin-conformance \
  ./plugins_external/my_policy/manifest.json \
  python3 ./plugins_external/my_policy/plugin.py
```

The bundled default config also ships with a disabled example plugin. Its manifest and script paths are resolved relative to the config file, so if you copy the config elsewhere you should update those relative paths.

## 7) Custom config

Use `--config` to point at your own JSON config:

```bash
modeio-middleware-gateway --config /path/to/middleware.json
```

Important path rule:

- `manifest` paths are resolved relative to the config file.
- `command` arguments that point at existing local files are also resolved relative to the config file.

## 8) Uninstall / rollback

```bash
modeio-middleware-setup \
  --uninstall \
  --apply-opencode \
  --apply-openclaw \
  --apply-claude
```

## 9) Repo-only maintainer validation

These helpers are intentionally repo-only and are not part of the installed package surface:

```bash
# Offline matrix
modeio-middleware/scripts/smoke_e2e.sh

# Live gateway check
modeio-middleware/scripts/smoke_e2e.sh --live

# Live Codex/OpenCode/OpenClaw/Claude matrix via middleware
modeio-middleware/scripts/smoke_e2e.sh --live-agents
```
