# Standalone product handoff

`modeio-middleware` now lives as a standalone product repo:

- Repo: `https://github.com/mode-io/mode-io-middleware`
- Product README: `https://github.com/mode-io/mode-io-middleware/blob/main/README.md`
- Quickstart: `https://github.com/mode-io/mode-io-middleware/blob/main/QUICKSTART.md`
- Architecture: `https://github.com/mode-io/mode-io-middleware/blob/main/ARCHITECTURE.md`
- Plugin protocol: `https://github.com/mode-io/mode-io-middleware/blob/main/MODEIO_PLUGIN_PROTOCOL.md`

## Install

```bash
python -m pip install git+https://github.com/mode-io/mode-io-middleware
```

## Start

```bash
export MODEIO_GATEWAY_UPSTREAM_API_KEY="<your-upstream-key>"

modeio-middleware-gateway \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-chat-url "https://api.openai.com/v1/chat/completions" \
  --upstream-responses-url "https://api.openai.com/v1/responses"
```

## Route supported clients

Codex CLI:

```bash
export OPENAI_BASE_URL="http://127.0.0.1:8787/v1"
```

OpenCode / OpenClaw / Claude Code:

```bash
modeio-middleware-setup --apply-opencode --create-opencode-config
modeio-middleware-setup --apply-openclaw --create-openclaw-config
modeio-middleware-setup --apply-claude --create-claude-settings
```

## Verify

```bash
modeio-middleware-setup --health-check --json
curl -s http://127.0.0.1:8787/healthz
open http://127.0.0.1:8787/modeio/dashboard
curl -s http://127.0.0.1:8787/modeio/api/events
```

Monitoring routes owned by the standalone runtime:

- `GET /modeio/dashboard`
- `GET /modeio/api/events`
- `GET /modeio/api/events/{request_id}`
- `GET /modeio/api/stats`
- `GET /modeio/api/events/live`

## Roll back

```bash
unset OPENAI_BASE_URL
modeio-middleware-setup --uninstall --apply-opencode --apply-openclaw --apply-claude
```

## Product boundary

- Use the standalone repo for runtime code, monitoring/dashboard behavior, plugin-host behavior, packaging, release workflows, and test/smoke issues.
- Use this `mode-io-skills` wrapper for agent-facing install prompts, setup recipes, and safe operator defaults.

## Common handoff cases

- Gateway bug or API behavior question -> standalone repo
- Monitoring dashboard, request journal, or observability API question -> standalone repo
- Plugin protocol, runtime, or conformance issue -> standalone repo
- Agent setup instruction update -> thin skill wrapper
- Product quickstart or contributor validation question -> standalone repo docs
