# Protocol Implementation Plan

This plan tracks protocol-first middleware execution in clear phases.

## Phase 1 - Spec and Schemas

- Publish protocol spec (`MODEIO_PLUGIN_PROTOCOL.md`).
- Add manifest and message schemas.
- Define action mapping and hook names.

Status: done

## Phase 2 - Runtime Abstraction

- Introduce runtime interface (`runtime/base.py`).
- Move current in-process behavior into `runtime/legacy_inprocess.py`.
- Keep backward compatibility for existing plugins.

Status: done

## Phase 3 - Registry and Manifest Loader

- Add runtime spec resolution (`registry/resolver.py`).
- Validate external plugin manifest and runtime mode.
- Resolve capability grants and timeout settings.

Status: done

## Phase 4 - Stdio JSON-RPC Runtime

- Implement subprocess supervisor (`runtime/supervisor.py`).
- Implement stdio runtime (`runtime/stdio_jsonrpc.py`).
- Support initialize/invoke lifecycle and patch translation.

Status: done

## Phase 5 - DX and Conformance

- Add manifest validator script.
- Add protocol conformance runner.
- Add scaffolding support for protocol plugins.

Status: in_progress

## Phase 6 - Scale Hardening

- Add optional runtime pooling for stdio plugins.
- Add circuit breaker and richer timeout policy modules.
- Add richer telemetry export surfaces.

Status: todo
