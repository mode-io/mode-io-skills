# modeio-guardrail Architecture

## Goals

- Keep existing `modeio-guardrail/scripts/safety.py` entrypoint stable.
- Split reusable safety logic into an importable package module.
- Preserve CLI flags, JSON envelope shape, and exit-code behavior.
- Add deterministic Skill Safety Assessment v2 tooling with layered evaluation, deterministic evidence IDs, integrity metadata, prompt payload rendering, and strict validator checks.

## Package Layout

```text
modeio-guardrail/
  modeio_guardrail/
    cli/
      safety.py
      skill_safety_assessment.py
    skill_safety/
      constants.py
      models.py
      common.py
      collector.py
      engine.py
      scoring.py
      finding.py
      prompt_payload.py
      validation.py
      json_utils.py
      context.py
      adjudication.py
      scanners/
        prompt.py
        execution.py
        secret.py
        supply_chain.py
        capability.py
  scripts/
    safety.py
    skill_safety_assessment.py
  tests/
    test_safety_contract.py
    test_skill_safety_assessment.py
  benchmarks/
    run_repo_set.py
    repo_sets/
      fresh_holdout_repos.json
      fresh_sourcepack_repos.json
```

## Compatibility Strategy

- `scripts/safety.py` remains the public command surface for docs and automation.
- Script now bootstraps package path and delegates to `modeio_guardrail.cli.safety`.
- Import-time module aliasing keeps backward-compatible test patch targets (for example `patch("safety.detect_safety", ...)`).
- `scripts/skill_safety_assessment.py` uses the same wrapper pattern and delegates to `modeio_guardrail.cli.skill_safety_assessment`.
- Legacy `scan` command remains available as a compatibility alias; `evaluate` is the authoritative v2 entrypoint.

## Boundary Rules

- `modeio_guardrail/cli/safety.py` owns backend API call behavior, retry policy, envelope formatting, and main CLI flow.
- `scripts/safety.py` should stay thin and avoid business logic.
- `modeio_guardrail/cli/skill_safety_assessment.py` owns argparse and command routing only.
- `modeio_guardrail/skill_safety/engine.py` owns scan orchestration and final report assembly.
- `modeio_guardrail/skill_safety/scanners/*` own domain scanners (prompt/exec/secret/supply/capability).
- `modeio_guardrail/skill_safety/collector.py` owns file collection and scan-surface classification.
- `modeio_guardrail/skill_safety/scoring.py` owns scoring, decision policy, and finding kind classification.
- `modeio_guardrail/skill_safety/validation.py` owns strict JSON summary validation and integrity re-scan checks.
- `modeio_guardrail/skill_safety/prompt_payload.py` owns prompt payload rendering.
- `modeio_guardrail/skill_safety/context.py` owns context profile parsing and context-aware score multipliers.
- `modeio_guardrail/skill_safety/adjudication.py` owns adjudication prompt generation and deterministic merge of LLM evidence decisions.
- `scripts/skill_safety_assessment.py` should stay thin and avoid scan/validation business logic.

## Regression Checklist

- `python3 -m unittest modeio-guardrail.tests.test_safety_contract`
- `python3 modeio-guardrail/scripts/safety.py --help`
- `python3 -m unittest modeio-guardrail.tests.test_skill_safety_assessment`
- `python3 modeio-guardrail/scripts/skill_safety_assessment.py evaluate --target-repo modeio-guardrail --json`
- `python3 modeio-guardrail/scripts/skill_safety_assessment.py scan --target-repo modeio-guardrail --json`
- `python3 modeio-guardrail/scripts/skill_safety_assessment.py adjudicate --scan-file /tmp/skill_scan.json`
- `python3 modeio-guardrail/benchmarks/run_repo_set.py --repo-set modeio-guardrail/benchmarks/repo_sets/fresh_holdout_repos.json --repos-root .tmp-extensive-benchmark/fresh/repos`
