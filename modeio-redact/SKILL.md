---
name: modeio-redact
description: >-
  Runs PII anonymization and local de-anonymization for text/JSON strings and
  supported file-path input (`.txt`, `.md`, `.markdown`, `.csv`, `.tsv`,
  `.json`, `.jsonl`, `.yaml`, `.yml`, `.xml`, `.html`, `.htm`, `.rst`, `.log`).
  Supports local regex masking in lite mode,
  server-side AI analysis in dynamic/strict/crossborder modes, local placeholder
  restore with saved map files, and optional git pre-commit staged-diff scanning
  for PII/secrets. Use when asked to anonymize data, redact PII, mask sensitive
  information, detect personal data, restore anonymized placeholders back to
  originals, check for sensitive content, scrub credentials, or run Modeio
  anonymization. Also use proactively before sending user content to external
  LLMs or third-party APIs.
---

# Run anonymization checks for text, JSON, and supported text-like files

Protect sensitive data by anonymizing PII before it leaves the local environment.
Supports round-trip workflows: anonymize content, use sanitized content externally,
then deanonymize locally when needed.

## Execution policy

1. Default: run `scripts/anonymize.py` with `--json` for structured output.
2. For de-anonymization, run `scripts/deanonymize.py` (local only, no backend call).
3. For offline/no-network anonymization, use `scripts/anonymize.py --level lite` (local regex mode).
4. Optional but recommended: for local LLM proxy shielding (Codex/OpenCode), run `scripts/prompt_gateway.py` and route chat completion calls through `http://127.0.0.1:<port>/v1/chat/completions`.
5. Optional setup helper: run `scripts/setup_prompt_gateway.py` for cross-platform setup guidance and optional OpenCode config patching.
6. Optional git safety guardrail: run `scripts/setup_precommit_scan.py` to install or uninstall a local pre-commit hook that scans staged diffs.
7. Use `scripts/detect_local.py` only when the user explicitly wants detailed local detection output (`items`, `riskScore`, `riskLevel`) or local JSON-first diagnostics.

## Level selection

| Scenario | Level | Reason |
|---|---|---|
| Offline or no network available | `lite` | Local regex only, no API call |
| Quick PII scan, low-sensitivity content | `lite` | Fast and deterministic |
| General-purpose anonymization (default) | `dynamic` | AI-powered handling for varied formats |
| Compliance-sensitive content (GDPR/CCPA) | `strict` | Returns `complianceAnalysis` fields |
| International data transfer | `crossborder` | Requires jurisdiction codes and returns `crossBorderAnalysis` |

When unsure, use `dynamic`. Escalate to `strict` for compliance language and
to `crossborder` when data transfer across regions is involved.

## Action policy

1. When `hasPII: true`, provide anonymized output instead of original content.
2. When `hasPII: false`, report that no PII was detected and content is unchanged.
3. For file workflows, always report `data.outputPath` so the user can find the result.
4. When `data.mapRef` exists, tell the user deanonymization is available via `mapRef.mapId`.
5. Warn on `riskLevel: High` before external sharing.
6. For `strict`/`crossborder`, surface compliance findings (`complianceAnalysis`, `crossBorderAnalysis`).
7. On API failure for `dynamic`/`strict`/`crossborder`, offer fallback to `--level lite`.

## Script commands

### `scripts/anonymize.py`

- `-i, --input`: required, literal content or supported file path
- `--level`: `lite`, `dynamic`, `strict`, `crossborder` (default: `dynamic`)
- `--sender-code`: required for `crossborder` (example: `CN SHA`)
- `--recipient-code`: required for `crossborder` (example: `US NYC`)
- `--json`: output unified JSON envelope
- `--output`: write anonymized content to explicit output file
- `--in-place`: overwrite input file in place (file-path input only)
- Endpoint: `https://safety-cf.modeio.ai/api/cf/anonymize` (override with `ANONYMIZE_API_URL`)
- Retries: 2 retries on 502/503/504 and connection/timeout errors (exponential backoff)
- Timeout: 60 seconds per attempt

Input behavior:

- Existing supported file paths are auto-read as file input.
- Other existing file types are rejected with validation error.
- Non-file strings are treated as literal input.
- `lite` runs local regex anonymization only.
- `dynamic|strict|crossborder` call backend API.

Output behavior:

- Default file output path: `<name>.redacted.<ext>` (auto-increments on collision).
- If map entries exist, script saves a local map and returns `data.mapRef`.
- For `.txt`/`.md`/`.markdown` output, script embeds `modeio-redact-map-id` marker.
- For other supported file types, script preserves syntax and uses sidecar-only map linkage.
- Script also writes sidecar map ref file `<output>.map.json`.
- Default map dir: `~/.modeio/redact/maps` (override with `MODEIO_REDACT_MAP_DIR`).
- Map files auto-prune after 7 days.

```bash
python scripts/anonymize.py --input "Name: Jack, ID number: 110101199001011234" --json

python scripts/anonymize.py --input "Email: alice@example.com" --level dynamic --json

python scripts/anonymize.py --input "Email: alice@example.com, Phone: 415-555-1234" --level lite --json

python scripts/anonymize.py --input "Name: Jack" --level crossborder --sender-code "CN SHA" --recipient-code "US NYC" --json

python scripts/anonymize.py --input ./incident-notes.txt --level lite --json

python scripts/anonymize.py --input ./handoff.md --level dynamic --json

python scripts/anonymize.py --input ./incident-notes.txt --level lite --in-place --json

python scripts/anonymize.py --input "Email: alice@example.com" --output ./redacted-output.txt --json
```

### `scripts/deanonymize.py`

- `-i, --input`: required, anonymized text or supported file path
- `--map`: optional map ID or map file path
- `--allow-hash-mismatch`: continue when input hash mismatches map hash
- `--output`: write restored content to explicit output file
- `--in-place`: overwrite input file in place (file-path input only)
- `--json`: output unified JSON envelope
- No network call is made.

Map resolution order when `--map` is omitted:

1. Embedded map marker in file input
2. Sidecar map file `<input>.map.json`
3. Latest local map (literal text input only)

Default file output path: `<name>.restored.<ext>`.

```bash
python scripts/deanonymize.py --input "Email: [EMAIL_1]" --json

python scripts/deanonymize.py --input "Email: [EMAIL_1]" --map 20260304T050000Z-a1b2c3d4 --json

python scripts/deanonymize.py --input ./anonymized_notes.redacted.txt --json

python scripts/deanonymize.py --input ./anonymized_notes.redacted.txt --in-place --json
```

### Prompt shield gateway: `scripts/prompt_gateway.py`

Use this when Codex CLI or OpenCode should send LLM requests through a local shield/unshield proxy.
This mode is optional (manual anonymize/deanonymize still works), but recommended for automatic request-level protection.

Quickstart: `PROMPT_GATEWAY_QUICKSTART.md`.

- Endpoint contract:
  - `GET /healthz`
  - `POST /v1/chat/completions` (OpenAI-compatible payload, `stream=false` only)
- Request extension:
  - Optional `modeio` object in request body:
    - `policy`: must be `strict` in v1
    - `allow_degraded_unshield`: boolean, default `true`
- Shield behavior:
  - Detects and replaces sensitive spans in text message content before upstream forwarding
  - Uses signed placeholders (`__MIO_*__`) and local map persistence for request linkage
- Unshield behavior:
  - Restores signed placeholders in upstream response message text before returning to client
  - If response shape is not restorable and `allow_degraded_unshield=true`, returns degraded safe output with header `x-modeio-degraded: unshield_failed`

Key headers returned on responses:

- `x-modeio-contract-version`
- `x-modeio-request-id`
- `x-modeio-shielded`
- `x-modeio-redaction-count`
- `x-modeio-degraded`
- `x-modeio-upstream-called`

```bash
# Optional one-time setup helper
python scripts/setup_prompt_gateway.py --client both

# Start local gateway (OpenAI-compatible upstream by default)
python scripts/prompt_gateway.py \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-url "https://api.openai.com/v1/chat/completions"

# Set upstream key used when incoming requests do not provide Authorization
export MODEIO_GATEWAY_UPSTREAM_API_KEY="<your-upstream-key>"

# Health check
curl -s http://127.0.0.1:8787/healthz

# Example proxied call
curl -s http://127.0.0.1:8787/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model":"gpt-4o-mini",
    "messages":[{"role":"user","content":"Email alice@example.com about invoice 42."}],
    "modeio":{"policy":"strict","allow_degraded_unshield":true}
  }'

# Dedicated prompt-gateway tests only
python -m unittest discover tests -p "test_prompt_gateway*.py"

# Setup helper tests
python -m unittest tests.test_setup_prompt_gateway
```

### Setup helper: `scripts/setup_prompt_gateway.py`

Use this optional script to reduce onboarding friction across macOS/Linux/Windows.

- Prints OS-aware Codex `OPENAI_BASE_URL` command.
- Can apply OpenCode `provider.openai.options.baseURL` update (with backup).
- Optionally checks local gateway health endpoint.
- Supports human-readable and `--json` machine-readable reports.

```bash
# Guidance only (no file edits)
python scripts/setup_prompt_gateway.py --client both

# Shortcut
make prompt-gateway-setup

# Apply OpenCode baseURL patch with backup and create config if missing
python scripts/setup_prompt_gateway.py \
  --client opencode \
  --apply-opencode \
  --create-opencode-config

# JSON output for automation
python scripts/setup_prompt_gateway.py --client both --json

# One-command uninstall (OpenCode rollback + gateway-local map cleanup)
python scripts/setup_prompt_gateway.py \
  --client both \
  --uninstall \
  --apply-opencode \
  --cleanup-maps

# Shortcut
make prompt-gateway-uninstall
```

### Optional git pre-commit scan: `scripts/precommit_scan.py` + `scripts/setup_precommit_scan.py`

Use this when users want a local git commit blocker for staged PII/secret diffs.
This flow is optional and user-controlled; it is not enabled automatically.

- `scripts/precommit_scan.py` reads staged additions from `git diff --cached` and runs local detection.
- Exit code `1` means findings detected (commit blocked in hook mode).
- Exit code `2` means runtime/validation error.
- `scripts/setup_precommit_scan.py` installs or uninstalls the managed pre-commit block.
- If an existing unmanaged hook exists, setup fails by default; use `--append` or `--overwrite` explicitly.

```bash
# Install optional pre-commit scan hook (default: profile=balanced, minimum risk=medium)
python scripts/setup_precommit_scan.py

# Shortcut
make precommit-scan-setup

# Keep existing custom hook and append modeio scan block
python scripts/setup_precommit_scan.py --append

# Tune scanner sensitivity in hook
python scripts/setup_precommit_scan.py --minimum-risk-level low --profile strict

# Uninstall modeio-managed hook block
python scripts/setup_precommit_scan.py --uninstall

# Shortcut
make precommit-scan-uninstall

# Run one-off staged scan without installing hook
python scripts/precommit_scan.py --verbose

# JSON output for automation
python scripts/precommit_scan.py --json
```

Notes:

- Hook scanning is local only and uses `scripts/detect_local.py` logic.
- Hook can still be bypassed with `git commit --no-verify`; use CI checks for non-bypassable enforcement.

### `scripts/detect_local.py`

Use this only when user explicitly asks for local/offline detection details.

- `-i, --input`: required input content
- `--profile`: threshold profile (`strict`, `balanced`, `precision`; default `balanced`)
- `--allowlist-file`: optional JSON allowlist rules
- `--blocklist-file`: optional JSON blocklist rules
- `--thresholds-file`: optional JSON per-type threshold overrides
- `--explain`: print heuristic scoring diagnostics in non-JSON mode
- `--json`: output full JSON diagnostics
- No network call is made.

Supported type families include `phone`, `email`, `idCard`, `creditCard`,
`bankCard`, `address`, `name`, `password`, `apiKey`, `ipAddress`, `ssn`,
`passport`, and `dateOfBirth`.

```bash
python scripts/detect_local.py --input "Phone 13812345678 Email test@example.com" --json

python scripts/detect_local.py --input "Name: Alice Wang, phone 415-555-1234" --json

python scripts/detect_local.py --input "Name: Alice Wang" --profile precision --json

python scripts/detect_local.py --input "Project codename Phoenix" --blocklist-file ./blocklist.json --json
```

## Output contracts

### Anonymize success (`--json`)

```json
{
  "success": true,
  "tool": "modeio-redact",
  "mode": "api",
  "level": "dynamic",
  "data": {
    "anonymizedContent": "Name: [REDACTED_NAME_1], ID: [REDACTED_ID_1]",
    "hasPII": true,
    "action": "ANONYMIZED",
    "riskLevel": "High",
    "description": "PII detected and anonymized",
    "mapping": [
      { "original": "Jack", "anonymized": "[REDACTED_NAME_1]", "type": "name" }
    ],
    "privacyScore": { "before": 25, "after": 85 },
    "mapRef": {
      "mapId": "20260304T050000Z-a1b2c3d4",
      "mapPath": "~/.modeio/redact/maps/20260304T050000Z-a1b2c3d4.json",
      "entryCount": 1
    }
  }
}
```

Core `data` fields:

| Field | Type | Meaning |
|---|---|---|
| `anonymizedContent` | `string` | Content with placeholders |
| `hasPII` | `boolean` | Whether sensitive data was detected |
| `action` | `string` | Backend action (`ANONYMIZED`/`PASSTHROUGH`/`NONE`) |
| `riskLevel` | `string` | `High`/`Medium`/`Low`/`None` |
| `mapping` | `array` | Mapping entries `{original, anonymized, type}` |
| `privacyScore` | `object` | Score object `{before, after}` |
| `mapRef` | `object` | Local map reference `{mapId, mapPath, entryCount}` |
| `outputPath` | `string` | Output file path for file workflows |
| `inputType` | `string` | `text` or `file` |
| `inputPath` | `string` | Source path for file workflows |
| `warnings` | `array` | Warning list (for example `map_persist_failed`) |

Additional API-level fields:

| Field | Level | Meaning |
|---|---|---|
| `complianceAnalysis` | `strict`, `crossborder` | Compliance score and violated articles |
| `crossBorderAnalysis` | `crossborder` | Cross-border transfer analysis |
| `intention` | API levels | AI-inferred intent summary |
| `residualRiskReason` | API levels | Reason privacy score is not maximal |

For `lite`, `mode` is `local-regex` and `data.localDetection` contains the full local detector payload.

### Deanonymize success (`--json`)

```json
{
  "success": true,
  "tool": "modeio-redact",
  "mode": "local-map",
  "data": {
    "deanonymizedContent": "Email: alice@example.com",
    "replacementSummary": {
      "totalReplacements": 1,
      "replacementsByType": { "email": 1 }
    },
    "mapRef": {
      "mapId": "20260304T050000Z-a1b2c3d4",
      "mapPath": "~/.modeio/redact/maps/20260304T050000Z-a1b2c3d4.json",
      "entryCount": 1
    },
    "linkageSource": "explicit-map",
    "warnings": []
  }
}
```

`linkageSource` values:

- `explicit-map`: map ref provided via `--map`
- `embedded-mapid`: map ID found in embedded marker
- `sidecar`: map ref read from sidecar file
- `latest-fallback`: most recent local map fallback

For file workflows, `data.outputPath` is included.

### Detect local output (`--json`)

Default mode prints sanitized text to stdout and summary lines to stderr.
`--json` prints full structured output.

Notable JSON fields:

- `sanitizedText`: masked text
- `items`: detected entities
- `items[].detectionScore`: heuristic score in `[0,1]`
- `items[].scoreThreshold`: active threshold for that type
- `items[].scoreReasons`: additive score reasons
- `items[].validator`: validator status for format/checksum-guarded types
- `items[].detectionSource`: `regex` / `name-context` / `blocklist`
- `riskScore`: 0-100
- `riskLevel`: `low` / `medium` / `high`
- `profile`: active profile
- `thresholds`: effective per-type thresholds
- `scoringMethod`: scoring algorithm ID (`heuristic-v1`)
- `detectorVersion`: detector version (`local-rules-v1`)
- Deprecated aliases (temporary): `confidence`, `confidenceThreshold`, `confidenceReasons`

```json
{
  "originalText": "Phone 13812345678 Email test@example.com",
  "sanitizedText": "Phone [PHONE_1] Email [EMAIL_1]",
  "items": [
    {
      "id": "1",
      "type": "phone",
      "label": "Phone Number",
      "value": "13812345678",
      "maskedValue": "[PHONE_1]",
      "riskLevel": "medium",
      "startIndex": 6,
      "endIndex": 17,
      "detectionScore": 0.92,
      "scoreThreshold": 0.70,
      "detectionSource": "regex"
    }
  ],
  "riskScore": 46,
  "riskLevel": "medium",
  "profile": "balanced",
  "scoringMethod": "heuristic-v1",
  "detectorVersion": "local-rules-v1"
}
```

Risk thresholds: `high >= 60`, `medium >= 30`, `low < 30`.

### Failure envelope (`--json`)

```json
{
  "success": false,
  "tool": "modeio-redact",
  "mode": "api",
  "level": "dynamic",
  "error": {
    "type": "network_error",
    "message": "anonymization request failed: ConnectionError"
  }
}
```

Error types by script:

| Script | Error types |
|---|---|
| `anonymize.py` | `validation_error`, `network_error`, `api_error`, `io_error` |
| `deanonymize.py` | `validation_error`, `map_error`, `runtime_error`, `io_error` |

Exit code conventions:

- `2`: validation errors
- `1`: network/API/map/runtime/IO errors

## Failure policy

- On API/network errors for non-lite levels, offer retry with `--level lite`.
- On `map_error`, verify map ID/path and local map TTL window.
- On `io_error`, verify output directory exists and is writable.
- On hash mismatch, ask user before applying `--allow-hash-mismatch`.
- Never claim anonymization succeeded when command exits non-zero.

---

## Jurisdiction codes for `crossborder`

`--sender-code` and `--recipient-code` use format `<COUNTRY_ISO2> <CITY_CODE>`.

| Code | Jurisdiction |
|------|-------------|
| `CN SHA` | China - Shanghai |
| `CN BJS` | China - Beijing |
| `CN GZH` | China - Guangzhou |
| `CN SZX` | China - Shenzhen |
| `US NYC` | United States - New York |
| `US SFO` | United States - San Francisco |
| `US LAX` | United States - Los Angeles |
| `US CHI` | United States - Chicago |
| `GB LON` | United Kingdom - London |
| `DE BER` | Germany - Berlin |
| `DE FRA` | Germany - Frankfurt |
| `FR PAR` | France - Paris |
| `JP TYO` | Japan - Tokyo |
| `SG SIN` | Singapore |
| `AU SYD` | Australia - Sydney |
| `CA TOR` | Canada - Toronto |
| `KR SEL` | South Korea - Seoul |
| `IN BOM` | India - Mumbai |
| `BR SAO` | Brazil - Sao Paulo |
| `AE DXB` | UAE - Dubai |

Country code is ISO 3166-1 alpha-2. City code is IATA. Any valid `<ISO2> <IATA>`
pair is accepted by backend API.

---

## When NOT to use

- For command safety/destructive-operation analysis; use `modeio-guardrail`.
- For pure policy/legal discussion with no text to anonymize.
- For content already anonymized with no original values to protect.

## Resources

- `scripts/anonymize.py`: default script (`lite` local regex; other levels call `https://safety-cf.modeio.ai/api/cf/anonymize`)
- `scripts/deanonymize.py`: local-only placeholder restore using saved map files
- `scripts/prompt_gateway.py`: local OpenAI-compatible shield/unshield gateway for Codex/OpenCode routing
- `scripts/setup_prompt_gateway.py`: optional cross-platform setup and uninstall helper
- `scripts/precommit_scan.py`: staged-diff scanner for optional git pre-commit blocking
- `scripts/setup_precommit_scan.py`: optional pre-commit install/uninstall helper (append/overwrite aware)
- `scripts/map_store.py`: local map persistence and resolution utilities
- `scripts/detect_local.py`: offline local detection with scoring profiles
- `ANONYMIZE_API_URL`: optional anonymize endpoint override
- `MODEIO_REDACT_MAP_DIR`: optional local map directory override
- Supported file paths are auto-detected through `--input`.
