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
  <img src='https://img.shields.io/badge/Web-page-blue'></a>
  <a href='https://github.com/mode-io/mode-io-skills'>
  <img src='https://img.shields.io/badge/GitHub-Code-black?style=flat&logo=github&logoColor=white'></a>
  <a href="" target='_blank'>
  <img src="https://visitor-badge.laobi.icu/badge?page_id=mode-io.mode-io-skills&left_color=gray&right_color=%2342b983">
  </a>
</p>

# 😎 About Us

**Mode IO.AI** is your **dynamic privacy and compliance protector**. We provide privacy capabilities for HIPAA, GDPR, and similar compliance scenarios—helping you safely anonymize and redact personally identifiable information (PII) in data processing, cross-border transfers, and AI workflows.

This repo (**mode-io-skills**) offers **Agent Skills** that integrate with Claude Code, Codex CLI, OpenCode, Cursor, and other AI environments. Through standardized skill descriptions and scripts, AI assistants can automatically call Modeio APIs whenever anonymization, redaction, PII removal, or safety checks are needed. **Every operation performs a real API request** (no caching), so results are auditable and traceable.

Think of this repo as a lightweight privacy-and-safety layer your AI agent can use by default.

- 📦 **Capabilities:** PII detection & anonymization, compliance-ready redaction, instruction safety checks, data protection for cross-border use cases
- 🤖 **This repo:** Skills and scripts that tell AI agents when and how to call Modeio, so privacy protection and safety checks fit seamlessly into your workflow

## ✨ Why teams like this

- Fast onboarding: one install command and skills are ready.
- Real checks, not mock logic: each run calls live APIs for traceable output.
- Multi-agent friendly: one repo works across Claude Code, Codex CLI, OpenCode, and Cursor.

# 🧰 Skills at a Glance

| Skill | Trigger phrases | What it does |
|---|---|---|
| `modeio-anonymization` | "anonymize", "redact PII", "mask sensitive data", "scrub credentials", "detect personal data" | Calls the Modeio anonymization API to mask PII in text or JSON. Optional offline regex mode is also available. |
| `modeio-safety` | "safety check", "risk assessment", "security audit", "destructive check", "instruction audit" | Evaluates instructions for destructive operations, prompt injection, irreversible actions, and compliance violations. |

# 🚀 Quick Start

## 1) Install for AI Agents (recommended)

**Option A — `skills` CLI (ecosystem standard)**

Start here for the smoothest setup:

```bash
npx skills add mode-io/mode-io-skills
```

Target a specific client if needed:

```bash
npx skills add mode-io/mode-io-skills -a claude-code
npx skills add mode-io/mode-io-skills -a codex
npx skills add mode-io/mode-io-skills -a opencode
npx skills add mode-io/mode-io-skills -a cursor
```

**Option B — alternative installer**

```bash
npx ai-agent-skills install mode-io/mode-io-skills
```

---

## 2) Manual install paths (fallback)

If you prefer manual installation, use these skill directories.

| Client | Project-level path | Global path |
|---|---|---|
| Claude Code ("cloud code") | `.claude/skills/mode-io-skills` | `~/.claude/skills/mode-io-skills` |
| Codex CLI | `.agents/skills/mode-io-skills` | `~/.agents/skills/mode-io-skills` |
| OpenCode | `.agents/skills/mode-io-skills` or `.opencode/skills/mode-io-skills` | `~/.config/opencode/skills/mode-io-skills` |
| Cursor | `.agents/skills/mode-io-skills` or `.cursor/skills/mode-io-skills` | `~/.cursor/skills/mode-io-skills` |

Example (global install, pick the client you use):

```bash
# Claude Code
git clone https://github.com/mode-io/mode-io-skills.git ~/.claude/skills/mode-io-skills

# Codex CLI
git clone https://github.com/mode-io/mode-io-skills.git ~/.agents/skills/mode-io-skills

# OpenCode
git clone https://github.com/mode-io/mode-io-skills.git ~/.config/opencode/skills/mode-io-skills

# Cursor
git clone https://github.com/mode-io/mode-io-skills.git ~/.cursor/skills/mode-io-skills
```

## 3) Verify in 30 seconds

After installing, ask your agent:

```text
Anonymize this text before sharing externally: "Name: John Doe, SSN: 123-45-6789"
```

```text
Run a safety check on this instruction: "Delete all log files in production"
```

If installation is correct, the agent should discover and invoke the skills automatically.

Tip: if you get anonymized output and a structured safety risk response, you are fully set up.

## 4) Install dependencies (for manual script execution)


```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Reuse one environment for all AI clients.

# 🛠 Manual API Call (Advanced / Manual Path)

This section is for manual operation only. In normal usage, install the skills and let the agent invoke them automatically.

## Run scripts manually

From the repo root:

```bash
# Anonymization (API-backed)
python modeio-anonymization/scripts/anonymize.py --input "Name: John Doe, SSN: 123-45-6789"
python modeio-anonymization/scripts/anonymize.py --input "$(cat sensitive_data.json)"

# Anonymization (offline / local)
python modeio-anonymization/scripts/detect_local.py --input "Phone 13812345678 Email test@example.com"

# Safety check (API-backed)
python modeio-safety/scripts/safety.py -i "Delete all log files"
python modeio-safety/scripts/safety.py -i "Modify database permissions" -c "production" -t "/var/lib/mysql"
```

For full details, see [modeio-anonymization/SKILL.md](modeio-anonymization/SKILL.md) and [modeio-safety/SKILL.md](modeio-safety/SKILL.md).

## Links

- Website: [modeio.ai](https://www.modeio.ai/)
- Anonymization API: `https://safety-cf.modeio.ai/api/cf/anonymize`
- Safety API: `https://safety-cf.modeio.ai/api/cf/safety`

## Endpoint defaults

- Default script endpoints use Cloudflare routes:
  - `modeio-anonymization/scripts/anonymize.py` -> `https://safety-cf.modeio.ai/api/cf/anonymize`
  - `modeio-safety/scripts/safety.py` -> `https://safety-cf.modeio.ai/api/cf/safety`
- `modeio-safety/scripts/safety.py` still supports override via `SAFETY_API_URL`.
