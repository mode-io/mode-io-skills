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

Use this skill to gate risky operations behind a real-time safety assessment, or to scan third-party skill repos before installation.

## Tool routing

1. For executable instructions, use the backend-powered `scripts/safety.py` flow.
2. For requests like "scan this skill repo" or "is this repo dangerous", run the Skill Safety Assessment contract at `prompts/static_repo_scan.md`.
3. Skill Safety Assessment is static analysis only. Never execute code, install dependencies, or run hooks in the target repository.
4. For Skill Safety Assessment, run deterministic script evaluation first (`evaluate`), then pass highlights into the prompt contract.

## Dependencies

- `requests` is required for `scripts/safety.py` because it makes backend API calls.
- `scripts/skill_safety_assessment.py` does not require `requests` for basic local repository evaluation.
- For repo-local setup from the repo root:

```bash
python scripts/bootstrap_env.py
python scripts/doctor_env.py
```

## Instruction safety execution policy

1. Always run `scripts/safety.py` with `--json` for structured output.
2. Run the check **before** executing the instruction, not after.
3. Each instruction must trigger a fresh backend call. Do not reuse cached or historical results.
4. For any state-changing instruction (`delete`, `overwrite`, `permission change`, `deploy`, `schema change`), always pass both `--context` and `--target`.
5. `scripts/safety.py` accepts `--context` and `--target` as optional flags, so this requirement is enforced by policy, not by automatic CLI blocking.
6. Use the Context Contract below exactly. Do not send free-form `--context` values like `"production"` only.
7. If policy-required context or target is missing, treat the instruction as unverified and ask for the missing fields before execution.
8. If an instruction contains multiple operations, check the riskiest one.

## Context contract (policy-required for state-changing instructions)

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

## Scripts

### `scripts/safety.py`

- `-i, --input`: required, instruction text to evaluate (whitespace-only rejected)
- `-c, --context`: policy-required for state-changing instructions (CLI accepts it as optional); JSON string following the Context Contract above
- `-t, --target`: policy-required for state-changing instructions (CLI accepts it as optional); concrete operation target (file path, table name, service name, URL)
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

- `evaluate`: authoritative v2 layered evaluator with deterministic evidence IDs, integrity fingerprinting, and risk scoring
  - Native first-layer gate: GitHub metadata/README/issue-search precheck runs by default and hard-rejects on high-risk attack-demo/malware signals before local file scan.
- `scan`: compatibility alias to `evaluate` for existing automation
- `prompt`: renders prompt payload with script highlights and structured scan JSON
- `validate`: validates model output against scan evidence IDs (`evidence_refs`), required highlights, and score/decision consistency checks
- `adjudicate`: context-aware LLM adjudication bridge (prompt generation + merge decisions back into deterministic score/decision)

Context profile (optional, no user identity required):

```json
{
  "environment": "local-dev|ci|staging|production|unknown",
  "execution_mode": "read-only|build-test|install|deploy|mutating|unknown",
  "risk_tolerance": "strict|balanced|permissive",
  "data_sensitivity": "public|internal|sensitive|regulated|unknown"
}
```

```bash
# 1) Deterministic layered evaluation (v2)
python scripts/skill_safety_assessment.py evaluate --target-repo /path/to/repo --json > /tmp/skill_scan.json
python scripts/skill_safety_assessment.py evaluate --target-repo /path/to/repo --context-profile '{"environment":"ci","execution_mode":"build-test","risk_tolerance":"balanced","data_sensitivity":"internal"}' --json > /tmp/skill_scan.json
python scripts/skill_safety_assessment.py evaluate --target-repo /path/to/repo --github-osint-timeout 8 --json > /tmp/skill_scan.json
python scripts/skill_safety_assessment.py evaluate --target-repo /path/to/repo --context-profile-file ./context_profile.json --output /tmp/skill_scan.json --json

# (compat) legacy alias still supported
python scripts/skill_safety_assessment.py scan --target-repo /path/to/repo --json > /tmp/skill_scan.json

# 2) Build prompt payload with highlights + full findings (recommended for strict evidence_refs linking)
python scripts/skill_safety_assessment.py prompt --target-repo /path/to/repo --scan-file /tmp/skill_scan.json --include-full-findings

# 3) Validate model output for evidence linkage + integrity
python scripts/skill_safety_assessment.py validate --scan-file /tmp/skill_scan.json --assessment-file /tmp/assessment.md --json
# --rescan-on-validate requires --target-repo
python scripts/skill_safety_assessment.py validate --scan-file /tmp/skill_scan.json --assessment-file /tmp/assessment.md --target-repo /path/to/repo --rescan-on-validate --json

# 4) Optional adjudication bridge (LLM interprets context, engine keeps deterministic control)
python scripts/skill_safety_assessment.py adjudicate --scan-file /tmp/skill_scan.json
python scripts/skill_safety_assessment.py adjudicate --scan-file /tmp/skill_scan.json --assessment-file /tmp/adjudication.json --json
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

Error types: `validation_error` (empty input), `dependency_error` (missing local package such as `requests`), `network_error` (HTTP/connection failure), `api_error` (backend returned error payload).

Exit code is non-zero on any failure.

## Failure policy

Safety verification failures must never be silently ignored.

- **Network/API error**: Tell the user the safety check could not be completed. Present the original instruction and ask whether to proceed without verification.
- **Validation error** (empty input): Fix the input and retry before executing anything.
- **Unexpected response** (null or missing fields): Treat as unverified. Warn the user.
- **Never** assume an instruction is safe because the check failed to run.

## Skill Safety Assessment policy (static prompt contract)

1. Use `prompts/static_repo_scan.md` as the strict contract.
2. Run `scripts/skill_safety_assessment.py evaluate` first (or `scan` compatibility alias) and pass its highlights into prompt input.
3. When model output must include strict `evidence_refs`, render prompt input with `--include-full-findings` so scan evidence IDs and snippets are available in `SCRIPT_SCAN_JSON`.
4. Every finding must include `path:line` evidence, exact snippet quote, and `evidence_refs` linked to scan evidence IDs.
5. Always include all required highlight evidence IDs from scan output in final findings.
6. Keep decision/score consistent with referenced evidence severity and coverage constraints.
7. Use `adjudicate` when context interpretation is required (docs/examples/tests vs runtime/install paths).
8. Return one of: `reject`, `caution`, or `approve`.
9. If coverage is partial or evidence is insufficient, return `caution` with explicit coverage note.
10. Include a prioritized remediation plan so users can fix and re-scan quickly.

## When not to use

- For PII redaction or anonymization — use `modeio-redact` instead.
- For tasks with no executable instruction or repository target to evaluate (pure discussion, documentation, questions).
- For operations that are clearly read-only (listing files, reading configs, `git status`).

## Resources

- `scripts/safety.py` — CLI entry point for instruction safety checks
- `scripts/skill_safety_assessment.py` — CLI entry point for skill repo assessment (evaluate/scan/prompt/validate/adjudicate)
- `prompts/static_repo_scan.md` — Skill Safety Assessment prompt contract
- `ARCHITECTURE.md` — package boundaries and compatibility notes
- `SAFETY_API_URL` env var — optional endpoint override (default: `https://safety-cf.modeio.ai/api/cf/safety`)
