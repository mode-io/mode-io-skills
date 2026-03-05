# modeio-guardrail Architecture

## Goals

- Keep existing `modeio-guardrail/scripts/safety.py` entrypoint stable.
- Split reusable safety logic into an importable package module.
- Preserve CLI flags, JSON envelope shape, and exit-code behavior.
- Add deterministic Skill Safety Assessment tooling (scan -> prompt payload -> validator) with script wrappers.

## Package Layout

```text
modeio-guardrail/
  modeio_guardrail/
    cli/
      safety.py
      skill_safety_assessment.py
  scripts/
    safety.py
    skill_safety_assessment.py
  tests/
    test_safety_contract.py
    test_skill_safety_assessment.py
```

## Compatibility Strategy

- `scripts/safety.py` remains the public command surface for docs and automation.
- Script now bootstraps package path and delegates to `modeio_guardrail.cli.safety`.
- Import-time module aliasing keeps backward-compatible test patch targets (for example `patch("safety.detect_safety", ...)`).
- `scripts/skill_safety_assessment.py` uses the same wrapper pattern and delegates to `modeio_guardrail.cli.skill_safety_assessment`.

## Boundary Rules

- `modeio_guardrail/cli/safety.py` owns backend API call behavior, retry policy, envelope formatting, and main CLI flow.
- `scripts/safety.py` should stay thin and avoid business logic.
- `modeio_guardrail/cli/skill_safety_assessment.py` owns deterministic static scan rules, prompt payload rendering, and output validation.
- `scripts/skill_safety_assessment.py` should stay thin and avoid scan/validation business logic.

## Regression Checklist

- `python3 -m unittest modeio-guardrail.tests.test_safety_contract`
- `python3 modeio-guardrail/scripts/safety.py --help`
- `python3 -m unittest modeio-guardrail.tests.test_skill_safety_assessment`
- `python3 modeio-guardrail/scripts/skill_safety_assessment.py scan --target-repo modeio-guardrail --json`
