---
name: modeioAI-anonymization
description: Use Modeio AI to detect and anonymize PII in text or JSON. Two options: (1) Call https://api.modeio.ai/api/detector/anonymize for anonymization—every run must hit the API, no caching; (2) Local privacy detection (scripts/detect_local.py), regex-based PII detection and masking, no network. Use when the user asks for "anonymize", "redact PII", "detect sensitive info", "PII detection", or "Modeio anonymization".
---

# Modeio AI Anonymization

This skill provides two capabilities: **API anonymization** (server-side masking, requires network) and **local privacy detection** (regex-based detection and masking, no API).

## Rules

- **When using the API**: Every anonymization must call `https://api.modeio.ai/api/detector/anonymize`; no caching or skipping the request.
- **When using local detection**: No external calls; only `scripts/detect_local.py` in this skill is used for regex detection and masking. Suitable for offline or quick scans.

---

## 1. API anonymization (server-side masking)

### Core: Put raw content in `input` to anonymize

Put the content to be masked (text or JSON string) in the request body’s `input` field, call the API, and read the anonymized result from the response’s `anonymizedContent`.

- Raw content → into body `input` (string)
- Call `POST https://api.modeio.ai/api/detector/anonymize`
- Response `data.anonymizedContent` is the anonymized content.

### When to use the API

- User explicitly asks for “Modeio anonymization”, “API masking”, or “compliance anonymization”.
- You need server-consistent masking or audit/compliance records.

### Using scripts/anonymize.py

```bash
# Pass content string directly
python scripts/anonymize.py --input "Name: Jack, ID number: 110101199001011234"

# Content from file
python scripts/anonymize.py --input "$(cat sensitive_data.json)"
```

- **URL**: `POST https://api.modeio.ai/api/detector/anonymize`
- **Response**: `data.anonymizedContent` is the anonymized string; `data.hasPII` etc. per actual API.

---

## 2. Local privacy detection (no API)

Local detection matches the behavior of `detectSensitiveLocal` in `api.ts`: regex-based detection of PII (phone, email, ID card, bank card, SSN, API key, password, etc.), outputting detected items, risk score, and masked text—**no network required**.
Name detection is built in as conservative field-anchored matching such as `姓名:`, `联系人:`, or `Name:`.

### When to use local detection

- User asks to “check for sensitive info”, “local detection”, “no API”, or “offline detection”.
- You need a quick risk score and masked result without requiring the Modeio server.

### Using scripts/detect_local.py

```bash
# Output only masked text (default)
python scripts/detect_local.py --input "Phone 138xxx45678 Email test@example.com"

# Output full JSON (originalText, sanitizedText, items, riskScore, riskLevel)
python scripts/detect_local.py --input "Phone 138xxx45678 Email test@example.com" --json

# Name detection is built in (field-anchored)
python scripts/detect_local.py --input "姓名：张三 电话 138xxx45678" --json

# Read from file
python scripts/detect_local.py --input "$(cat draft.txt)" --json
```

### Output fields

- **sanitizedText**: Text with detected PII replaced by placeholders (e.g. `[PHONE_1]`, `[EMAIL_1]`).
- **items**: Each entry has `type`, `label`, `value`, `maskedValue`, `riskLevel`, `startIndex`, `endIndex`, etc.
- **riskScore**: 0–100; higher means higher risk.
- **riskLevel**: `low` / `medium` / `high`.

Supported types include: phone, email, ID card, credit/bank card, IP, SSN, passport, date of birth, API key, password, address, name, etc. (same regex set as in api.ts).

---

## Workflow: which to use

1. **User asks for “Modeio API anonymization” or “server-side masking”**  
   → Use `scripts/anonymize.py` with content in `--input`; get `anonymizedContent` from the API response.

2. **User asks for “detect sensitive info”, “local detection”, “no network”, or “see what PII is there”**  
   → Use `scripts/detect_local.py` with content in `--input`; add `--json` when you need full detail.

3. **Not specified**  
   → Prefer the API when compliance/audit or Modeio server is mentioned; use local detection for quick checks or offline use.

---

## Resources

- **scripts/anonymize.py**: Calls the Modeio API for anonymization.
- **scripts/detect_local.py**: Local PII detection and masking (aligned with `detectSensitiveLocal` in api.ts).
- **api.ts**: Frontend/TS reference (API calls, local detection, types and regex definitions).
