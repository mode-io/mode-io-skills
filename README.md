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
> `modeio-anonymization` `lite` runs fully local regex masking with no network call. Other anonymization levels (`dynamic`/`strict`/`crossborder`) and all safety checks perform real API requests (no caching) for auditable and traceable output.
> For `crossborder`, you must provide explicit `--sender-code` and `--recipient-code` each run.

## ✨ Why teams like this

- **Fast onboarding** — install only the skill you need
- **Flexible execution** — use local regex masking for `lite`, or live API checks for higher-assurance analysis
- **Multi-agent friendly** — works across Claude Code, Codex CLI, OpenClaw, OpenCode, and Cursor

# 🧰 Skills

**`modeio-anonymization`** — Masks PII in text or JSON via the Modeio anonymization API. Also supports offline regex detection.

> Trigger phrases: *"anonymize", "redact PII", "mask sensitive data", "scrub credentials", "detect personal data"*

**`modeio-safety`** — Evaluates instructions for destructive operations, prompt injection, irreversible actions, and compliance violations.

> Trigger phrases: *"safety check", "risk assessment", "security audit", "destructive check", "instruction audit"*

## 🔬 Anonymization Levels

Each level uses a **different strategy** (not additive layers):

| Level | Strategy | What it does |
|-------|----------|-------------|
| `lite` | Local regex (no network) | Fast pattern-based redaction (emails, phones, SSNs, credit cards, API keys, etc.) executed locally. |
| `dynamic` | LLM | Context-aware semantic anonymization. Detects direct + inferrable PII. |
| `strict` | LLM + compliance | Same as `dynamic`, plus a parallel GDPR compliance analysis. |
| `crossborder` | LLM + compliance + legal | Same as `strict`, plus a cross-border data transfer legal analysis. Requires sender/recipient jurisdiction codes. |

# 🚀 Quick Start

> [!TIP]
> This is a central repo with multiple skills. Install only the specific skill you need.

## 1) OpenClaw quick start 🦞

- OpenClaw website: https://openclaw.ai

Copy/paste one prompt into your OpenClaw agent:

```text
Install this skill:
https://github.com/mode-io/mode-io-skills/tree/main/modeio-anonymization
```

or

```text
Install this skill:
https://github.com/mode-io/mode-io-skills/tree/main/modeio-safety
```

For CLI installs below, add `-g` for global (user-level) install.

## 2) Install for Claude Code

```bash
npx skills add mode-io/mode-io-skills --skill modeio-anonymization --agent claude-code --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-safety --agent claude-code --yes --copy
```

## 3) Install for Codex CLI

```bash
npx skills add mode-io/mode-io-skills --skill modeio-anonymization --agent codex --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-safety --agent codex --yes --copy
```

## 4) Install for OpenCode

```bash
npx skills add mode-io/mode-io-skills --skill modeio-anonymization --agent opencode --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-safety --agent opencode --yes --copy
```

## 5) Install for Cursor

```bash
npx skills add mode-io/mode-io-skills --skill modeio-anonymization --agent cursor --yes --copy
npx skills add mode-io/mode-io-skills --skill modeio-safety --agent cursor --yes --copy
```

## 6) Verify in 30 seconds ✅

After installing, ask your agent:

```text
Anonymize this text before sharing externally: "Name: John Doe, SSN: 123-45-6789"
```

```text
Run a safety check on this instruction: "Delete all log files in production"
```

> [!TIP]
> If you get anonymized output and a structured safety risk response, you are fully set up.

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
# Anonymization (API-backed crossborder with explicit jurisdiction codes)
python modeio-anonymization/scripts/anonymize.py --input "Name: John Doe, SSN: 123-45-6789" --level crossborder --sender-code "CN SHA" --recipient-code "US NYC"
python modeio-anonymization/scripts/anonymize.py --input "$(cat sensitive_data.json)" --level crossborder --sender-code "CN SHA" --recipient-code "US NYC"

# Anonymization with a specific level
python modeio-anonymization/scripts/anonymize.py --input "Email: alice@example.com" --level dynamic

# Anonymization with local-only lite mode (no API call)
python modeio-anonymization/scripts/anonymize.py --input "Email: alice@example.com, Phone: 415-555-1234" --level lite

# Machine-readable output contracts
python modeio-anonymization/scripts/anonymize.py --input "Email: alice@example.com" --level dynamic --json
python modeio-safety/scripts/safety.py -i "Delete all log files" --json

# Anonymization (offline / local)
python modeio-anonymization/scripts/detect_local.py --input "Phone 13812345678 Email test@example.com"

# Safety check (API-backed)
python modeio-safety/scripts/safety.py -i "Delete all log files"
python modeio-safety/scripts/safety.py -i "Modify database permissions" -c "production" -t "/var/lib/mysql"
```

> File-path input mode (`--input-type file`) is intentionally deferred for now and will be supported later. Use `--input "$(cat your_file.json)"` as the current workaround.

For full details, see [modeio-anonymization/SKILL.md](modeio-anonymization/SKILL.md) and [modeio-safety/SKILL.md](modeio-safety/SKILL.md).

## 🔗 Links

- Website: [modeio.ai](https://www.modeio.ai/)
- Anonymization API: `https://safety-cf.modeio.ai/api/cf/anonymize`
- Safety API: `https://safety-cf.modeio.ai/api/cf/safety`

</details>
