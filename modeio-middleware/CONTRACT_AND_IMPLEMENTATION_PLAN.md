# modeio-middleware Contract and Implementation Plan

> Note (2026-03-05): the built-in guardrail adapter and `guardrail_quiet` preset were intentionally removed from default middleware packaging to prioritize protocol-first plugin integration.

Status: draft for implementation kickoff
Owner: mode-io-skills
Target users: Codex CLI and OpenCode users who want request/response middleware before and after provider calls
Contract version: `0.1.0-draft`

## 1) Product Concept

`modeio-middleware` is a local OpenAI-compatible gateway.

- Request path: `client -> middleware (pre-hooks) -> provider`
- Response path: `provider -> middleware (post-hooks) -> client`

The middleware core stays simple and generic.

- It does not hardcode safety/privacy logic.
- It executes plugin hooks.
- `modeio-guardrail` and `modeio-redact` are optional plugins, not core dependencies.

## 2) Scope and Non-Goals

### v1 scope

- OpenAI-compatible endpoint: `POST /v1/chat/completions`
- Non-streaming only (`stream=false`)
- Health endpoint: `GET /healthz`
- Plugin hook execution for pre-request and post-response
- Setup/unsetup script for Codex CLI and OpenCode
- Structured operational headers and JSON error contract

### v1 non-goals

- No SSE streaming transform in v1
- No `POST /v1/responses` in v1
- No UI/dashboard
- No mandatory external backend dependency for base pass-through behavior

## 3) Design Principles

- Simple core: route traffic and run hooks
- Stable contracts: versioned hook I/O and gateway error schema
- Config-driven behavior: profiles and plugin chain from config file
- Graceful degradation: configurable fail-open/fail-safe per environment
- Backward compatibility: client receives provider-compatible payloads

## 4) Runtime Contract

## 4.1 Endpoints

### `GET /healthz`

Response `200`:

```json
{
  "ok": true,
  "service": "modeio-middleware",
  "version": "0.1.0"
}
```

### `POST /v1/chat/completions`

- Accept OpenAI-compatible JSON body
- Reject `stream=true` in v1 with `400` + middleware error payload
- Forward upstream request after pre-hook pipeline
- Process upstream JSON through post-hook pipeline

## 4.2 Middleware extension field

Top-level optional field in inbound request:

```json
{
  "model": "gpt-4o-mini",
  "messages": [{"role": "user", "content": "..."}],
  "modeio": {
    "profile": "dev",
    "plugins": {
      "guardrail": {"enabled": true},
      "redact": {"enabled": true}
    },
    "on_plugin_error": "warn"
  }
}
```

Rules:

- `modeio` is middleware-only metadata
- Middleware strips `modeio` before forwarding upstream
- If `modeio` is invalid type, return `400 MODEIO_VALIDATION_ERROR`

## 4.3 Response compatibility

- Body should remain provider-compatible JSON shape
- Middleware can transform text fields via plugins
- Middleware always appends operational headers

Required response headers:

- `x-modeio-contract-version`
- `x-modeio-request-id`
- `x-modeio-profile`
- `x-modeio-pre-actions`
- `x-modeio-post-actions`
- `x-modeio-degraded`
- `x-modeio-upstream-called`

## 4.4 Error payload contract

All middleware-generated errors use:

```json
{
  "error": {
    "message": "human-readable message",
    "type": "modeio_error",
    "code": "MODEIO_VALIDATION_ERROR",
    "request_id": "req_abc123",
    "retryable": false,
    "details": {
      "field": "modeio.profile"
    }
  }
}
```

Common error codes:

- `MODEIO_VALIDATION_ERROR`
- `MODEIO_UNSUPPORTED_STREAMING`
- `MODEIO_PLUGIN_BLOCKED`
- `MODEIO_PLUGIN_ERROR`
- `MODEIO_UPSTREAM_ERROR`
- `MODEIO_UPSTREAM_TIMEOUT`

## 5) Plugin Hook Contract

## 5.1 Plugin manifest

Each plugin registers:

- `name` (unique)
- `version`
- `hooks` supported (`pre_request`, `post_response`)
- `default_enabled`

## 5.2 Hook interfaces

### Pre-request hook input

```python
{
  "request_id": str,
  "profile": str,
  "request_body": dict,
  "request_headers": dict,
  "context": dict,
  "plugin_config": dict,
}
```

### Pre-request hook output

```python
{
  "action": "allow" | "modify" | "block" | "warn",
  "request_body": dict | None,
  "request_headers": dict | None,
  "findings": [
    {
      "class": str,
      "severity": "low" | "medium" | "high" | "critical",
      "confidence": float,
      "reason": str,
      "evidence": [str]
    }
  ],
  "message": str | None
}
```

### Post-response hook input

```python
{
  "request_id": str,
  "profile": str,
  "request_context": dict,
  "response_body": dict,
  "response_headers": dict,
  "plugin_config": dict,
}
```

### Post-response hook output

```python
{
  "action": "allow" | "modify" | "block" | "warn",
  "response_body": dict | None,
  "response_headers": dict | None,
  "findings": [...],
  "message": str | None
}
```

## 5.3 Plugin execution order

- Pre hooks run in configured order
- Post hooks run in reverse order by default
- If any pre hook returns `block`, middleware returns error and does not call upstream

## 5.4 Plugin error handling policy

Controlled by profile/config:

- `fail_open`: continue request and record degraded status
- `fail_safe`: block request on plugin error
- `warn`: continue with warning finding

Default policy:

- `dev`: `fail_open`
- `staging`: `warn`
- `prod`: `fail_safe`

## 6) Configuration Contract

Default file path: `modeio-middleware/config/default.json`

```json
{
  "version": "0.1",
  "gateway": {
    "host": "127.0.0.1",
    "port": 8787,
    "upstream_url": "https://api.openai.com/v1/chat/completions",
    "upstream_timeout_seconds": 60,
    "upstream_api_key_env": "MODEIO_GATEWAY_UPSTREAM_API_KEY"
  },
  "profiles": {
    "dev": {
      "on_plugin_error": "fail_open",
      "plugins": ["guardrail", "redact"]
    },
    "staging": {
      "on_plugin_error": "warn",
      "plugins": ["guardrail", "redact"]
    },
    "prod": {
      "on_plugin_error": "fail_safe",
      "plugins": ["guardrail", "redact"]
    }
  },
  "plugins": {
    "guardrail": {
      "enabled": false,
      "module": "modeio_middleware.plugins.guardrail"
    },
    "redact": {
      "enabled": false,
      "module": "modeio_middleware.plugins.redact"
    }
  }
}
```

Note: plugins are listed but disabled by default in v1 starter mode.

## 7) OpenCode and Codex Integration Contract

## 7.1 Setup script

`scripts/setup_middleware_gateway.py`

Required capabilities:

- Print Codex shell command to set/unset `OPENAI_BASE_URL`
- Optional OpenCode config patch with backup
- Optional health check against middleware `healthz`
- JSON report mode
- Safe uninstall behavior

Suggested CLI flags:

- `--gateway-base-url http://127.0.0.1:8787/v1`
- `--apply-opencode`
- `--apply-claude`
- `--create-opencode-config`
- `--create-claude-settings`
- `--opencode-config-path <path>`
- `--claude-settings-path <path>`
- `--health-check`
- `--json`
- `--uninstall`
- `--force-remove-opencode-base-url`
- `--force-remove-claude-hook-url`

## 7.2 Setup JSON report contract

```json
{
  "success": true,
  "tool": "modeio-middleware-setup",
  "gateway": {
    "baseUrl": "http://127.0.0.1:8787/v1",
    "health": {
      "checked": true,
      "ok": true,
      "statusCode": 200,
      "message": "healthy"
    }
  },
  "codex": {
    "setCommand": "export OPENAI_BASE_URL=\"http://127.0.0.1:8787/v1\"",
    "unsetCommand": "unset OPENAI_BASE_URL"
  },
  "opencode": {
    "path": "~/.config/opencode/opencode.json",
    "changed": true,
    "backupPath": "..."
  }
}
```

## 7.3 Codex integration notes

- Codex routing is session-scoped via `OPENAI_BASE_URL`
- Setup script should detect shell flavor and print proper command
- Unsetup should always print corresponding unset command

## 7.4 OpenCode integration notes

- Patch `provider.openai.options.baseURL`
- Preserve existing keys and unrelated provider config
- On uninstall, remove baseURL only when it matches target gateway URL by default

## 8) Project Structure Plan

```text
modeio-middleware/
  SKILL.md
  ARCHITECTURE.md
  QUICKSTART.md
  config/
    default.json
  scripts/
    middleware_gateway.py
    setup_middleware_gateway.py
  modeio_middleware/
    __init__.py
    cli/
      gateway.py
      setup.py
    core/
      contracts.py
      engine.py
      errors.py
      http_contract.py
      plugin_manager.py
      profiles.py
    plugins/
      base.py
      guardrail.py
      redact.py
  tests/
    test_gateway_contract.py
    test_setup_gateway.py
    test_plugin_manager.py
    test_profile_policy.py
```

## 9) Detailed Implementation Plan

## Phase 0 - Contract freeze

Deliverables:

- Finalize this contract doc
- Freeze error codes and response header names
- Freeze plugin hook request/response structures

Acceptance criteria:

- Team agreement on versioned contract `0.1.0`

## Phase 1 - Core pass-through gateway

Tasks:

- Implement gateway server for `POST /v1/chat/completions` + `GET /healthz`
- Implement request ID generation and response operational headers
- Implement upstream call with retry on transient errors
- Enforce v1 non-streaming rule

Acceptance criteria:

- Pass-through works with Codex/OpenCode when no plugins enabled
- Contract tests for validation and upstream failure envelope pass

## Phase 2 - Plugin manager and hook runtime

Tasks:

- Implement plugin base interface
- Implement plugin discovery/registration from config
- Implement pre and post hook pipelines
- Implement policy-based plugin error handling (`fail_open`/`warn`/`fail_safe`)

Acceptance criteria:

- Mock plugins can `allow/modify/block` request and response
- Plugin errors follow profile policy and set degraded header

## Phase 3 - Setup/unsetup integration tooling

Tasks:

- Implement `setup_middleware_gateway.py`
- Add Codex shell command generation and uninstall command output
- Add OpenCode config patch/unpatch with backup logic
- Add JSON report output and health-check support

Acceptance criteria:

- Setup works on macOS/Linux/Windows path conventions
- Uninstall is safe and idempotent

## Phase 4 - Optional adapters

Tasks:

- Add `guardrail` plugin adapter
- Add `redact` plugin adapter
- Keep adapters disabled by default in config

Acceptance criteria:

- Core middleware still runs without adapters
- Enabling one plugin does not require enabling the other

## Phase 5 - Docs and demo hardening

Tasks:

- Add `SKILL.md`, `QUICKSTART.md`, and README snippets
- Add copy-paste setup examples for Codex/OpenCode
- Add troubleshooting for auth/baseURL mismatch and health checks

Acceptance criteria:

- New user can install, start gateway, route client, and verify in under 5 minutes

## 10) Test Plan

Contract tests:

- invalid `modeio` payload
- `stream=true` rejection
- upstream timeout/network failure envelope
- required headers always present

Plugin tests:

- pre-hook modify request body
- post-hook modify response content
- pre-hook block without upstream call
- plugin runtime error under each profile policy

Setup tests:

- Codex command generation for bash/zsh/fish/powershell/cmd
- OpenCode patch with nested config preservation
- uninstall mismatch-safe behavior
- JSON report schema assertions

Integration smoke tests:

- launch local fake upstream server
- route request through middleware
- verify request/response transformations and headers

## 11) Operational Defaults

- Host: `127.0.0.1`
- Port: `8787`
- Upstream timeout: `60s`
- Retry: transient `502/503/504` + connection/timeout
- Max retries: `2`

## 12) Future Extensions (post-v1)

- Streaming support for chat completions
- `POST /v1/responses` endpoint support
- Plugin marketplace manifest and signed plugin loading
- Per-plugin latency budgets and metrics endpoint
