# modeio-guardrail Architecture

## Goal

Provide a thin, backend-backed command-safety CLI for execution-time safety checks.

## Layout

```text
modeio-guardrail/
  SKILL.md
  ARCHITECTURE.md
  scripts/
    safety.py
    skill_safety_assessment.py  # deprecation stub
  modeio_guardrail/
    cli/
      safety.py
  tests/
    test_safety_contract.py
    test_repo_scan_deprecation.py
```

## Boundaries

- `scripts/safety.py` is the repo-local wrapper for the live safety CLI.
- `modeio_guardrail/cli/safety.py` owns request shaping, retry behavior, JSON envelope formatting, and CLI flow.
- `scripts/skill_safety_assessment.py` is retained only to emit a migration message to `modeio-skill-audit`.

## Runtime flow

1. Accept instruction text plus optional context/target.
2. Call the configured safety backend with retry on transient failures.
3. Normalize the backend payload into the stable success/error envelope.
4. Return a machine-readable decision for the caller to enforce.
