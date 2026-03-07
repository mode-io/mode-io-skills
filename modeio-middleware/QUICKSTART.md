# modeio-middleware Quickstart

This quickstart currently assumes a checkout of `mode-io-skills` and a repo-local Python environment.
`modeio-middleware` now has a standalone `pyproject.toml`, but the supported path in this repo remains repo-first.

Use this file in three passes:

1. Start the local gateway and verify `/healthz`.
2. Route one host through it (`Codex`, `OpenCode`, `OpenClaw`, or Claude hooks).
3. Only then move on to external plugin authoring.

## 0) Bootstrap the repo-local Python environment

```bash
python scripts/bootstrap_env.py
source .venv/bin/activate
python scripts/doctor_env.py
```

## 1) Start the gateway

```bash
export MODEIO_GATEWAY_UPSTREAM_API_KEY="<your-upstream-key>"

python modeio-middleware/scripts/middleware_gateway.py \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-chat-url "https://api.openai.com/v1/chat/completions" \
  --upstream-responses-url "https://api.openai.com/v1/responses"
```

## 2) Configure client routing

### Codex CLI

```bash
python modeio-middleware/scripts/setup_middleware_gateway.py --health-check --json
export OPENAI_BASE_URL="http://127.0.0.1:8787/v1"
```

### OpenCode

```bash
python modeio-middleware/scripts/setup_middleware_gateway.py \
  --apply-opencode \
  --create-opencode-config
```

### Claude Code hooks

```bash
python modeio-middleware/scripts/setup_middleware_gateway.py \
  --apply-claude \
  --create-claude-settings
```

This writes `~/.claude/settings.json` hook entries for `UserPromptSubmit` and `Stop`
to `POST http://127.0.0.1:8787/connectors/claude/hooks`.

The live smoke harness covers Claude separately from OpenAI-routed clients: it drives Claude through native hooks and records `/connectors/claude/hooks` traffic with a local hook tap.

## 3) Health check

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

## 4) Send a request through middleware

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

Check middleware headers in response:

- `x-modeio-request-id`
- `x-modeio-profile`
- `x-modeio-pre-actions`
- `x-modeio-post-actions`
- `x-modeio-degraded`

## 5) Use external protocol plugins (optional)

External plugins use `stdio-jsonrpc` and default to non-intrusive `observe` mode.
The shipped example plugin lives under `modeio-middleware/plugins_external/example/`.

Example plugin config entry:

```json
{
  "external_policy": {
    "enabled": false,
    "runtime": "stdio_jsonrpc",
    "manifest": "plugins_external/example/manifest.json",
    "command": ["python3", "plugins_external/example/plugin.py"],
    "mode": "observe",
    "capabilities_grant": {
      "can_patch": false,
      "can_block": false
    }
  }
}
```

Validate and run conformance:

```bash
python modeio-middleware/scripts/validate_plugin_manifest.py plugins_external/example/manifest.json
python modeio-middleware/scripts/run_plugin_conformance.py plugins_external/example/manifest.json python3 plugins_external/example/plugin.py
```

The example plugin is intentionally minimal: it emits an `annotate` decision on `pre.request` and otherwise passes through.
Once this works, use `new_plugin.py` to scaffold your own plugin. The default scaffold is `stdio-jsonrpc`; `legacy_inprocess` remains internal-only for bundled plugins.

## 6) Uninstall / rollback

```bash
python modeio-middleware/scripts/setup_middleware_gateway.py \
  --uninstall \
  --apply-opencode \
  --apply-claude
```

## 7) Scaffold a plugin

```bash
python modeio-middleware/scripts/new_plugin.py my-plugin
python modeio-middleware/scripts/new_plugin.py my-protocol-plugin --runtime stdio_jsonrpc
```
