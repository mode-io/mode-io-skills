# modeio-middleware Quickstart

## 1) Start the gateway

```bash
export MODEIO_GATEWAY_UPSTREAM_API_KEY="<your-upstream-key>"

python modeio-middleware/scripts/middleware_gateway.py \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-url "https://api.openai.com/v1/chat/completions"
```

## 2) Configure client routing

### Codex CLI

```bash
export OPENAI_BASE_URL="http://127.0.0.1:8787/v1"
```

### OpenCode

```bash
python modeio-middleware/scripts/setup_middleware_gateway.py \
  --client opencode \
  --apply-opencode \
  --create-opencode-config
```

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

## 5) Uninstall / rollback

```bash
python modeio-middleware/scripts/setup_middleware_gateway.py \
  --client both \
  --uninstall \
  --apply-opencode
```
