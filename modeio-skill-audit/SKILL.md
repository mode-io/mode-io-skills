---
name: modeio-skill-audit
description: >-
  Runs a deterministic static safety audit for third-party AI skill or plugin
  repositories before install or execution. Use when asked to scan a skill repo,
  assess whether a repo is safe to install, run a skill safety assessment, or
  produce evidence-backed findings for pre-install security screening.
version: 0.1.0
metadata:
  openclaw:
    homepage: https://github.com/mode-io/mode-io-skills/tree/main/modeio-skill-audit
    requires:
      bins:
        - python3
---

# Run pre-install repository safety audits

Use this skill to evaluate a skill, plugin, or repository before you install it, trust it, or recommend it.

This skill is for static evidence-backed auditing only. It does not execute code, install dependencies, or run hooks in the target repository.

Tests and benchmark assets are maintainer-only and are excluded from ClawHub uploads.

Run these commands from inside the `modeio-skill-audit` folder. Set `GITHUB_TOKEN` only when you want higher GitHub API rate limits for the automatic GitHub precheck.

## Requirements

- Hard requirement: `python3`
- Optional enhancement: `git` for commit metadata and GitHub-origin discovery
- Optional enhancement: `GITHUB_TOKEN` for higher GitHub API rate limits
- The GitHub precheck only runs when the target repository has a GitHub `origin`
- `evaluate` intentionally skips target-repo `tests/` and fixture paths so the result stays focused on installable runtime surfaces

## Use cases

- Pre-install trust gate for a third-party skill repository.
- Evidence-backed security screening for a plugin or agent extension repo.
- Repeatable repo-audit workflow that produces findings, risk score, and validation artifacts.

## Trigger phrases

- "scan this skill repo"
- "is this repo safe to install"
- "run a skill safety assessment"
- "audit this plugin repository"
- "screen this repo before install"

## Script-first workflow

### `scripts/skill_safety_assessment.py`

Primary CLI for deterministic repository audit, prompt payload generation, validator checks, and adjudication merge.

Packaged command alias when the project is installed:

```bash
modeio-skill-audit evaluate --target-repo /path/to/repo --json
```

```bash
python3 scripts/skill_safety_assessment.py evaluate --target-repo /path/to/repo --json > /tmp/skill_scan.json
python3 scripts/skill_safety_assessment.py prompt --target-repo /path/to/repo --scan-file /tmp/skill_scan.json --include-full-findings
python3 scripts/skill_safety_assessment.py validate --scan-file /tmp/skill_scan.json --assessment-file /tmp/assessment.md --json
python3 scripts/skill_safety_assessment.py adjudicate --scan-file /tmp/skill_scan.json --assessment-file /tmp/adjudication.json --json
```

Compatibility alias:

```bash
python3 scripts/skill_safety_assessment.py scan --target-repo /path/to/repo --json > /tmp/skill_scan.json
```

`scripts/run_repo_set.py` is a maintainer benchmark helper and is not part of the normal ClawHub runtime flow.

## Workflow rules

1. Run `evaluate` first. Treat its scan output as the authoritative baseline.
2. Use `prompt` only after a deterministic scan exists.
3. Use `validate` whenever model-written findings need evidence-linkage checks.
4. If context interpretation matters, use `adjudicate` instead of hand-waving findings.
5. Do not execute code in the target repository.

## When not to use

- Live execution-time safety checks for commands or operations
- Content transformation tasks that need to mask, rewrite, or restore sensitive data
- Local routing or middleware scenarios where requests must flow through a gateway

## References

- `references/architecture.md` — package layout and scan pipeline.
- `references/prompt-contract.md` — strict prompt contract for model-assisted review.
- `references/output-contract.md` — JSON/report contract and compatibility expectations.
