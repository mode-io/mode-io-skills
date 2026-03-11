---
name: modeio-skill-audit
description: >-
  Runs a deterministic static safety audit for third-party AI skill or plugin
  repositories before install or execution. Use when asked to scan a skill repo,
  assess whether a repo is safe to install, run a skill safety assessment, or
  produce evidence-backed findings for pre-install security screening.
version: 1.0.0
metadata:
  openclaw:
    homepage: https://github.com/mode-io/mode-io-skills/tree/main/modeio-skill-audit
    requires:
      bins:
        - python3
        - git
      env:
        - GITHUB_TOKEN
---

# Run pre-install repository safety audits

Use this skill to evaluate a skill, plugin, or repository before you install it, trust it, or recommend it.

This skill is for static evidence-backed auditing only. It does not execute code, install dependencies, or run hooks in the target repository.

Run these commands from inside the `modeio-skill-audit` folder. Set `GITHUB_TOKEN` when you want higher GitHub API rate limits for the optional OSINT precheck.

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

```bash
python scripts/skill_safety_assessment.py evaluate --target-repo /path/to/repo --json > /tmp/skill_scan.json
python scripts/skill_safety_assessment.py prompt --target-repo /path/to/repo --scan-file /tmp/skill_scan.json --include-full-findings
python scripts/skill_safety_assessment.py validate --scan-file /tmp/skill_scan.json --assessment-file /tmp/assessment.md --json
python scripts/skill_safety_assessment.py adjudicate --scan-file /tmp/skill_scan.json --assessment-file /tmp/adjudication.json --json
```

Compatibility alias:

```bash
python scripts/skill_safety_assessment.py scan --target-repo /path/to/repo --json > /tmp/skill_scan.json
```

### `scripts/run_repo_set.py`

Batch benchmark runner for curated repo sets.

```bash
python scripts/run_repo_set.py \
  --repo-set references/repo_sets/fresh_holdout_repos.json \
  --repos-root /path/to/local/repo-cache
```

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
- `references/benchmarking.md` — benchmark runner usage and repo-set interpretation.
