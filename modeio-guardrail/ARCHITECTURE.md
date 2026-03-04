# modeio-guardrail Architecture

## Goals

- Keep existing `modeio-guardrail/scripts/safety.py` entrypoint stable.
- Split reusable safety logic into an importable package module.
- Preserve CLI flags, JSON envelope shape, and exit-code behavior.

## Package Layout

```text
modeio-guardrail/
  modeio_guardrail/
    cli/
      safety.py
  scripts/
    safety.py
  tests/
    test_safety_contract.py
```

## Compatibility Strategy

- `scripts/safety.py` remains the public command surface for docs and automation.
- Script now bootstraps package path and delegates to `modeio_guardrail.cli.safety`.
- Import-time module aliasing keeps backward-compatible test patch targets (for example `patch("safety.detect_safety", ...)`).

## Boundary Rules

- `modeio_guardrail/cli/safety.py` owns backend API call behavior, retry policy, envelope formatting, and main CLI flow.
- `scripts/safety.py` should stay thin and avoid business logic.

## Regression Checklist

- `python3 -m unittest modeio-guardrail.tests.test_safety_contract`
- `python3 modeio-guardrail/scripts/safety.py --help`
