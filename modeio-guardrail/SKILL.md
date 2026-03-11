---
name: modeio-guardrail
description: >-
  Runs a backend-backed live safety check for instructions that may trigger
  tool execution, external calls, file edits, permission changes, destructive
  or irreversible actions, prompt injection, or compliance-sensitive
  operations. Use before executing instructions with side effects; skip pure
  read-only chat, planning, or pre-install repository auditing.
version: 0.1.0
metadata:
  openclaw:
    homepage: https://github.com/mode-io/mode-io-skills/tree/main/modeio-guardrail
    requires:
      bins:
        - python3
---

# Run backend-backed live safety checks

Use this skill to gate instructions that may trigger tools or state changes behind a backend-backed safety decision before execution.

This skill is for live instruction and operation safety only. For pre-install repository auditing, use `modeio-skill-audit`.

Tests are maintainer-only contract coverage and are excluded from ClawHub uploads.

## Tool routing

1. Use `scripts/safety.py` for instruction and operation safety checks.
2. Run the check before executing any instruction that may trigger tool use, external calls, file edits, permission changes, or other state changes.
3. For state-changing work, provide both `--context` and `--target` so the backend has enough context to judge risk.
4. If the safety check cannot be completed, treat the operation as unverified.

## Dependencies

- Hard requirement: `python3`
- Required package for successful live checks: `requests`
- Required runtime condition: network reachability to the safety backend
- Optional override: `SAFETY_API_URL`

## Context contract

Pass `--context` as JSON with these keys when the instruction may change state:

```json
{
  "environment": "local-dev|ci|staging|production|unknown",
  "operation_intent": "read-only|cleanup|maintenance|migration|permission-change|destructive|unknown",
  "scope": "single-resource|bounded-batch|broad|unknown",
  "data_sensitivity": "public|internal|sensitive|regulated|unknown",
  "rollback": "easy|partial|none|unknown",
  "change_control": "ticket:<id>|approved-manual|none|unknown"
}
```

`--target` should be a concrete resource identifier such as an absolute path, table name, service name, or URL.

## Script

### `scripts/safety.py`

```bash
python3 scripts/safety.py -i "Delete /tmp/cache/build-123.log" \
  -c '{"environment":"local-dev","operation_intent":"cleanup","scope":"single-resource","data_sensitivity":"internal","rollback":"easy","change_control":"none"}' \
  -t "/tmp/cache/build-123.log" --json

python3 scripts/safety.py -i "DROP TABLE users" \
  -c '{"environment":"production","operation_intent":"destructive","scope":"broad","data_sensitivity":"regulated","rollback":"none","change_control":"ticket:DB-9021"}' \
  -t "postgres://prod/maindb.users" --json
```

## JSON contract

- Success envelope: `success`, `tool`, `mode`, `data`
- Error envelope: `success`, `tool`, `mode`, `error`
- Error types: `validation_error`, `dependency_error`, `network_error`, `api_error`

## Action policy

| `approved` | `risk_level` | Agent action |
|---|---|---|
| `true` | `low` | Proceed. |
| `true` | `medium` | Proceed and mention the risk. |
| `false` | `medium` | Require explicit confirmation before proceeding. |
| `false` | `high` | Block by default and require explicit override. |
| `false` | `critical` | Block and require explicit acknowledgement before any override. |

If the check fails with network/API/dependency issues, do not silently proceed.

This table is caller policy guidance. The CLI itself forwards the request and returns the backend result; it does not locally enforce the action table.

## When not to use

- Pre-install or repository-level inspection that should happen before any execution attempt
- Pure planning, summarization, or clearly read-only analysis with no tool call or state-change path
- Data transformation tasks that need to rewrite or mask content rather than score runtime safety
- Local routing or middleware scenarios where you need to sit in front of upstream model traffic

## Resources

- `scripts/safety.py` — live safety check entry point
- `ARCHITECTURE.md` — command-safety package boundaries
