# Prompt Shield Gateway Quickstart

Optional but recommended for Codex CLI and OpenCode.

The `modeio-redact` skill works without this gateway. If you skip gateway mode, you can still run:

- `scripts/anonymize.py` before external sharing
- `scripts/deanonymize.py` after receiving masked output

Gateway mode is recommended because it automates shield/unshield around OpenAI-compatible chat completion requests.

## 0) Optional setup assistant (recommended)

Run once to get OS-aware setup guidance and optional OpenCode config patching:

```bash
python modeio-redact/scripts/setup_prompt_gateway.py --client both
```

If you prefer a shortcut target:

```bash
make prompt-gateway-setup
```

`make` shortcut is mainly for macOS/Linux shells. On Windows, use the direct `python .../setup_prompt_gateway.py` command.

Apply OpenCode `baseURL` automatically (with backup):

```bash
python modeio-redact/scripts/setup_prompt_gateway.py \
  --client opencode \
  --apply-opencode \
  --create-opencode-config
```

Machine-readable report:

```bash
python modeio-redact/scripts/setup_prompt_gateway.py --client both --json
```

## How it works

```
Client (Codex/OpenCode)
  -> http://127.0.0.1:8787/v1/chat/completions
  -> shield (local PII masking)
  -> upstream model provider
  -> unshield (restore original values)
  -> client
```

## 1) Start the local gateway

From repo root:

```bash
export MODEIO_GATEWAY_UPSTREAM_API_KEY="<your-upstream-key>"

python modeio-redact/scripts/prompt_gateway.py \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-url "https://api.openai.com/v1/chat/completions"
```

Health check:

```bash
curl -s http://127.0.0.1:8787/healthz
```

## 2) Point your client to the gateway

### Codex CLI (quickest path)

Codex supports overriding the built-in OpenAI endpoint with `OPENAI_BASE_URL`.

```bash
export OPENAI_BASE_URL="http://127.0.0.1:8787/v1"
codex
```

If your Codex auth mode is ChatGPT and upstream returns auth/model errors, switch Codex to API-key auth for gateway mode.

### OpenCode (persistent config)

In `~/.config/opencode/opencode.json`, configure your provider to use:

`baseURL: "http://127.0.0.1:8787/v1"`

Example pattern:

```json
{
  "model": "openai/gpt-4o-mini",
  "provider": {
    "openai": {
      "options": {
        "baseURL": "http://127.0.0.1:8787/v1",
        "apiKey": "<your-openai-api-key>"
      }
    }
  }
}
```

## 3) Verify end-to-end

Run a direct request through the gateway:

```bash
curl -i http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "user", "content": "Email alice@example.com and phone 415-555-1234"}
    ],
    "modeio": {"policy": "strict", "allow_degraded_unshield": true}
  }'
```

Look for response headers:

- `x-modeio-shielded: true`
- `x-modeio-redaction-count: <n>`
- `x-modeio-upstream-called: true`
- `x-modeio-degraded: none` (or `unshield_failed` in degraded-safe mode)

## Common notes

- v1 supports `POST /v1/chat/completions` with non-streaming (`stream=false`) only.
- Text content is shielded; non-text message parts are passed through in v1.
- Keep this optional: users can stay on manual `anonymize.py` + `deanonymize.py` if they prefer explicit control.

## Uninstall in one command (optional)

If you want to roll back OpenCode config and clean local gateway-generated map files:

```bash
make prompt-gateway-uninstall
```

`make` shortcut is mainly for macOS/Linux shells. On Windows, run the direct Python command below.

Equivalent direct command:

```bash
python modeio-redact/scripts/setup_prompt_gateway.py \
  --client both \
  --uninstall \
  --apply-opencode \
  --cleanup-maps
```

Notes:

- For Codex, uninstall prints the shell command to unset `OPENAI_BASE_URL`.
- OpenCode rollback only removes `provider.openai.options.baseURL` when it matches your gateway URL (safe default).
- Map cleanup removes local map files with `sourceMode: gateway-local` only.
