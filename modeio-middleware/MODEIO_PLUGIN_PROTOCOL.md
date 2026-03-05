# ModeIO Plugin Protocol (MPP) v1

MPP defines a stable contract between `modeio-middleware` and external policy plugins.

## Goals

- Keep middleware core generic and non-plugin-specific.
- Make integrations language-agnostic.
- Default to non-intrusive behavior.
- Scale to many community plugins with strict runtime safety.

## Versioning

- Protocol name: `modeio-plugin-protocol`
- Current version: `1.0`
- Compatibility rule: host accepts explicit supported versions only.

## Transport

v1 transport is `stdio-jsonrpc`.

- Message format: JSON-RPC 2.0
- Wire framing: one JSON object per line (`\n` delimited)
- Process model: host-managed subprocess

## Lifecycle Methods

- `modeio.initialize`
- `modeio.invoke`
- `modeio.shutdown`

### `modeio.initialize`

Request params:

```json
{
  "protocol_version": "1.0",
  "plugin_name": "example/policy"
}
```

Response result:

```json
{
  "protocol_version": "1.0",
  "name": "example/policy"
}
```

### `modeio.invoke`

Request params:

```json
{
  "hook": "pre.request",
  "input": {
    "request_id": "req_...",
    "endpoint_kind": "chat_completions",
    "profile": "dev",
    "source": "openai_gateway",
    "source_event": "http_request",
    "surface_capabilities": {
      "can_patch": true,
      "can_block": true,
      "can_defer": true
    },
    "plugin_config": {},
    "request_body": {}
  }
}
```

Response result:

```json
{
  "decision": {
    "action": "annotate",
    "message": "example",
    "findings": []
  }
}
```

`decision` can also be returned as the top-level object.

Optional host metadata fields may be present in `input` for connector-aware plugins:

- `source`: host connector identifier (for example `openai_gateway`, `claude_hooks`)
- `source_event`: connector-native event name
- `surface_capabilities`: connector action support map (`can_patch`, `can_block`, `can_defer`)
- `native_event`: sanitized connector-native payload when available

## Hooks

- `pre.request`
- `post.response`
- `post.stream.start`
- `post.stream.event`
- `post.stream.end`

## Actions

Protocol actions:

- `pass`
- `annotate`
- `patch`
- `defer`
- `block`

Host mapping to middleware actions:

- `pass -> allow`
- `annotate -> warn`
- `patch -> modify`
- `defer -> defer`
- `block -> block`

Patch action uses RFC6902 operations (`add`, `replace`, `remove`) plus `patch_target`.

## Non-Intrusive Modes

Each plugin runs with one host mode:

- `observe` (default for external plugins)
- `assist`
- `enforce`

Downgrade rules:

- `observe`: `modify`, `defer`, `block` are downgraded to `warn`
- `assist`: `block` is downgraded to `warn`
- `enforce`: no mode downgrade

## Capability Grants

Manifest capabilities do not imply permission. Host grants are explicit.

Enforced capability gates:

- `can_patch`
- `can_block`
- `can_defer`

If not granted, corresponding action is downgraded to `warn`.

## Timeouts

Per-hook timeout budgets are enforced by host. Defaults:

- `pre.request`: 150ms
- `post.response`: 120ms
- `post.stream.start`: 120ms
- `post.stream.event`: 30ms
- `post.stream.end`: 80ms

Plugin manifest/config can tighten or relax these values.

## Error Handling

- Plugin process failure: handled by profile `on_plugin_error` policy.
- JSON-RPC error response: treated as plugin failure.
- Timeout: treated as plugin failure.

## Security and Operational Notes

- External plugins run as local subprocesses.
- Plugins should not log protocol frames to stdout.
- Any plugin diagnostics should go to stderr.
