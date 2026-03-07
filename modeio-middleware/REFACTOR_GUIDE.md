# modeio-middleware Refactor Guide

This is the refactor plan I would choose if I owned `modeio-middleware` and had one chance to reset the design before publishing it.

The goal is not to preserve every current convenience.
The goal is to publish a middleware that is understandable, scalable, and hard to regret.

## Executive Decision

`modeio-middleware` should become a **policy gateway with OpenAI-style ingress adapters**, not a transparent OpenAI proxy and not a full agent host.

That means:

- Keep the product centered on policy execution around model traffic.
- Keep MPP as the middleware-to-plugin contract.
- Do **not** adopt ACP as the core architecture now.
- Do **not** keep request-scoped plugin runtime creation.
- Do **not** publish `defer` until it actually exists end to end.

This is the direction I would commit to.

## Product Boundary

### Decision

The product is a **policy gateway**.

It accepts traffic from:

- OpenAI-style HTTP clients
- Claude hook events
- future editor or agent connectors

It then:

1. normalizes the request into a canonical internal model
2. runs a policy pipeline
3. forwards to an upstream when allowed
4. transforms the downstream response or stream when required
5. returns a ModeIO-aware contract

### Why

Right now the code sits in an awkward middle:

- it claims “OpenAI-compatible”
- but it does not preserve upstream headers or upstream error bodies faithfully
- and it adds its own headers and error envelope

That is fine for a policy gateway.
It is not fine for a transparent proxy.

So the fix is not “be a little more proxy-like.”
The fix is to choose the correct category and design around it.

### Resulting language

After the refactor, describe it as:

> A local policy gateway with OpenAI-compatible ingress routes and connector adapters.

Not:

> A transparent OpenAI-compatible proxy.

## Architecture Decision

### Decision

Move to a **typed service core + connector adapters + runtime manager** architecture.

Target shape:

```text
transport/
  http/
    app.py
    routes_openai.py
    routes_connectors.py

connectors/
  base.py
  openai_http.py
  claude_hooks.py
  acp.py            # later, not now

domain/
  models.py
  actions.py
  errors.py
  contracts.py

orchestration/
  gateway_service.py
  policy_pipeline.py
  stream_pipeline.py

plugins/
  sdk/
  builtins/
  runtimes/
    manager.py
    legacy_inprocess.py
    stdio_jsonrpc.py

config/
  models.py
  loader.py
  resolver.py

upstream/
  client.py
  streaming.py
```

### Why

The current code has decent intent but too much logic lives in dicts and cross-cutting helper calls.
That makes small features easy and large refactors expensive.

The refactor should move the architecture from “script-grade modular” to “service-grade modular.”

## Transport Stack

### Decision

Replace `ThreadingHTTPServer` with an **ASGI app** and replace `requests` with **httpx**.

I would use:

- `Starlette` or `FastAPI` for transport
- `httpx` for upstream calls and streaming
- `uvicorn` as the runtime entry point

### Why

The current server stack is good for a local spike.
It is not the right long-term base for:

- many concurrent requests
- longer-lived streams
- connector growth
- standardized middleware behavior

ASGI also makes it easier to test transport concerns separately from policy concerns.

### Decision detail

I would keep the transport thin.
The ASGI layer should do only:

- route selection
- request decoding
- connector dispatch
- response encoding

The orchestration layer should do the policy work.

## Plugin Model

### Decision

Public plugin development should standardize on **stdio-jsonrpc only**.

`legacy_inprocess` should remain:

- allowed for built-in plugins
- allowed for internal migration
- not positioned as the public extension model

### Why

Two plugin worlds with different powers create long-term confusion.
Right now in-process plugins can see services and richer shared state that stdio plugins cannot.
That makes external plugins second-class by design.

The right move is:

- public contract: one portable model
- internal convenience: separate and clearly internal

### Runtime lifecycle decision

Plugin runtimes must be **managed and reused**, not created per request.

Introduce a runtime manager keyed by:

- plugin name
- resolved plugin config hash
- runtime type

Responsibilities:

- warm start plugin runtimes
- lease runtimes to requests
- shut down stale runtimes
- expose health and crash metadata

This is mandatory before publication.

## Action Model

### Decision

Public v1 actions should be:

- `allow`
- `warn`
- `modify`
- `block`

Remove `defer` from the public contract for now.

### Why

`defer` currently exists in names only.
That is worse than not having it.

Publishing a fake capability creates:

- misleading plugin contracts
- unclear user expectations
- future backward compatibility problems

If deferred execution matters later, add it back only with:

- an explicit deferred object model
- storage semantics
- replay or review flow
- connector-specific user-facing behavior

Until then, cut it.

## Streaming

### Decision

Redesign streaming around **full SSE events**, not per-line mutation.

### Why

The current stream handling works for a narrow event shape, but it is not a transport abstraction.
It is a heuristic that happens to match current tests.

### Required changes

Introduce:

- an SSE event parser
- an SSE event serializer
- a canonical stream event model
- stream lifecycle reporting that does not rely on final headers

### Contract decision

For streaming, do not pretend headers can carry final policy state.

Instead:

- headers should describe initial stream setup only
- stream-time policy events should be emitted as explicit ModeIO sideband events or recorded in telemetry

If you do not want sideband events, then keep stream policy features intentionally limited.
Do not over-promise.

## Connectors

### Decision

Connectors must become a **real adapter layer**, not special cases in engine code.

Each connector should implement a common interface:

- `parse_incoming(payload, headers) -> CanonicalInvocation`
- `capabilities() -> ConnectorCapabilities`
- `render_result(result) -> ConnectorResponse`
- `name()`

### Why

Right now Claude hooks are a path-specific exception.
That will not scale to:

- more editor integrations
- ACP later
- connector-specific policy behavior

### Canonical internal model

Every connector should normalize into the same internal request shape:

- source
- source event
- endpoint kind
- phase
- request body
- response body
- profile
- plugin overrides
- connector capabilities
- native metadata

That should be a typed model, not a dict.

## Upstream Compatibility

### Decision

Be explicit that the gateway has its own contract.

Then decide one of these two modes:

1. `proxy_mode`
2. `policy_mode`

I would ship **policy mode only** first.

### Why

A fake proxy is harder to reason about than an honest gateway.
If you later need transparent passthrough, add it as a separate mode with explicit guarantees.

### Policy mode rules

- upstream success body may be transformed
- upstream error body may be normalized
- ModeIO headers are authoritative
- request `modeio` metadata is consumed internally

That is coherent.

## Config System

### Decision

Replace raw-dict config with typed config models.

I would use `pydantic` for:

- global config
- profile config
- plugin config
- runtime config
- manifest loading
- request-side overrides

### Why

The current code spreads validation and merge semantics across multiple files.
That makes the configuration system flexible but not dependable.

### Config rules I would enforce

- one canonical merge order
- explicit forbidden override fields
- resolved config objects must be immutable
- config hashing must be stable for runtime pooling

## Built-in Plugins

### Decision

Built-in plugins should move under an explicit internal namespace and stop depending on monorepo sibling imports.

I would choose one of two options:

1. keep built-ins in the middleware package and vendor their minimal logic
2. split them into separately installable packages with extras

I would pick **option 2** if publication is serious.

Recommended shape:

- `modeio-middleware`
- `modeio-middleware-redact`
- later `modeio-middleware-guardrail`

### Why

Monorepo-relative imports are acceptable for internal development and unacceptable for public packaging.

## ACP Decision

### Decision

Do **not** adopt ACP in the first refactor wave.

Revisit ACP only after:

1. connector architecture exists
2. runtime manager exists
3. packaging is standalone
4. MPP is stable

### Why

ACP solves a different problem:

- ACP is client/editor to agent host control-plane
- MPP is middleware to policy-plugin execution-plane

If we adopt ACP too early, we will blur the product boundary and turn a policy gateway into an accidental agent runtime.

### When ACP becomes relevant

ACP becomes useful when you want:

- editor-native session control
- approvals
- terminal/filesystem mediated through a standard client protocol
- a richer “ModeIO as agent host” story

That is a real future path.
It is not the first milestone.

## What I Would Build First

### Phase 1: Boundary Reset

Deliverables:

- rewrite product language around policy gateway
- remove `defer` from public contract
- mark `legacy_inprocess` as internal
- add characterization tests around current behavior that must survive

Exit criteria:

- no public doc claims transparent proxy semantics
- no fake public action remains

### Phase 2: Typed Core

Deliverables:

- typed request, response, stream event, and config models
- new `GatewayService`
- new `PolicyPipeline`
- new connector interface

Exit criteria:

- engine no longer passes raw dicts across every layer
- Claude hook path uses the same canonical invocation flow as OpenAI ingress

### Phase 3: Runtime Manager

Deliverables:

- pooled stdio runtime manager
- config-hash keyed runtime instances
- health, crash, and restart behavior
- shutdown lifecycle

Exit criteria:

- stdio plugins are not spawned per request
- performance profile is stable under repeated calls

### Phase 4: ASGI Transport

Deliverables:

- ASGI app
- `httpx` upstream client
- proper streaming implementation
- transport tests separated from policy tests

Exit criteria:

- stdlib HTTP server removed from the main runtime path
- streaming tests cover multi-event and failure cases

### Phase 5: Plugin SDK and Packaging

Deliverables:

- standalone package metadata
- console entry points
- public plugin SDK docs
- separate built-in plugin packaging strategy

Exit criteria:

- middleware can be installed without the monorepo
- example plugin works from installed package docs

### Phase 6: ACP Connector Evaluation

Deliverables:

- ACP adapter prototype as a connector
- explicit decision on whether ModeIO wants agent-host responsibilities

Exit criteria:

- ACP adoption is based on a connector use case, not curiosity

## What I Would Not Do

- I would not keep `defer` as a no-op.
- I would not keep per-request stdio plugin process startup.
- I would not publish “transparent OpenAI-compatible proxy” wording.
- I would not treat Claude hooks as the pattern for all future connectors.
- I would not make ACP the core before the middleware core is stable.

## Final Recommendation

If we are serious about this skill, I would authorize a **large refactor now**.

I would not publish the current structure as the long-term architecture.

The refactor should be decisive, not incremental:

1. choose policy gateway as the product
2. simplify the public contract
3. build typed internals
4. add a real runtime manager
5. move to ASGI
6. package it cleanly
7. revisit ACP later

That is the path I would choose.
