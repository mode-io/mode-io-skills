<div align="center">

<p align="center">
  <picture>
    <img src="assets/modeio.png" alt="Modeio Logo" width="120px">
  </picture>
</p>
<h1>Mode IO.AI: Dynamic Privacy & Compliance Protector</h1>

</div>

<p align="center">
  <a href='https://www.modeio.ai/'>
  <img src='https://img.shields.io/badge/Website-modeio.ai-blue?logo=google-chrome&logoColor=white'></a>
  <a href='https://github.com/mode-io/mode-io-skills'>
  <img src='https://img.shields.io/badge/GitHub-Code-black?style=flat&logo=github&logoColor=white'></a>
  <img src='https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white'>
  <img src='https://img.shields.io/badge/API-Cloudflare%20Workers-F38020?logo=cloudflare&logoColor=white'>
  <a href='https://github.com/mode-io/mode-io-skills' target='_blank' rel='noopener noreferrer'>
  <img src="https://visitor-badge.laobi.icu/badge?page_id=mode-io.mode-io-skills&left_color=gray&right_color=%2342b983">
  </a>
</p>

# 😎 About Us

**Mode IO.AI** is your **dynamic privacy and compliance protector**. We provide privacy capabilities for HIPAA, GDPR, and similar compliance scenarios — helping you safely anonymize and redact personally identifiable information (PII) in data processing, cross-border transfers, and AI workflows.

This repo (**mode-io-skills**) offers **Agent Skills** that integrate with Claude Code, Codex CLI, OpenClaw, OpenCode, Cursor, and other AI environments. Through standardized skill descriptions and scripts, AI assistants can run local regex masking (`lite`) or call Modeio APIs (`dynamic`/`strict`/`crossborder`) whenever anonymization, redaction, PII removal, or safety checks are needed.

> [!NOTE]
> `modeio-redact` `lite` runs fully local regex masking with no network call. Other anonymization levels (`dynamic`/`strict`/`crossborder`) and all safety checks perform real API requests (no caching) for auditable and traceable output.
> For `crossborder`, you must provide explicit `--sender-code` and `--recipient-code` each run.

## ✨ Why teams like this

- **Fast onboarding** — install only the skill you need
- **Flexible execution** — use local regex masking for `lite`, or live API checks for higher-assurance analysis
- **Multi-agent friendly** — works across Claude Code, Codex CLI, OpenClaw, OpenCode, and Cursor

# 👀 See It In Action

### Anonymization — `lite` (local, no network)

> *A developer pastes a customer record into a shared channel. The agent redacts locally in milliseconds.*

```bash
python modeio-redact/scripts/anonymize.py \
  --input "Name: John Doe, Email: johndoe@company.com, Phone: 415-555-1234, SSN: 123-45-6789" \
  --level lite
```

```
Name: [NAME_1], Email: [EMAIL_1], Phone: [PHONE_1], SSN: [SSN_1]
```

<details>
<summary>JSON output (<code>--json</code>)</summary>

```json
{
  "success": true,
  "tool": "modeio-redact",
  "mode": "local-regex",
  "level": "lite",
  "data": {
    "anonymizedContent": "Name: [NAME_1], Email: [EMAIL_1], Phone: [PHONE_1], SSN: [SSN_1]",
    "hasPII": true,
    "localDetection": {
      "items": [
        { "type": "name",  "value": "John Doe",            "riskLevel": "low" },
        { "type": "email", "value": "johndoe@company.com",  "riskLevel": "medium" },
        { "type": "phone", "value": "415-555-1234",          "riskLevel": "medium" },
        { "type": "ssn",   "value": "123-45-6789",           "riskLevel": "high" }
      ],
      "riskScore": 100,
      "riskLevel": "high"
    }
  }
}
```

</details>

---

### Anonymization — `dynamic` (LLM-powered)

> *An HR system exports employee data for a vendor. The agent catches PII that regex would miss — employee IDs, city names, state abbreviations.*

```bash
python modeio-redact/scripts/anonymize.py \
  --input "Please update the account for Alice Wang (alice.wang@techcorp.io). Her employee ID is E-20231542 and she can be reached at 650-234-5678. Ship the package to 1455 Market Street, San Francisco, CA." \
  --level dynamic
```

```
Please update the account for [REDACTED_NAME_1] ([REDACTED_EMAIL_1]).
Her employee ID is [REDACTED_EMPLOYEE_ID_1] and she can be reached at [REDACTED_PHONE_NUMBER_1].
Ship the package to [REDACTED_STREET_ADDRESS_1], [REDACTED_CITY_1], [REDACTED_STATE_1].
```

> `dynamic` catches **employee ID**, **city**, and **state** — things regex-based `lite` would miss. Privacy score: **75 → 100**.

<details>
<summary>JSON output (<code>--json</code>)</summary>

```json
{
  "success": true,
  "tool": "modeio-redact",
  "mode": "api",
  "level": "dynamic",
  "data": {
    "hasPII": true,
    "anonymizedContent": "Please update the account for [REDACTED_NAME_1] ([REDACTED_EMAIL_1]). Her employee ID is [REDACTED_EMPLOYEE_ID_1] and she can be reached at [REDACTED_PHONE_NUMBER_1]. Ship the package to [REDACTED_STREET_ADDRESS_1], [REDACTED_CITY_1], [REDACTED_STATE_1].",
    "mapping": [
      { "original": "Alice Wang",           "anonymized": "[REDACTED_NAME_1]",           "type": "NAME" },
      { "original": "alice.wang@techcorp.io","anonymized": "[REDACTED_EMAIL_1]",          "type": "EMAIL" },
      { "original": "E-20231542",           "anonymized": "[REDACTED_EMPLOYEE_ID_1]",    "type": "EMPLOYEE_ID" },
      { "original": "650-234-5678",         "anonymized": "[REDACTED_PHONE_NUMBER_1]",   "type": "PHONE_NUMBER" },
      { "original": "1455 Market Street",   "anonymized": "[REDACTED_STREET_ADDRESS_1]", "type": "STREET_ADDRESS" },
      { "original": "San Francisco",        "anonymized": "[REDACTED_CITY_1]",           "type": "CITY" },
      { "original": "CA",                   "anonymized": "[REDACTED_STATE_1]",          "type": "STATE" }
    ],
    "privacyScore": { "before": 75, "after": 100 }
  }
}
```

</details>

---

### Anonymization — `crossborder` (compliance + legal analysis)

> *A company in Shanghai transfers a customer record to a US partner. The agent anonymizes **and** flags GDPR violations with cross-border legal guidance.*

```bash
python modeio-redact/scripts/anonymize.py \
  --input "Customer record: Name: 张伟, ID: 310101199001011234, Phone: 13812345678, Email: zhangwei@example.cn. Transfer this data to our US partner office in New York for account verification." \
  --level crossborder --sender-code "CN SHA" --recipient-code "US NYC"
```

```
Customer record: Name: [REDACTED_NAME_1], ID: [REDACTED_ID_NUMBER_1],
Phone: [REDACTED_PHONE_NUMBER_1], Email: [REDACTED_EMAIL_1].
Transfer this data to our US partner office in [REDACTED_LOCATION_1] for account verification.

Compliance score: 30/100 — violated: Article 6, 13, 44, 25
Cross-border: CN SHA → US NYC triggers PIPL/CSL obligations
```

<details>
<summary>JSON output (<code>--json</code>)</summary>

```json
{
  "success": true,
  "tool": "modeio-redact",
  "mode": "api",
  "level": "crossborder",
  "data": {
    "hasPII": true,
    "riskLevel": "High",
    "anonymizedContent": "Customer record: Name: [REDACTED_NAME_1], ID: [REDACTED_ID_NUMBER_1], Phone: [REDACTED_PHONE_NUMBER_1], Email: [REDACTED_EMAIL_1]. Transfer this data to our US partner office in [REDACTED_LOCATION_1] for account verification.",
    "mapping": [
      { "original": "张伟",                "anonymized": "[REDACTED_NAME_1]",         "type": "NAME" },
      { "original": "310101199001011234",  "anonymized": "[REDACTED_ID_NUMBER_1]",    "type": "ID_NUMBER" },
      { "original": "13812345678",         "anonymized": "[REDACTED_PHONE_NUMBER_1]", "type": "PHONE_NUMBER" },
      { "original": "zhangwei@example.cn", "anonymized": "[REDACTED_EMAIL_1]",        "type": "EMAIL" },
      { "original": "New York",            "anonymized": "[REDACTED_LOCATION_1]",     "type": "LOCATION" }
    ],
    "privacyScore": { "before": 95, "after": 100 },
    "complianceAnalysis": {
      "overall_score": 30,
      "violated_articles": [
        { "article": "Article 6",  "description": "No legal basis for processing is identified." },
        { "article": "Article 13", "description": "Data subjects not informed about the transfer." },
        { "article": "Article 44", "description": "No safeguards for international data transfer." },
        { "article": "Article 25", "description": "Data protection by design not evident." }
      ]
    },
    "crossBorderAnalysis": "The transfer from CN SHA to US NYC triggers PIPL and CSL obligations. Required: CAC security assessment or Standard Contractual Clauses, recipient due diligence, data minimization, and data subject rights mechanisms."
  }
}
```

</details>

---

### Safety check — dangerous instruction

> *An automated pipeline receives an instruction to wipe a production database. The agent blocks it.*

```bash
python modeio-guardrail/scripts/safety.py \
  -i "Drop all tables in the production database and rebuild from scratch" \
  -c "production" -t "postgres://prod-db:5432/main"
```

```
approved: false
risk_level: critical
is_destructive: true
is_reversible: false
recommendation: Never execute DROP TABLE directly on production. Ensure backup
  and recovery procedures are in place. Consider blue/green deployments or
  schema migrations that preserve data.
```

<details>
<summary>JSON output (<code>--json</code>)</summary>

```json
{
  "success": true,
  "tool": "modeio-guardrail",
  "mode": "api",
  "data": {
    "approved": false,
    "risk_level": "critical",
    "risk_types": ["data loss", "denial-of-service", "system instability"],
    "concerns": [
      "Direct and complete data loss for all existing data in the production database.",
      "Immediate and prolonged service outage for any applications relying on the database.",
      "Potential for irreversible data loss if no recent, validated backups are available."
    ],
    "recommendation": "Never execute DROP TABLE directly on production without a comprehensive change management plan. Ensure robust backup and recovery procedures are in place. Consider blue/green deployments or schema migrations that preserve data.",
    "is_destructive": true,
    "is_reversible": false
  }
}
```

</details>

---

### Safety check — safe instruction

> *A read-only monitoring command. The agent confirms it is low-risk.*

```bash
python modeio-guardrail/scripts/safety.py \
  -i "List all running containers and display their resource usage"
```

```
approved: true
risk_level: low
is_destructive: false
is_reversible: true
```

<details>
<summary>JSON output (<code>--json</code>)</summary>

```json
{
  "success": true,
  "tool": "modeio-guardrail",
  "mode": "api",
  "data": {
    "approved": true,
    "risk_level": "low",
    "risk_types": ["Information Disclosure"],
    "concerns": [
      "Read-only monitoring operation. Does not modify the system or delete data.",
      "Minor information disclosure risk if output is exposed to unauthorized individuals."
    ],
    "recommendation": "Ensure only authorized personnel have access to execute container listing commands. Implement proper access controls and secure logging.",
    "is_destructive": false,
    "is_reversible": true
  }
}
```

</details>

---

# 🧰 Skills

**`modeio-redact`** — Masks PII in text or JSON via the Modeio anonymization API. Also supports offline regex detection.

> Trigger phrases: *"anonymize", "redact PII", "mask sensitive data", "scrub credentials", "detect personal data"*

**`modeio-guardrail`** — Evaluates instructions for destructive operations, prompt injection, irreversible actions, and compliance violations. Also supports prompt-only static scanning of third-party skill repos before install.

> Trigger phrases: *"safety check", "risk assessment", "security audit", "destructive check", "instruction audit", "scan this skill repo", "is this skill dangerous"*

**`modeio-middleware`** — Runs a local OpenAI-compatible request/response middleware gateway for Codex/OpenCode routing. Supports plugin-driven pre-request and post-response controls, with optional guardrail/redact adapters.

> Trigger phrases: *"middleware gateway", "route provider through local proxy", "pre request hook", "post response hook", "OpenCode baseURL middleware", "Codex OPENAI_BASE_URL"*

Static scan contract: [`modeio-guardrail/prompts/static_repo_scan.md`](modeio-guardrail/prompts/static_repo_scan.md)

## 🔬 Anonymization Levels

Each level uses a **different strategy** (not additive layers):

| Level | Strategy | What it does |
|-------|----------|-------------|
| `lite` | Local regex (no network) | Fast pattern-based redaction (emails, phones, SSNs, credit cards, API keys, etc.) executed locally. |
| `dynamic` | LLM | Context-aware semantic anonymization. Detects direct + inferrable PII. |
| `strict` | LLM + compliance | Same as `dynamic`, plus a parallel GDPR compliance analysis. |
| `crossborder` | LLM + compliance + legal | Same as `strict`, plus a cross-border data transfer legal analysis. Requires sender/recipient jurisdiction codes. |

> **Default level is `dynamic`.** Use `--level crossborder` with explicit `--sender-code` and `--recipient-code` when cross-border analysis is needed.

<details>
<summary>Jurisdiction code reference (click to expand)</summary>

Codes use the format `<ISO 3166-1 alpha-2> <IATA city code>`. Common examples:

| Code | Jurisdiction |
|------|-------------|
| `CN SHA` | China – Shanghai |
| `CN BJS` | China – Beijing |
| `US NYC` | United States – New York |
| `US SFO` | United States – San Francisco |
| `GB LON` | United Kingdom – London |
| `DE FRA` | Germany – Frankfurt |
| `JP TYO` | Japan – Tokyo |
| `SG SIN` | Singapore |
| `AU SYD` | Australia – Sydney |
| `CA TOR` | Canada – Toronto |

Any valid `<ISO2> <IATA>` pair is accepted. See [modeio-redact/SKILL.md](modeio-redact/SKILL.md) for the full list.
</details>

# 🚀 Quick Start

> [!TIP]
> This is a central repo with multiple skills. Install only the specific skill you need.

## 1) OpenClaw quick start 🦞

- OpenClaw website: https://openclaw.ai

Copy/paste one prompt into your OpenClaw agent:

```text
Install this skill:
https://github.com/mode-io/mode-io-skills/tree/main/modeio-redact
```

or

```text
Install this skill:
https://github.com/mode-io/mode-io-skills/tree/main/modeio-guardrail
```

or

```text
Install this skill:
https://github.com/mode-io/mode-io-skills/tree/main/modeio-middleware
```

For CLI installs below, add `-g` for global (user-level) install.

## 2) Install for Claude Code

```bash
npx skills add mode-io/mode-io-skills --skill modeio-redact --agent claude-code --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-guardrail --agent claude-code --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-middleware --agent claude-code --yes --copy
```

## 3) Install for Codex CLI

```bash
npx skills add mode-io/mode-io-skills --skill modeio-redact --agent codex --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-guardrail --agent codex --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-middleware --agent codex --yes --copy
```

## 4) Install for OpenCode

```bash
npx skills add mode-io/mode-io-skills --skill modeio-redact --agent opencode --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-guardrail --agent opencode --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-middleware --agent opencode --yes --copy
```

## 5) Install for Cursor

```bash
npx skills add mode-io/mode-io-skills --skill modeio-redact --agent cursor --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-guardrail --agent cursor --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-middleware --agent cursor --yes --copy
```

## 6) Verify in 30 seconds ✅

After installing, ask your agent:

```text
Anonymize this text before sharing externally: "Name: John Doe, SSN: 123-45-6789"
```

Expected output:

```
Name: [REDACTED_NAME_1], SSN: [REDACTED_SSN_1]
```

```text
Run a safety check on this instruction: "Delete all log files in production"
```

Expected output:

```json
{
  "approved": false,
  "risk_level": "critical",
  "is_destructive": true,
  "is_reversible": false,
  "recommendation": "..."
}
```

```text
Scan this skill repo before install and tell me if it is dangerous: <repo_url_or_local_path>
```

Expected output (shape):

```text
Verdict: ALLOW|WARN|BLOCK|UNVERIFIED
Risk Score: <0-100>
Top Findings:
- file:line + exact snippet + fix
```

```text
Set up local middleware routing for Codex and OpenCode so every request/response passes through policy hooks.
```

Expected output (shape):

```text
Gateway: http://127.0.0.1:8787/v1
Codex set command: export OPENAI_BASE_URL=...
OpenCode config: changed=true backup=...
Health: healthy
```

> [!TIP]
> If you see redacted placeholders and a structured risk response like above, you are fully set up.

## 7) Install dependencies (for manual script execution) 📦

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Reuse one environment for all AI clients.

<details>
<summary><h1>🛠 Manual API Call (Advanced)</h1></summary>

> **Warning:** This section is for manual operation only. In normal usage, install the skills and let the agent invoke them automatically.

## Run scripts manually

From the repo root:

```bash
# Default level is dynamic (LLM-powered, no jurisdiction codes needed)
python modeio-redact/scripts/anonymize.py --input "Email: alice@example.com"

# Local-only lite mode — no network, runs in milliseconds
python modeio-redact/scripts/anonymize.py --input "Email: alice@example.com, Phone: 415-555-1234" --level lite

# Crossborder — full compliance + legal analysis (requires jurisdiction codes)
python modeio-redact/scripts/anonymize.py --input "Name: 张伟, ID: 310101199001011234" --level crossborder --sender-code "CN SHA" --recipient-code "US NYC"

# File path input is auto-detected for supported formats
python modeio-redact/scripts/anonymize.py --input ./sensitive_notes.txt --level dynamic
python modeio-redact/scripts/anonymize.py --input ./handoff.md --level lite
python modeio-redact/scripts/anonymize.py --input ./incident.docx --level lite
python modeio-redact/scripts/anonymize.py --input ./incident.pdf --level lite

# File input writes output files by default:
# ./sensitive_notes.redacted.txt + ./sensitive_notes.redacted.map.json

# PDF note:
# - .pdf anonymization is supported for text-layer PDFs in --level lite only.
# - Redaction removes underlying text and applies black fill.
# - .pdf de-anonymization is not supported.
# - file outputs enforce coverage checks by default.
# - .docx/.pdf also run residual verification by default.

# Optional file output controls
python modeio-redact/scripts/anonymize.py --input ./sensitive_notes.txt --level lite --in-place
python modeio-redact/scripts/anonymize.py --input "Email: alice@example.com" --output ./manual-redacted.txt --json

# Local de-anonymization (auto map resolution for file input)
python modeio-redact/scripts/deanonymize.py --input ./sensitive_notes.redacted.txt --json
python modeio-redact/scripts/deanonymize.py --input ./sensitive_notes.redacted.txt --in-place --json
python modeio-redact/scripts/deanonymize.py --input "Email: [EMAIL_1]" --map 20260304T050000Z-a1b2c3d4 --json

# Machine-readable JSON output (works with any level)
python modeio-redact/scripts/anonymize.py --input "Email: alice@example.com" --level dynamic --json

# Safety checks
python modeio-guardrail/scripts/safety.py -i "Delete all log files"
python modeio-guardrail/scripts/safety.py -i "Modify database permissions" -c "production" -t "/var/lib/mysql" --json

# Generic middleware gateway (Codex/OpenCode)
python modeio-middleware/scripts/setup_middleware_gateway.py --client both --health-check
python modeio-middleware/scripts/middleware_gateway.py --host 127.0.0.1 --port 8787 --upstream-chat-url "https://api.openai.com/v1/chat/completions" --upstream-responses-url "https://api.openai.com/v1/responses"
# Quickstart: modeio-middleware/QUICKSTART.md

# Middleware one-command uninstall (prints Codex unset and optional OpenCode rollback)
python modeio-middleware/scripts/setup_middleware_gateway.py --client both --uninstall --apply-opencode

# Runtime prompt shielding now belongs to modeio-middleware (not modeio-redact)
# Start middleware gateway with separate upstream routes
export MODEIO_GATEWAY_UPSTREAM_API_KEY="<your-upstream-key>"
python modeio-middleware/scripts/middleware_gateway.py \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-chat-url "https://api.openai.com/v1/chat/completions" \
  --upstream-responses-url "https://api.openai.com/v1/responses"

# In your client, set base URL to: http://127.0.0.1:8787/v1

# Run middleware contract and plugin tests
python -m unittest discover modeio-middleware/tests -p "test_*.py"

# Run redact test suite (focused anonymize/deanonymize and file workflows)
python -m unittest discover modeio-redact/tests -p "test_*.py"

# Run extensive anonymize/deanonymize smoke matrix
python -m unittest discover modeio-redact/tests -p "test_smoke_matrix_extensive.py"

# Optional API smoke (requires network + backend availability)
MODEIO_REDACT_RUN_API_SMOKE=1 python -m unittest discover modeio-redact/tests -p "test_smoke_matrix_extensive.py"

# Offline local detection (detailed risk scoring)
python modeio-redact/scripts/detect_local.py --input "Phone 13812345678 Email test@example.com" --json
python modeio-redact/scripts/detect_local.py --input "Name: Alice Wang" --profile precision --json
python modeio-redact/scripts/detect_local.py --input "Project codename Phoenix" --blocklist-file ./blocklist.json --json
python modeio-redact/scripts/detect_local.py --input "Email: alice@example.com" --explain
```

> Local detector score fields are heuristic decision scores (for threshold gating), not statistical confidence intervals.

> `--input` auto-reads supported file paths (`.txt`, `.md`, `.markdown`, `.csv`, `.tsv`, `.json`, `.jsonl`, `.yaml`, `.yml`, `.xml`, `.html`, `.htm`, `.rst`, `.log`, `.docx`, `.pdf`).
> `.pdf` requires a text layer, is supported only with `--level lite`, and is anonymize-only.
> `.docx` and `.pdf` outputs run verified fail-closed checks by default.
> For file workflows, anonymize/deanonymize now write output files by default unless you use explicit `--output` or `--in-place`.
> File output JSON includes `applyReport`, `verificationReport`, and `assurancePolicy` for coverage + verification visibility.
> `deanonymize.py` always continues on hash mismatch and emits an `input_hash_mismatch` warning.

For full details, see [modeio-redact/SKILL.md](modeio-redact/SKILL.md), [modeio-guardrail/SKILL.md](modeio-guardrail/SKILL.md), and [modeio-middleware/SKILL.md](modeio-middleware/SKILL.md).

## 🔗 Links

- Website: [modeio.ai](https://www.modeio.ai/)
- Anonymization API: `https://safety-cf.modeio.ai/api/cf/anonymize`
- Safety API: `https://safety-cf.modeio.ai/api/cf/safety`

</details>
