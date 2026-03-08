---
name: modeio-guardrail
description: >-
  Runs real-time safety analysis for instructions involving destructive
  operations, permission changes, irreversible actions, prompt injection, or
  compliance-sensitive operations. Use when asked for a safety check, risk
  assessment, destructive check, instruction audit, or execution-time security
  review before mutating state.
---

# Run live instruction safety checks

Use this skill to gate risky operations behind a backend-backed safety decision before you execute them.

This skill is for live instruction and operation safety only. For pre-install repository auditing, use `modeio-skill-audit`.

## Tool routing

1. Use `scripts/safety.py` for instruction and operation safety checks.
2. Always run the check before execution.
3. For state-changing work, provide both `--context` and `--target`.
4. If the safety check cannot be completed, treat the operation as unverified.

## Dependencies

- `requests` is required for `scripts/safety.py`.
- For repo-local setup from the repo root:

```bash
python scripts/bootstrap_env.py
python scripts/doctor_env.py
```

## Context contract

Pass `--context` as JSON with these keys:

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

`--target` must be a concrete resource identifier such as an absolute path, table name, service name, or URL.

## Script

### `scripts/safety.py`

```bash
python scripts/safety.py -i "Delete /tmp/cache/build-123.log" \
  -c '{"environment":"local-dev","operation_intent":"cleanup","scope":"single-resource","data_sensitivity":"internal","rollback":"easy","change_control":"none"}' \
  -t "/tmp/cache/build-123.log" --json

python scripts/safety.py -i "DROP TABLE users" \
  -c '{"environment":"production","operation_intent":"destructive","scope":"broad","data_sensitivity":"regulated","rollback":"none","change_control":"ticket:DB-9021"}' \
  -t "postgres://prod/maindb.users" --json
```

## Action policy

| `approved` | `risk_level` | Agent action |
|---|---|---|
| `true` | `low` | Proceed. |
| `true` | `medium` | Proceed and mention the risk. |
| `false` | `medium` | Require explicit confirmation before proceeding. |
| `false` | `high` | Block by default and require explicit override. |
| `false` | `critical` | Block and require explicit acknowledgement before any override. |

If the check fails with network/API/dependency issues, do not silently proceed.

## When not to use

- Pre-install or repository-level inspection that should happen before any execution attempt
- Data transformation tasks that need to rewrite or mask content rather than score runtime safety
- Local routing or middleware scenarios where you need to sit in front of upstream model traffic

## Resources

- `scripts/safety.py` — live safety check entry point
- `ARCHITECTURE.md` — command-safety package boundaries
