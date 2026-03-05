---
name: modeio-guardrail
description: >-
  Runs real-time safety analysis for instructions involving destructive operations,
  permission changes, irreversible actions, prompt injection, or compliance-sensitive
  operations. Evaluates risk level, destructiveness, and reversibility via backend API.
  Use when asked for safety check, risk assessment, security audit, destructive check,
  instruction audit, or Modeio safety scan. Also use proactively before executing any
  instruction that deletes data, modifies permissions, drops or truncates tables,
  deploys to production, or alters system state irreversibly. Also supports pre-install
  Skill Safety Assessment for third-party skill repositories via a static prompt contract.
---

# Run safety checks for instructions and skill repos

Gate risky operations behind a real-time safety assessment. Every instruction that could cause data loss, permission escalation, or irreversible state change should be checked before execution.

## Tool routing

1. For executable instructions, use the backend-powered `scripts/safety.py` flow.
2. For requests like "scan this skill repo" or "is this repo dangerous", run the Skill Safety Assessment contract at `prompts/static_repo_scan.md`.
3. Skill Safety Assessment is static analysis only. Never execute code, install dependencies, or run hooks in the target repository.
4. For Skill Safety Assessment, run deterministic script pre-scan first, then pass scan highlights into the prompt contract.

## Instruction safety execution policy

1. Always run `scripts/safety.py` with `--json` for structured output.
2. Run the check **before** executing the instruction, not after.
3. Each instruction must trigger a fresh backend call. Do not reuse cached or historical results.
4. For any state-changing instruction (`delete`, `overwrite`, `permission change`, `deploy`, `schema change`), pass both `--context` and `--target`.
5. Use the Context Contract below exactly. Do not send free-form `--context` values like `"production"` only.
6. If required context or target is missing, treat the instruction as unverified and ask for the missing fields before execution.
7. If an instruction contains multiple operations, check the riskiest one.

## Context contract (required for state-changing instructions)

Pass `--context` as a JSON string with this exact shape:

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

Rules:

1. Include all six keys. If a value is unknown, set it to `unknown` instead of omitting the key.
2. `--target` must be a concrete resource identifier (absolute file path, table name, service name, or URL). Avoid generic targets such as `"database"`.
3. For a file deletion request that should usually be allowed, use: `environment=local-dev|ci`, `operation_intent=cleanup`, `scope=single-resource`, `data_sensitivity=public|internal`, and `rollback=easy`.
4. If those conditions are not met, expect stricter output (`approved=false` or higher `risk_level`) and require explicit user confirmation.

## Action policy

This table applies to `scripts/safety.py` responses.

Use the result to gate execution. Never silently ignore a safety check result.

| `approved` | `risk_level` | Agent action |
|---|---|---|
| `true` | `low` | Proceed. No user prompt needed. |
| `true` | `medium` | Proceed. Mention the risk and recommendation to the user. |
| `false` | `medium` | Warn user with `concerns` and `recommendation`. Proceed only with explicit user confirmation. |
| `false` | `high` | Block execution. Show `concerns` and `recommendation`. Ask user for explicit override. |
| `false` | `critical` | Block execution. Show full assessment. Require user to explicitly acknowledge the risk before proceeding. |

Additional signals:

- `is_destructive: true` combined with `is_reversible: false`: always surface the recommendation to the user, regardless of approval status.
- If the safety check itself fails (network error, API error): warn the user that safety could not be verified. Do not silently proceed with unverified instructions.

## Script commands

### `scripts/safety.py`

- `-i, --input`: required, instruction text to evaluate (whitespace-only rejected)
- `-c, --context`: required for state-changing instructions; JSON string following the Context Contract above
- `-t, --target`: required for state-changing instructions; concrete operation target (file path, table name, service name, URL)
- `--json`: output unified JSON envelope for machine consumption
- Endpoint: `https://safety-cf.modeio.ai/api/cf/safety` (override via `SAFETY_API_URL`)
- Retries: automatic retry on HTTP 502/503/504 and connection/timeout errors (up to 2 retries with exponential backoff)
- Request timeout: 60 seconds per attempt

```bash
python scripts/safety.py -i "Delete /tmp/cache/build-123.log" \
  -c '{"environment":"local-dev","operation_intent":"cleanup","scope":"single-resource","data_sensitivity":"internal","rollback":"easy","change_control":"none"}' \
  -t "/tmp/cache/build-123.log" --json

python scripts/safety.py -i "DROP TABLE users" \
  -c '{"environment":"production","operation_intent":"destructive","scope":"broad","data_sensitivity":"regulated","rollback":"none","change_control":"ticket:DB-9021"}' \
  -t "postgres://prod/maindb.users" --json

python scripts/safety.py -i "chmod 777 /etc/passwd" \
  -c '{"environment":"production","operation_intent":"permission-change","scope":"single-resource","data_sensitivity":"regulated","rollback":"partial","change_control":"ticket:SEC-118"}' \
  -t "/etc/passwd" --json

python scripts/safety.py -i "List all running containers and display their resource usage" --json
```

### `scripts/skill_safety_assessment.py`

- `scan`: deterministic static pre-scan to gather low-noise evidence and highlight IDs
- `prompt`: renders prompt payload with script highlights and structured scan JSON
- `validate`: validates model output against scan evidence IDs (`evidence_refs`) and required highlights

```bash
# 1) Deterministic pre-scan
python scripts/skill_safety_assessment.py scan --target-repo /path/to/repo --json > /tmp/skill_scan.json

# 2) Build prompt payload with highlights
python scripts/skill_safety_assessment.py prompt --target-repo /path/to/repo --scan-file /tmp/skill_scan.json

# 3) Validate model output for evidence linkage
python scripts/skill_safety_assessment.py validate --scan-file /tmp/skill_scan.json --assessment-file /tmp/assessment.md --json
```

## Output contract

### Success response (`--json`)

```json
{
  "success": true,
  "tool": "modeio-guardrail",
  "mode": "api",
  "data": {
    "approved": false,
    "risk_level": "critical",
    "risk_types": ["data loss"],
    "concerns": ["Irreversible destructive operation targeting all user data"],
    "recommendation": "Create a backup before deletion. Use staged rollback plan.",
    "is_destructive": true,
    "is_reversible": false
  }
}
```

Response fields in `data`:

| Field | Type | Values | Meaning |
|---|---|---|---|
| `approved` | `boolean` | `true` / `false` | Whether execution is recommended |
| `risk_level` | `string` | `low` / `medium` / `high` / `critical` | Severity of identified risks |
| `risk_types` | `string[]` | open-ended | Risk categories (e.g., `"data loss"`, `"injection attacks"`, `"unauthorized access"`, `"denial-of-service"`) |
| `concerns` | `string[]` | open-ended | Specific risk points in natural language |
| `recommendation` | `string` | open-ended | Suggested safer alternative or mitigation |
| `is_destructive` | `boolean` | `true` / `false` | Whether the action involves destruction (deletion, overwrite, system modification) |
| `is_reversible` | `boolean` | `true` / `false` | Whether the action can be rolled back |

Any field may be `null` if the backend could not determine it. Treat `null` in `approved` as `false`.

### Failure envelope (`--json`)

```json
{
  "success": false,
  "tool": "modeio-guardrail",
  "mode": "api",
  "error": {
    "type": "network_error",
    "message": "safety request failed: ConnectionError"
  }
}
```

Error types: `validation_error` (empty input), `network_error` (HTTP/connection failure), `api_error` (backend returned error payload).

Exit code is non-zero on any failure.

## Failure policy

Safety verification failures must never be silently ignored.

- **Network/API error**: Tell the user the safety check could not be completed. Present the original instruction and ask whether to proceed without verification.
- **Validation error** (empty input): Fix the input and retry before executing anything.
- **Unexpected response** (null or missing fields): Treat as unverified. Warn the user.
- **Never** assume an instruction is safe because the check failed to run.

## Skill Safety Assessment policy (static prompt contract)

1. Use `prompts/static_repo_scan.md` as the strict contract.
2. Run `scripts/skill_safety_assessment.py scan` first and pass its highlights into prompt input.
3. Every finding must include `path:line` evidence, exact snippet quote, and `evidence_refs` linked to scan evidence IDs.
4. Always include all required highlight evidence IDs from scan output in final findings.
5. Return one of: `ALLOW`, `WARN`, `BLOCK`, or `UNVERIFIED`.
6. If coverage is partial or evidence is insufficient, return `UNVERIFIED` and treat it operationally as `WARN`.
7. Include a prioritized remediation plan so users can fix and re-scan quickly.

## When NOT to use

- For PII redaction or anonymization — use `modeio-redact` instead.
- For tasks with no executable instruction or repository target to evaluate (pure discussion, documentation, questions).
- For operations that are clearly read-only (listing files, reading configs, `git status`).

## Resources

- `modeio_guardrail/cli/safety.py`: modular safety client implementation (importable core)
- `scripts/safety.py`: compatibility wrapper entrypoint for CLI usage
- `modeio_guardrail/cli/skill_safety_assessment.py`: deterministic scan, prompt payload, and output validator for skill-repo safety assessment
- `scripts/skill_safety_assessment.py`: compatibility wrapper entrypoint for assessment scan/prompt/validate commands
- `prompts/static_repo_scan.md`: Skill Safety Assessment prompt contract for pre-install skill-repo risk scanning
- `SAFETY_API_URL`: optional environment override for custom endpoint routing
- `ARCHITECTURE.md`: package boundaries and compatibility notes
