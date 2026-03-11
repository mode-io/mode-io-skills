<div align="center">

<p align="center">
  <picture>
    <img src="assets/modeio.png" alt="Modeio Logo" width="120px">
  </picture>
</p>
<h1>Mode IO.AI: Privacy, Safety & Policy Skills for AI Agents</h1>

</div>

<p align="center">
  <a href='https://www.modeio.ai/'>
  <img src='https://img.shields.io/badge/Website-modeio.ai-blue?logo=google-chrome&logoColor=white'></a>
  <a href='https://github.com/mode-io/mode-io-skills'>
  <img src='https://img.shields.io/badge/GitHub-Code-black?style=flat&logo=github&logoColor=white'></a>
  <a href='https://github.com/mode-io/mode-io-skills/blob/main/LICENSE'>
  <img src='https://img.shields.io/badge/License-Apache%202.0-blue?logo=apache&logoColor=white'></a>
  <img src='https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white'>
  <img src='https://img.shields.io/badge/API-Cloudflare%20Workers-F38020?logo=cloudflare&logoColor=white'>
  <a href='https://github.com/mode-io/mode-io-skills' target='_blank' rel='noopener noreferrer'>
  <img src="https://visitor-badge.laobi.icu/badge?page_id=mode-io.mode-io-skills&left_color=gray&right_color=%2342b983">
  </a>
</p>

# 😎 About Us

**Mode IO.AI** is your **dynamic privacy and compliance protector**. We provide privacy, safety, and policy routing capabilities for HIPAA, GDPR, PIPL, and similar compliance scenarios — helping you safely anonymize and redact personally identifiable information (PII), gate risky operations, and route AI requests through local policy controls.

This repo (**mode-io-skills**) offers **Agent Skills** that integrate with Claude Code, Codex CLI, OpenClaw, OpenCode, and other AI environments. Four skills cover the core surface:

- **`privacy-protector`** — PII anonymization and de-anonymization for text, files, and cross-border compliance.
- **`security`** — Real-time pre-execution safety checks for instructions that may trigger tools or state changes.
- **`skill-audit`** — Deterministic pre-install repository safety audit for skills and plugins.
- **`modeio-middleware`** — Thin agent wrapper for the standalone `mode-io-middleware` product repo that runs the local policy gateway and built-in monitoring surface for Codex, OpenCode, OpenClaw, and Claude Code.

Through standardized skill descriptions and scripts, AI assistants can run local regex masking (`lite`) or call Modeio APIs (`dynamic`/`strict`/`crossborder`) whenever anonymization, redaction, PII removal, safety checks, or policy routing are needed.

> [!NOTE]
> `privacy-protector` `lite` runs fully local regex masking with no network call. Other anonymization levels (`dynamic`/`strict`/`crossborder`) and live guardrail safety checks perform real API requests (no caching) for auditable and traceable output.
> For `crossborder`, you must provide explicit `--sender-code` and `--recipient-code` each run.
> `skill-audit` is deterministic static analysis; its GitHub OSINT precheck may call GitHub APIs when the target repo has a GitHub origin.
> `modeio-middleware` remains installable from this skills repo as a thin wrapper, while the runtime, tests, and release workflow now live in `https://github.com/mode-io/mode-io-middleware`.

## ✨ Why teams like this

- **Fast onboarding** — install only the skill you need
- **Flexible execution** — use local regex masking for `lite`, live API checks for higher-assurance analysis, or local gateway for policy routing
- **Policy in front of every request** — middleware gateway intercepts LLM traffic for audit, redaction, and custom hooks
- **Multi-agent friendly** — works across Claude Code, Codex CLI, OpenClaw, and OpenCode

# 👀 See It In Action

### Anonymization — `lite` (local, no network)

> *A developer pastes a customer record into a shared channel. The agent redacts locally in milliseconds.*

```bash
python3 privacy-protector/scripts/anonymize.py \
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
  "tool": "privacy-protector",
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
python3 privacy-protector/scripts/anonymize.py \
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
  "tool": "privacy-protector",
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
python3 privacy-protector/scripts/anonymize.py \
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
  "tool": "privacy-protector",
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
python3 security/scripts/safety.py \
  -i "Drop all tables in the production database and rebuild from scratch" \
  -c '{"environment":"production","operation_intent":"destructive","scope":"broad","data_sensitivity":"regulated","rollback":"none","change_control":"ticket:DB-9021"}' \
  -t "postgres://prod-db:5432/main"
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
  "tool": "security",
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

### Safety context contract (required for mutating instructions)

For `security`, pass `-c/--context` as JSON (single-quoted in shell) with all keys below. Do not send free text like `"production"` only.

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

`-t/--target` must be a concrete resource identifier (absolute path, table, service, or URL).

Example: deletion that should usually be allowed (`local-dev`, single temp file, easy rollback):

```bash
python3 security/scripts/safety.py \
  -i "Delete /tmp/cache/session-42.tmp" \
  -c '{"environment":"local-dev","operation_intent":"cleanup","scope":"single-resource","data_sensitivity":"internal","rollback":"easy","change_control":"none"}' \
  -t "/tmp/cache/session-42.tmp" --json
```

---

### Safety check — safe instruction

> *A read-only monitoring command. The agent confirms it is low-risk.*

```bash
python3 security/scripts/safety.py \
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
  "tool": "security",
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

### Skill audit — pre-install repository scan

> *A team wants to screen a third-party skill repository before installation and keep the review evidence-linked and repeatable.*

```bash
python3 skill-audit/scripts/skill_safety_assessment.py evaluate --target-repo /path/to/skill-repo --json > /tmp/skill_scan.json
python3 skill-audit/scripts/skill_safety_assessment.py prompt --target-repo /path/to/skill-repo --scan-file /tmp/skill_scan.json --include-full-findings
python3 skill-audit/scripts/skill_safety_assessment.py validate --scan-file /tmp/skill_scan.json --assessment-file /tmp/assessment.md --json
```

```text
decision: caution
risk_score: 42
required_highlight_evidence_ids: [E-4AB12F390C, E-7D3110EF92]
```

---

### Middleware gateway — local policy routing

> *A team wants every LLM request/response from Codex and OpenCode to pass through local policy hooks before hitting the upstream provider.*

```bash
# Install the standalone runtime, then start the gateway
python -m pip install git+https://github.com/mode-io/mode-io-middleware

modeio-middleware-gateway \
  --host 127.0.0.1 \
  --port 8787 \
  --upstream-chat-url "https://api.openai.com/v1/chat/completions" \
  --upstream-responses-url "https://api.openai.com/v1/responses"
```

```
Gateway listening on http://127.0.0.1:8787/v1
Routes: /v1/chat/completions, /v1/responses, /connectors/claude/hooks, /healthz
```

```bash
# Configure Codex/OpenCode to route through the gateway
modeio-middleware-setup --apply-opencode --create-opencode-config
```

```
OpenCode config: changed=true backup=/path/to/backup
Gateway health: healthy
```

```bash
# Full product docs and live smoke tooling live in the standalone repo:
# https://github.com/mode-io/mode-io-middleware
```

> The gateway intercepts every request/response, runs configured policy plugins, and produces `x-modeio-*` headers for audit trail. Tap-proxy logs prove upstream traversal.

---

# 🧰 Skills

**`privacy-protector`** — Masks PII in text or JSON via the Modeio anonymization API. Also supports offline regex detection.

> Trigger phrases: *"anonymize", "redact PII", "mask sensitive data", "scrub credentials", "detect personal data"*

**`security`** — Evaluates instructions that may trigger tools, external calls, file edits, permission changes, destructive actions, or compliance risks before execution.

> Trigger phrases: *"safety check", "risk assessment", "before running this", "before editing files", "instruction audit"*

**`skill-audit`** — Runs a deterministic static safety audit for a third-party skill or plugin repository before install or execution.

> Trigger phrases: *"scan this skill repo", "is this repo safe to install", "run a skill safety assessment", "audit this plugin repository"*

**`modeio-middleware`** — Thin skill wrapper that installs and configures the standalone `mode-io-middleware` local policy gateway plus its dashboard and monitoring APIs. The product repo owns runtime code, plugin hosting, observability surfaces, and tests.

> Trigger phrases: *"middleware gateway", "monitor model traffic", "dashboard for agent requests", "pre request hook", "post response hook", "OpenCode baseURL middleware", "Claude hooks connector"*

Skill audit contract: [`skill-audit/references/prompt-contract.md`](skill-audit/references/prompt-contract.md)

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

Any valid `<ISO2> <IATA>` pair is accepted. See [privacy-protector/SKILL.md](privacy-protector/SKILL.md) for the full list.
</details>

# 🚀 Quick Start

> [!TIP]
> This is a central repo with multiple skills. Install only the specific skill you need.

## 1) OpenClaw quick start 🦞

- OpenClaw website: https://openclaw.ai

Copy/paste one prompt into your OpenClaw agent:

```text
Install this skill:
https://github.com/mode-io/mode-io-skills/tree/main/privacy-protector
```

or

```text
Install this skill:
https://github.com/mode-io/mode-io-skills/tree/main/security
```

or

```text
Install this skill:
https://github.com/mode-io/mode-io-skills/tree/main/skill-audit
```

or

```text
Install this skill:
https://github.com/mode-io/mode-io-skills/tree/main/modeio-middleware
```

Then install or clone the standalone runtime from `https://github.com/mode-io/mode-io-middleware` when you actually need to run the gateway.

For CLI installs below, add `-g` for global (user-level) install.

## 2) Install for Claude Code

```bash
npx skills add mode-io/mode-io-skills --skill privacy-protector --agent claude-code --yes --copy
npx skills add mode-io/mode-io-skills --skill security --agent claude-code --yes --copy
npx skills add mode-io/mode-io-skills --skill skill-audit --agent claude-code --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-middleware --agent claude-code --yes --copy
```

## 3) Install for Codex CLI

```bash
npx skills add mode-io/mode-io-skills --skill privacy-protector --agent codex --yes --copy
npx skills add mode-io/mode-io-skills --skill security --agent codex --yes --copy
npx skills add mode-io/mode-io-skills --skill skill-audit --agent codex --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-middleware --agent codex --yes --copy
```

## 4) Install for OpenCode

```bash
npx skills add mode-io/mode-io-skills --skill privacy-protector --agent opencode --yes --copy
npx skills add mode-io/mode-io-skills --skill security --agent opencode --yes --copy
npx skills add mode-io/mode-io-skills --skill skill-audit --agent opencode --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-middleware --agent opencode --yes --copy
```

## 5) Cursor Support

Cursor is not currently supported in this repo, so there is no Cursor installation guide here.

## 6) Work From Source 📦

This repo root is a catalog and source index. Source execution happens inside each skill folder:

- `privacy-protector/` for anonymize, deanonymize, local detector, and file workflows
- `security/` for live safety checks
- `skill-audit/` for deterministic pre-install repository audits
- `modeio-middleware/` for the thin wrapper that points to the standalone `mode-io-middleware` product repo

If you are running commands locally, `cd` into the matching skill folder first and follow that folder's `SKILL.md`. There is no shared repo-root bootstrap or env template anymore.

Each skill folder also includes its own `LICENSE` and `NOTICE` so per-folder distribution stays under Apache License 2.0.

## 7) Verify in 30 seconds ✅

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
Run a Skill Safety Assessment before install for this repo: <repo_url_or_local_path>
```

Expected output (shape):

```text
Decision: reject|caution|approve
Risk Score: <0-100>
Top Findings:
- file:line + exact snippet + fix + evidence refs (E-xxx)
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

## 8) Local Source Commands

For source usage, run commands inside the matching skill folder. Examples:

```bash
cd privacy-protector
python3 scripts/anonymize.py --input "Email: alice@example.com" --level lite --json

cd ../security
python3 -m pip install requests
python3 scripts/safety.py --help

cd ../skill-audit
python3 scripts/skill_safety_assessment.py evaluate --target-repo /path/to/skill-repo --json > /tmp/skill_scan.json
```

For middleware runtime setup, use the standalone product repo: `https://github.com/mode-io/mode-io-middleware`.

<details>
<summary><h1>🛠 Manual Source Usage (Advanced)</h1></summary>

> **Warning:** This section is for manual operation only. In normal usage, install the skills and let the agent invoke them automatically.

Use the individual skill folder as the working directory. The repo root is intentionally catalog-only.

## `privacy-protector`

```bash
cd privacy-protector
python3 scripts/anonymize.py --input "Email: alice@example.com" --level lite --json
python3 scripts/deanonymize.py --input "Email: [EMAIL_1]" --map ~/.modeio/redact/maps/<map-id>.json --json
python3 scripts/detect_local.py --input "Phone 13812345678 Email test@example.com" --json
bash scripts/smoke_redact.sh
```

## `security`

```bash
cd security
python3 -m pip install requests
python3 scripts/safety.py -i "Delete all log files"
python3 scripts/safety.py -i "Modify database permissions" -c '{"environment":"production","operation_intent":"permission-change","scope":"single-resource","data_sensitivity":"regulated","rollback":"partial","change_control":"ticket:SEC-118"}' -t "/var/lib/mysql" --json
```

## `skill-audit`

```bash
cd skill-audit
python3 scripts/skill_safety_assessment.py evaluate --target-repo /path/to/skill-repo --json > /tmp/skill_scan.json
python3 scripts/skill_safety_assessment.py prompt --target-repo /path/to/skill-repo --scan-file /tmp/skill_scan.json
python3 scripts/skill_safety_assessment.py validate --scan-file /tmp/skill_scan.json --assessment-file /tmp/assessment.md --json
```

## `modeio-middleware`

Use the standalone product repo for runtime install, gateway startup, monitoring, and product-level tests:

- `https://github.com/mode-io/mode-io-middleware`
- Quickstart: `https://github.com/mode-io/mode-io-middleware/blob/main/QUICKSTART.md`

For full details, see [privacy-protector/SKILL.md](privacy-protector/SKILL.md), [security/SKILL.md](security/SKILL.md), [skill-audit/SKILL.md](skill-audit/SKILL.md), [modeio-middleware/SKILL.md](modeio-middleware/SKILL.md), and the standalone middleware product repo at `https://github.com/mode-io/mode-io-middleware`.

## 🔗 Links

- Website: [modeio.ai](https://www.modeio.ai/)
- Anonymization API: `https://safety-cf.modeio.ai/api/cf/anonymize`
- Safety API: `https://safety-cf.modeio.ai/api/cf/safety`

</details>
