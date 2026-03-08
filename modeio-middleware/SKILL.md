---
name: modeio-middleware
description: >-
  Runs a local policy gateway for Codex, OpenCode, OpenClaw, and Claude Code.
  Supports `/v1/chat/completions`, `/v1/responses`, and `/connectors/claude/hooks`
  with plugin-based policy hooks, full SSE event handling, and packaged public
  CLI entrypoints for gateway/setup/plugin tooling.
---

# Run middleware gateway for Codex/OpenCode/OpenClaw/ClaudeCode

Use this skill to run or maintain the local policy gateway in front of an OpenAI-compatible upstream.

Two workflows are supported:

- Public operator workflow: installed console scripts such as `modeio-middleware-gateway`.
- Repo maintainer workflow: repo wrappers plus smoke/test tooling from a `mode-io-skills` checkout.

## Core routes

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `POST /connectors/claude/hooks`
- `GET /healthz`

## Public CLI surface

### `modeio-middleware-gateway`

Start the packaged gateway with the bundled default config. It ships with no active plugins enabled:

```bash
modeio-middleware-gateway \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-chat-url "https://api.openai.com/v1/chat/completions" \
  --upstream-responses-url "https://api.openai.com/v1/responses"
```

### `modeio-middleware-setup`

Apply or remove host routing:

```bash
modeio-middleware-setup --health-check

modeio-middleware-setup \
  --apply-opencode \
  --create-opencode-config

modeio-middleware-setup \
  --apply-openclaw \
  --create-openclaw-config

modeio-middleware-setup \
  --apply-claude \
  --create-claude-settings

modeio-middleware-setup \
  --uninstall \
  --apply-opencode \
  --apply-openclaw \
  --apply-claude
```

The setup report now emits `modeio-middleware-gateway ...` as the startup command instead of a repo script path.

### Plugin helper entrypoints

```bash
modeio-middleware-new-plugin my-policy
modeio-middleware-new-plugin my-policy --runtime stdio_jsonrpc --output-dir ./my-plugin-work

modeio-middleware-validate-plugin /path/to/manifest.json
modeio-middleware-plugin-conformance /path/to/manifest.json python3 /path/to/plugin.py
```

`modeio-middleware-new-plugin` writes under the chosen output directory:

- `plugins_external/<plugin_name>/plugin.py`
- `plugins_external/<plugin_name>/manifest.json`
- `tests/test_protocol_plugin_<plugin_name>.py`

`stdio-jsonrpc` is the public plugin surface. `legacy_inprocess` remains internal-only for bundled plugins and tests.

## Repo maintainer workflow

From the repo root:

```bash
python scripts/bootstrap_env.py
python scripts/doctor_env.py
```

Repo wrappers:

```bash
python modeio-middleware/scripts/middleware_gateway.py
python modeio-middleware/scripts/setup_middleware_gateway.py --health-check
python modeio-middleware/scripts/new_plugin.py my-policy
```

Repo-only validation:

```bash
modeio-middleware/scripts/smoke_e2e.sh
modeio-middleware/scripts/smoke_e2e.sh --live
modeio-middleware/scripts/smoke_e2e.sh --live-agents
python modeio-middleware/scripts/smoke_agent_matrix.py
```

Claude Code support is hook-based (`/connectors/claude/hooks`). The live smoke matrix covers Claude with a dedicated hook tap, while Codex/OpenCode/OpenClaw still use upstream tap evidence.

## Behavior notes

- Plugin chain is config-driven; the bundled default config starts with no active plugins.
- A disabled `external_policy_example` stdio plugin is shipped as a scaffold/reference, not as an active policy default.
- Missing `runtime` now defaults to:
  - `legacy_inprocess` when a bundled `module` is configured
  - `stdio_jsonrpc` for external plugin-style configs
- External plugins use `observe`, `assist`, or `enforce`; stdio plugins default to `observe`.
- Runtime pools are configurable with `pool_size`; each request leases one runtime, and the pool scales up to the configured size before reusing workers.
- Requests accept plain JSON or `Content-Encoding` `gzip` / `deflate` / `zstd`.
- `modeio` metadata is stripped before upstream forwarding.
- Claude integration uses hook transport, not `OPENAI_BASE_URL`.
- Relative `manifest` paths and local-file `command` arguments are resolved relative to the config file.

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
- Middleware-generated failures use structured `modeio_error` payloads with stable error codes and `request_id`.

## When not to use

- One-off model calls that do not need local policy routing, hooks, or audit headers
- Standalone analysis tasks where you do not actually want to run a gateway process in front of an upstream
- Direct upstream API calls where local interception would only add overhead

## Resources

- `QUICKSTART.md` — installed-first quickstart and repo maintainer notes
- `ARCHITECTURE.md` — current design and extension points
- `MODEIO_PLUGIN_PROTOCOL.md` — external plugin contract
- `REFACTOR_GUIDE.md` — owner-level refactor rationale and boundaries
