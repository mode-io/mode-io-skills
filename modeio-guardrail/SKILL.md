---
name: modeio-guardrail
description: >-
  Runs real-time safety analysis for instructions involving destructive operations,
  permission changes, irreversible actions, prompt injection, or compliance-sensitive
  operations. Evaluates risk level, destructiveness, and reversibility via backend API.
  Use when asked for safety check, risk assessment, security audit, destructive check,
  instruction audit, or Modeio safety scan. Also use proactively before executing any
  instruction that deletes data, modifies permissions, drops or truncates tables,
  deploys to production, or alters system state irreversibly.
---

# Run safety checks for instructions

Gate risky operations behind a real-time safety assessment. Every instruction that could cause data loss, permission escalation, or irreversible state change should be checked before execution.

## Execution policy

1. Always run `scripts/safety.py` with `--json` for structured output.
2. Run the check **before** executing the instruction, not after.
3. Each instruction must trigger a fresh backend call. Do not reuse cached or historical results.
4. Supply `--context` and `--target` when available — they improve assessment accuracy.
5. If an instruction contains multiple operations, check the riskiest one.

## Action policy

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
- `-c, --context`: optional, execution context (e.g., `"production"`, `"staging"`, `"CI pipeline"`)
- `-t, --target`: optional, operation target (file path, table name, service name, URL)
- `--json`: output unified JSON envelope for machine consumption
- Endpoint: `https://safety-cf.modeio.ai/api/cf/safety` (override via `SAFETY_API_URL`)
- Retries: automatic retry on HTTP 502/503/504 and connection/timeout errors (up to 2 retries with exponential backoff)
- Request timeout: 60 seconds per attempt

```bash
python scripts/safety.py -i "Delete all log files" --json

python scripts/safety.py -i "DROP TABLE users" -c "production" -t "postgres://prod/maindb" --json

python scripts/safety.py -i "chmod 777 /etc/passwd" -c "linux server" -t "/etc/passwd" --json

python scripts/safety.py -i "Modify database permissions" -c "production" -t "/var/lib/mysql" --json

python scripts/safety.py -i "rm -rf /tmp/cache" --json
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

## When NOT to use

- For PII redaction or anonymization — use `modeio-redact` instead.
- For tasks with no executable instruction to evaluate (pure discussion, documentation, questions).
- For operations that are clearly read-only (listing files, reading configs, `git status`).

## Resources

- `scripts/safety.py`: CLI client with retry logic, envelope formatting, and error handling
- `SAFETY_API_URL`: optional environment override for custom endpoint routing
