---
name: modeio-anonymization
description: Runs PII anonymization checks for text or JSON. Supports local regex masking in lite mode and server-side analysis in dynamic/strict/crossborder modes. Use when asked to anonymize data, redact PII, mask sensitive information, detect personal data, check for sensitive content, scrub credentials, or run Modeio anonymization.
---

# Run anonymization checks for text and JSON

## Execution policy

1. Default: run `scripts/anonymize.py`.
2. For offline/no-network requests, use `scripts/anonymize.py --level lite` (local regex mode).
3. Use `scripts/detect_local.py` only when the user explicitly wants detailed local detection output (`items`, `riskScore`, `riskLevel`) or local JSON-first diagnostics.

## Script commands

### Primary mode: `scripts/anonymize.py`

- `-i, --input`: required, content to anonymize
- `--level`: anonymization level (`lite`, `dynamic`, `strict`, `crossborder`; default: `dynamic`)
- `--sender-code`: sender jurisdiction code, required for `crossborder` level (example: `CN SHA`)
- `--recipient-code`: recipient jurisdiction code, required for `crossborder` level (example: `US NYC`)
- `--json`: output unified JSON contract for machine consumption
- `--level lite` runs local regex anonymization (no network call).
- `--level dynamic|strict|crossborder` calls `https://safety-cf.modeio.ai/api/cf/anonymize` by default. Override via `ANONYMIZE_API_URL` environment variable.
- File-path input mode is not available yet. Planned in a future update.

```bash
python scripts/anonymize.py --input "Name: Jack, ID number: 110101199001011234"

python scripts/anonymize.py --input "$(cat sensitive_data.json)"

python scripts/anonymize.py --input "Name: Jack, ID number: 110101199001011234" --level crossborder --sender-code "CN SHA" --recipient-code "US NYC"

python scripts/anonymize.py --input "Email: alice@example.com" --level dynamic

python scripts/anonymize.py --input "Email: alice@example.com, Phone: 415-555-1234" --level lite

python scripts/anonymize.py --input "Email: alice@example.com" --level dynamic --json
```

### Output

- Successful responses include top-level `success: true` and a `data` object.
- `data.anonymizedContent`: anonymized content string
- `data.hasPII`: whether sensitive data was detected
- Optional `data` fields can include mapping and analysis metadata.
- For `lite`, output includes `data.mode: local-regex` and `data.localDetection` details.

`--json` output contract:

- `success`: `true`
- `tool`: `modeio-anonymization`
- `mode`: `local-regex` or `api`
- `level`: chosen anonymization level
- `data`: anonymization payload

```json
{
  "success": true,
  "data": {
    "anonymizedContent": "Name: [REDACTED_NAME_1]",
    "hasPII": true
  }
}
```

Failure behavior:

- For API-backed levels (`dynamic`/`strict`/`crossborder`): HTTP/network failure exits non-zero and prints URL/status/exception details to `stderr`.
- API semantic failure (`success: false`) prints full response JSON to `stderr` and exits non-zero.
- With `--json`, failures are emitted as a unified JSON envelope:
  - `success: false`
  - `tool: modeio-anonymization`
  - `mode`: `local-regex` or `api`
  - `level`: chosen anonymization level
  - `error.type`: `validation_error` / `network_error` / `api_error`
  - `error.message`: failure description

### Offline mode: `scripts/detect_local.py`

Use only when user explicitly asks for offline or local detection.

- `-i, --input`: content to scan
- `--json`: output full detection details instead of masked text only
- No network call is made.

```bash
python scripts/detect_local.py --input "Phone 13812345678 Email test@example.com"

python scripts/detect_local.py --input "Name: Alice Wang, phone 415-555-1234" --json
```

### Output

- Default mode prints masked text to `stdout` and summary information to `stderr`.
- `--json` prints full structured output.
- `sanitizedText`: masked text
- `items`: detected entities
- `riskScore`: 0-100
- `riskLevel`: `low` / `medium` / `high`

```json
{
  "originalText": "Phone 13812345678 Email test@example.com",
  "sanitizedText": "Phone [PHONE_1] Email [EMAIL_1]",
  "items": [
    {
      "id": "1",
      "type": "phone"
    },
    {
      "id": "2",
      "type": "email"
    }
  ],
  "riskScore": 46,
  "riskLevel": "medium"
}
```

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

- For command safety or destructive-operation analysis; use `modeio-safety` instead.
- For pure policy or legal discussion when no text needs anonymization.

## Resources

- `scripts/anonymize.py`: default script (`lite` local regex; other levels call `https://safety-cf.modeio.ai/api/cf/anonymize`)
- `scripts/detect_local.py`: offline regex detection
- File-path input mode is intentionally deferred and will be added in a later release.
