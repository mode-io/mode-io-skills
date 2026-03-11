<div align="center">

<p align="center">
  <picture>
    <img src="assets/modeio.png" alt="Mode IO logo" width="120">
  </picture>
</p>

# Mode IO Skills 🛡️🔍

🔒 Privacy, 🛡️ safety, 🔍 repository-audit, and ⚙️ middleware-routing skills for AI agents.

<p align="center">
  <a href="https://www.modeio.ai/">
    <img src="https://img.shields.io/badge/Website-modeio.ai-blue?logo=google-chrome&logoColor=white" alt="Website">
  </a>
  <a href="https://github.com/mode-io/mode-io-skills">
    <img src="https://img.shields.io/badge/GitHub-mode--io--skills-black?style=flat&logo=github&logoColor=white" alt="GitHub">
  </a>
  <a href="https://github.com/mode-io/mode-io-skills/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-Apache%202.0-blue?logo=apache&logoColor=white" alt="Apache 2.0">
  </a>
  <a href="https://github.com/mode-io/mode-io-skills">
    <img src="https://visitor-badge.laobi.icu/badge?page_id=mode-io.mode-io-skills&left_color=gray&right_color=%2342b983" alt="Visitor badge">
  </a>
</p>

</div>

Mode IO helps agents do four things well:

- protect sensitive data before it leaves the prompt
- check risky instructions before tools or state changes run
- audit third-party skills and plugins before install
- route traffic through a local middleware layer with policy hooks and monitoring

This repository is the home of four skills:

| Skill | What it does |
|---|---|
| [`privacy-protector`](./privacy-protector/) | Anonymizes and restores PII in text and supported files, with local detector tuning and higher-assurance API-backed modes |
| [`security`](./security/) | Runs live safety checks on instructions that may trigger tools, edits, destructive actions, or compliance-sensitive operations |
| [`skill-audit`](./skill-audit/) | Performs deterministic static safety audits for third-party skill and plugin repositories before install or execution |
| [`modeio-middleware`](./modeio-middleware/) | Connects agents to the standalone Mode IO middleware gateway for routing, policy hooks, and monitoring |

## Why Teams Use It

- **Safer prompts**: redact sensitive data before it reaches shared channels or external models
- **Safer execution**: stop risky instructions before they become destructive actions
- **Safer installs**: screen third-party skills and plugins with evidence-backed static analysis
- **Safer routing**: put a local policy layer in front of agent traffic
- **Multi-agent ready**: designed for Claude Code, Codex CLI, OpenCode, OpenClaw, and middleware-driven workflows

## See It In Action

### `privacy-protector`

```bash
cd privacy-protector
python3 scripts/anonymize.py \
  --input "Name: John Doe, Email: john@company.com, SSN: 123-45-6789" \
  --level lite
```

```text
Name: [NAME_1], Email: [EMAIL_1], SSN: [SSN_1]
```

### `security`

```bash
cd security
python3 scripts/safety.py \
  -i "Drop all tables in the production database" \
  -c '{"environment":"production","operation_intent":"destructive","scope":"broad","data_sensitivity":"regulated","rollback":"none","change_control":"ticket:DB-9021"}' \
  -t "postgres://prod/main" \
  --json
```

```json
{
  "approved": false,
  "risk_level": "critical"
}
```

### `skill-audit`

```bash
cd skill-audit
python3 scripts/skill_safety_assessment.py evaluate \
  --target-repo /path/to/repo \
  --json
```

```text
decision: caution
risk_score: 42
```

### `modeio-middleware`

```bash
python3 -m pip install git+https://github.com/mode-io/mode-io-middleware
modeio-middleware-setup --health-check
```

The standalone product repo for middleware runtime, monitoring UI, plugin development, and release flow is:

- [`mode-io-middleware`](https://github.com/mode-io/mode-io-middleware)

## Install

Install only the skill you need.

### Option 1: ClawHub / OpenClaw

When a skill is listed in ClawHub, install it by slug:

```bash
clawhub install <skill-slug>
```

### Option 2: `npx skills add`

If you prefer the repo-path workflow, `npx skills add` is still supported:

```bash
npx skills add mode-io/mode-io-skills --skill privacy-protector --agent codex --yes --copy
```

Swap `privacy-protector` for `security`, `skill-audit`, or `modeio-middleware`, and swap `codex` for `claude-code` or `opencode` as needed.

## Learn More

- [`privacy-protector/SKILL.md`](./privacy-protector/SKILL.md)
- [`security/SKILL.md`](./security/SKILL.md)
- [`skill-audit/SKILL.md`](./skill-audit/SKILL.md)
- [`modeio-middleware/SKILL.md`](./modeio-middleware/SKILL.md)

## License

Apache License 2.0.
