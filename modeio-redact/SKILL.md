---
name: modeio-redact
description: >-
  Runs PII anonymization and local de-anonymization for text, JSON strings, and
  `.txt`/`.md` file-path input. Supports local regex masking in lite mode,
  server-side AI analysis in dynamic/strict/crossborder modes, and local placeholder
  restore with saved map files. Use when asked to anonymize data, redact PII, mask
  sensitive information, detect personal data, restore anonymized placeholders back
  to originals, check for sensitive content, scrub credentials, or run Modeio
  anonymization. Also use proactively before sending user content to external LLMs
  or third-party APIs.
---

# Run anonymization checks for text, JSON, and `.txt`/`.md` files

Protect sensitive data by anonymizing PII before it leaves the local environment. Supports round-trip workflows: anonymize, use the sanitized content, then deanonymize to restore originals.

## Execution policy

1. Default: run `scripts/anonymize.py` with `--json` for structured output.
2. For de-anonymization, run `scripts/deanonymize.py` (local only, no backend call).
3. For offline/no-network anonymization, use `scripts/anonymize.py --level lite` (local regex mode).
4. Use `scripts/detect_local.py` only when the user explicitly wants detailed local detection output (`items`, `riskScore`, `riskLevel`) or local JSON-first diagnostics.

## Level selection

| Scenario | Level | Reason |
|---|---|---|
| Offline or no network available | `lite` | Local regex only, no API call |
| Quick PII scan, low-sensitivity content | `lite` | Fast, no backend dependency |
| General-purpose anonymization (default) | `dynamic` | AI-powered, handles context and edge cases |
| Compliance-sensitive content (GDPR, CCPA) | `strict` | Returns `complianceAnalysis` with violation scores and articles |
| International data transfer | `crossborder` | Requires jurisdiction codes, returns `crossBorderAnalysis` |

When unsure, use `dynamic` (the default). Escalate to `strict` if the user mentions compliance or regulation. Escalate to `crossborder` if the user mentions sending data across borders.

## Action policy

1. When `hasPII: true`: present the anonymized content. Mention the map reference if saved — it enables deanonymization later.
2. When `hasPII: false`: inform the user no PII was detected. The content is unchanged.
3. For file workflows: report the output path (`data.outputPath`) to the user.
4. When `data.mapRef` is present: mention that deanonymization is available using `scripts/deanonymize.py` with the returned `mapRef.mapId`. Maps expire after 7 days.
5. When `riskLevel` is `High`: warn the user about high PII density and suggest reviewing the anonymized output before use.
6. For `strict`/`crossborder` results: surface `complianceAnalysis` or `crossBorderAnalysis` findings to the user.
7. On API failure for `dynamic`/`strict`/`crossborder`: offer to retry with `--level lite` as a local fallback.

## Script commands

### `scripts/anonymize.py`

- `-i, --input`: required, content to anonymize (literal text or `.txt`/`.md` file path)
- `--level`: anonymization level (`lite`, `dynamic`, `strict`, `crossborder`; default: `dynamic`)
- `--sender-code`: sender jurisdiction code, required for `crossborder` level (example: `CN SHA`)
- `--recipient-code`: recipient jurisdiction code, required for `crossborder` level (example: `US NYC`)
- `--json`: output unified JSON envelope for machine consumption
- `--output`: write anonymized content to an explicit output file path
- `--in-place`: overwrite input file in place (file-path input only; mutually exclusive with `--output`)
- Endpoint: `https://safety-cf.modeio.ai/api/cf/anonymize` (override via `ANONYMIZE_API_URL`)
- Retries: automatic retry on HTTP 502/503/504 and connection/timeout errors (up to 2 retries with exponential backoff)
- Request timeout: 60 seconds per attempt

Input handling:

- Existing `.txt` and `.md` file paths are auto-detected and read as file input.
- Other existing file types are rejected with a validation error.
- Non-file strings are treated as literal content.
- `--level lite` runs local regex anonymization (no network call).
- `--level dynamic|strict|crossborder` calls the backend API.

Output handling:

- For file-path input, anonymized output writes to `<name>.redacted.<ext>` by default (auto-increments on collision).
- For file output, map linkage is written in both places:
  - embedded map marker (`modeio-redact-map-id`) in `.txt`/`.md` output
  - sidecar file `<output>.map.json`
- Default local map directory: `~/.modeio/redact/maps` (override via `MODEIO_REDACT_MAP_DIR`).

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

- `-i, --input`: required, anonymized content containing placeholders, or an existing `.txt`/`.md` file path
- `--map`: optional map ID or map file path
- `--allow-hash-mismatch`: allow restore to continue when map hash does not match input
- `--output`: write restored content to an explicit output file path
- `--in-place`: overwrite input file in place (file-path input only)
- `--json`: output unified JSON envelope for machine consumption
- No network call is made. Entirely local.

Map resolution order when `--map` is omitted:

1. embedded map marker in file input
2. sidecar map file `<input>.map.json`
3. latest local map (only for literal text input)

For file-path input, restored output writes to `<name>.restored.<ext>` by default.

```bash
python scripts/deanonymize.py --input "Email: [EMAIL_1]" --json

python scripts/deanonymize.py --input "Email: [EMAIL_1]" --map 20260304T050000Z-a1b2c3d4 --json

python scripts/deanonymize.py --input ./anonymized_notes.redacted.txt --json

python scripts/deanonymize.py --input ./anonymized_notes.redacted.txt --in-place --json
```

### `scripts/detect_local.py`

Use only when user explicitly asks for offline or local detection with full diagnostics.

- `-i, --input`: content to scan (minimum 5 characters)
- `--json`: output full detection details
- No network call is made.

Detected PII types: phone, email, idCard, creditCard, bankCard, address, name, password, apiKey, ipAddress, ssn, passport, dateOfBirth.

```bash
python scripts/detect_local.py --input "Phone 13812345678 Email test@example.com" --json

python scripts/detect_local.py --input "Name: Alice Wang, phone 415-555-1234" --json
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
      { "original": "Jack", "anonymized": "[REDACTED_NAME_1]", "type": "name" },
      { "original": "110101199001011234", "anonymized": "[REDACTED_ID_1]", "type": "idCard" }
    ],
    "privacyScore": { "before": 25, "after": 85 },
    "mapRef": {
      "mapId": "20260304T050000Z-a1b2c3d4",
      "mapPath": "~/.modeio/redact/maps/20260304T050000Z-a1b2c3d4.json",
      "entryCount": 2
    }
  }
}
```

Key `data` fields:

| Field | Type | Values | Meaning |
|---|---|---|---|
| `anonymizedContent` | `string` | — | Anonymized content with placeholders |
| `hasPII` | `boolean` | `true` / `false` | Whether sensitive data was detected |
| `action` | `string` | `ANONYMIZED` / `PASSTHROUGH` / `NONE` | What the backend did |
| `riskLevel` | `string` | `High` / `Medium` / `Low` / `None` | PII density and sensitivity |
| `mapping` | `array` | `{original, anonymized, type}` | Placeholder-to-original mappings |
| `privacyScore` | `object` | `{before, after}` (0–100) | Privacy score before and after anonymization |
| `mapRef` | `object` | `{mapId, mapPath, entryCount}` | Local map reference for deanonymization |

Additional fields for `strict`/`crossborder` levels:

| Field | Level | Meaning |
|---|---|---|
| `complianceAnalysis` | `strict`, `crossborder` | `{overall_score, violated_articles}` — regulatory compliance scoring |
| `crossBorderAnalysis` | `crossborder` | Prose analysis of cross-border data transfer risks |
| `intention` | all API levels | AI-inferred intent of the content |
| `residualRiskReason` | all API levels | Why the after-score may be below 100 |

For `lite` mode, `mode` is `"local-regex"` and `data` includes `localDetection` with the full local detection result.

For file workflows, `data` also includes `outputPath`, `inputType`, `inputPath`, and `mapRef.sidecarPath`.

Any field may be `null` if the backend could not determine it.

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
    "linkageSource": "explicit-map"
  }
}
```

`linkageSource` values: `explicit-map` (user-provided), `embedded-mapid` (from file marker), `sidecar` (from `.map.json`), `latest-fallback` (most recent map — less reliable).

For file workflows, `data` also includes `outputPath`.

### Detect local output (`--json`)

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
      "endIndex": 17
    }
  ],
  "riskScore": 46,
  "riskLevel": "medium"
}
```

Risk thresholds: `high` >= 60, `medium` >= 30, `low` < 30.

### Failure envelope (`--json`, all scripts)

```json
{
  "success": false,
  "tool": "modeio-redact",
  "mode": "api",
  "level": "dynamic",
  "error": {
    "type": "network_error",
    "message": "anonymize request failed: ConnectionError"
  }
}
```

Error types by script:

| Script | Error types |
|---|---|
| `anonymize.py` | `validation_error`, `network_error`, `api_error`, `io_error` |
| `deanonymize.py` | `validation_error`, `map_error`, `io_error`, `runtime_error` |

Exit codes: `2` for validation errors, `1` for all other failures.

## Failure policy

- **Network/API error on `dynamic`/`strict`/`crossborder`**: Offer to retry with `--level lite` as a local fallback. Inform the user that lite uses a simpler regex engine with fewer detection patterns.
- **`map_error` on deanonymize**: Check whether the map ID is correct and the map file exists in `~/.modeio/redact/maps`. Maps auto-expire after 7 days.
- **`io_error` on file write**: Verify the output directory exists and is writable.
- **Hash mismatch on deanonymize**: The input text has changed since anonymization. Ask the user whether to proceed with `--allow-hash-mismatch`.
- **`validation_error`**: Fix the input and retry. Do not proceed without a successful check.

---

## Jurisdiction codes for `crossborder`

`--sender-code` and `--recipient-code` use the format `<COUNTRY_ISO2> <CITY_CODE>`.

| Code | Jurisdiction |
|------|-------------|
| `CN SHA` | China – Shanghai |
| `CN BJS` | China – Beijing |
| `CN GZH` | China – Guangzhou |
| `CN SZX` | China – Shenzhen |
| `US NYC` | United States – New York |
| `US SFO` | United States – San Francisco |
| `US LAX` | United States – Los Angeles |
| `US CHI` | United States – Chicago |
| `GB LON` | United Kingdom – London |
| `DE BER` | Germany – Berlin |
| `DE FRA` | Germany – Frankfurt |
| `FR PAR` | France – Paris |
| `JP TYO` | Japan – Tokyo |
| `SG SIN` | Singapore |
| `AU SYD` | Australia – Sydney |
| `CA TOR` | Canada – Toronto |
| `KR SEL` | South Korea – Seoul |
| `IN BOM` | India – Mumbai |
| `BR SAO` | Brazil – São Paulo |
| `AE DXB` | UAE – Dubai |

The country portion is the ISO 3166-1 alpha-2 code. The city portion is the IATA airport code. Any valid `<ISO2> <IATA>` pair is accepted by the API; the table above lists common combinations.

---

## When NOT to use

- For command safety or destructive-operation analysis — use `modeio-guardrail` instead.
- For pure policy or legal discussion when no text needs anonymization.
- For content that is already fully anonymized (no originals to protect).

## Resources

- `scripts/anonymize.py`: primary anonymization (`lite` local regex; other levels call backend API)
- `scripts/deanonymize.py`: local-only placeholder restore using saved map files
- `scripts/map_store.py`: local map persistence, resolution, and TTL pruning
- `scripts/detect_local.py`: offline regex detection with risk scoring
- `ANONYMIZE_API_URL`: optional environment override for custom anonymize endpoint
- `MODEIO_REDACT_MAP_DIR`: optional environment override for local map storage directory
