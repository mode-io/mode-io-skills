---
name: modeio-anonymization
description: Runs PII anonymization checks for text or JSON. Supports server-side masking and offline regex detection. Use when asked to anonymize data, redact PII, mask sensitive information, detect personal data, check for sensitive content, scrub credentials, or run Modeio anonymization.
---

# Run anonymization checks for text and JSON

## Execution policy

1. Default: run `scripts/anonymize.py`.
2. Use `scripts/detect_local.py` only if the user explicitly asks for offline, no-network, or local-only detection.

## Script commands

### Primary mode: `scripts/anonymize.py`

- `-i, --input`: required, content to anonymize
- `--level`: anonymization level (`lite`, `dynamic`, `strict`, `crossborder`; default: `crossborder`)
- `--input-type`: content type (`text`, `file`; default: `text`)
- `--sender-code`: sender jurisdiction code, required for `crossborder` level (default: `CN SHA`)
- `--recipient-code`: recipient jurisdiction code, required for `crossborder` level (default: `US NYC`)
- Script calls `https://safety-cf.modeio.ai/api/cf/anonymize` by default. Override via `ANONYMIZE_API_URL` environment variable.

```bash
python scripts/anonymize.py --input "Name: Jack, ID number: 110101199001011234"

python scripts/anonymize.py --input "$(cat sensitive_data.json)"

python scripts/anonymize.py --input "Email: alice@example.com" --level dynamic
```

### Output

- Successful responses include top-level `success: true` and a `data` object.
- `data.anonymizedContent`: anonymized content string
- `data.hasPII`: whether sensitive data was detected
- Optional `data` fields can include mapping and analysis metadata.

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

- HTTP/network failure: script exits non-zero and prints URL/status/exception details to `stderr`.
- API semantic failure (`success: false`): script prints full response JSON to `stderr` and exits non-zero.

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

## When NOT to use

- For command safety or destructive-operation analysis; use `modeio-safety` instead.
- For pure policy or legal discussion when no text needs anonymization.

## Resources

- `scripts/anonymize.py`: default script, calls `https://safety-cf.modeio.ai/api/cf/anonymize`
- `scripts/detect_local.py`: offline regex detection
