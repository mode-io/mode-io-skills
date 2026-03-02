---
name: modeio-safety
description: Runs safety checks for instruction risk including destructive operations, prompt injection, irreversible actions, and compliance violations. Performs one real-time backend check per instruction. Use when asked for safety check, risk assessment, security audit, destructive check, instruction audit, or Modeio safety scan.
---

# Run safety checks for instructions

## Execution policy

1. Always run `scripts/safety.py` for safety checks.
2. Each instruction must trigger a fresh backend call.
3. Do not use cached or historical results as final judgment.

## Script commands

### Primary mode: `scripts/safety.py`

- `-i, --input`: required, instruction text to evaluate
- `-c, --context`: optional, execution context
- `-t, --target`: optional, operation target such as file path, table name, or service name
- Script calls the Cloudflare safety endpoint internally: `https://safety-cf.modeio.ai/api/cf/safety`.
- Override endpoint via `SAFETY_API_URL` environment variable.

```bash
python scripts/safety.py -i "Delete all log files"

python scripts/safety.py -i "Modify database permissions" -c "production" -t "/var/lib/mysql"

python scripts/safety.py -i "$(cat instruction.txt)"
```

### Output

- Successful checks return JSON on `stdout` and print `Status: success` to `stderr`.
- `approved`: whether execution is recommended
- `risk_level`: `low` / `medium` / `high` / `critical`
- `risk_types`: categories of identified risk
- `concerns`: detailed risk points
- `recommendation`: suggested safer action
- `is_destructive`: whether action is destructive
- `is_reversible`: whether action is reversible

```json
{
  "approved": false,
  "risk_level": "critical",
  "risk_types": ["data loss"],
  "concerns": ["Irreversible destructive operation"],
  "recommendation": "Use backup and staged rollback first",
  "is_destructive": true,
  "is_reversible": false
}
```

Failure behavior:

- HTTP/network failure: script exits non-zero and prints URL/status/exception details to `stderr`.
- API payload with top-level `error`: script exits non-zero and prints the full response JSON to `stderr`.

---

## When NOT to use

- For PII redaction or anonymization; use `modeio-anonymization` instead.
- For tasks with no executable instruction to evaluate.

## Resources

- `scripts/safety.py`: runs real-time safety checks via `https://safety-cf.modeio.ai/api/cf/safety`
- `SAFETY_API_URL`: optional environment override for custom endpoint routing.
