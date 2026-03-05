# Skill Safety Refactor Analysis

## Problem Statement

The prior implementation concentrated scanner rules, scoring, validation, integrity checks, prompt rendering, and CLI routing inside a single module (`modeio_guardrail/cli/skill_safety_assessment.py`, ~3400 lines). This created several engineering risks:

1. High blast radius for small edits (rule changes could accidentally affect CLI/validation behavior).
2. Difficult test targeting (most tests had to run end-to-end through subprocess calls).
3. Duplicate utility logic (JSON object extraction existed in multiple files).
4. Low separability of policy vs mechanics (rule catalogs and decision policy interleaved with scan loops).

## Baseline Structural Findings

- Approximate size before refactor: ~3400 lines in one file.
- Function count before refactor: 70.
- Largest functions (pre-refactor):
  - `main` (~317 lines)
  - `_scan_exec_and_evasion` (~219 lines)
  - `scan_repository` (~201 lines)
  - `validate_assessment_output` (~180 lines)

## Refactor Objectives

1. Preserve public CLI contract (`evaluate`, `scan`, `prompt`, `validate`, `adjudicate`).
2. Preserve output schema and evidence ID determinism.
3. Separate concerns into stable modules:
   - file collection
   - scanner families
   - scoring/decision policy
   - validation/integrity
   - prompt payload rendering
   - command routing

## New Module Topology

```
modeio_guardrail/skill_safety/
  constants.py
  models.py
  json_utils.py
  common.py
  finding.py
  collector.py
  scoring.py
  engine.py
  prompt_payload.py
  validation.py
  context.py
  adjudication.py
  scanners/
    prompt.py
    execution.py
    secret.py
    supply_chain.py
    capability.py
```

And the CLI module is now a thin router:

- `modeio_guardrail/cli/skill_safety_assessment.py`

## Responsibility Mapping

- `constants.py`: policy constants, regex rules, rule groups.
- `models.py`: typed structures (`FileRecord`, `Finding`, `ScanStats`, `LayerState`).
- `json_utils.py`: shared JSON object extraction helper.
- `common.py`: reusable primitives (hashing, snippet compare, path normalization, shell literal safety, etc.).
- `finding.py`: finding insertion, dedupe, layer bookkeeping.
- `collector.py`: repo walk, candidate filtering, prompt/executable surface tagging.
- `scanners/*.py`: domain-specific detectors.
- `scoring.py`: risk contribution math, decision policy, finding-kind policy, score floors.
- `engine.py`: deterministic orchestration and final scan report assembly.
- `prompt_payload.py`: `SCRIPT_SCAN_JSON` prompt serializer.
- `validation.py`: strict output contract validator + integrity re-scan checks.
- `context.py`, `adjudication.py`: retained ownership for context profile and adjudication logic.

## Legacy Cleanup Actions

1. Removed monolithic in-file ownership of all concerns.
2. Consolidated JSON object extraction via shared `json_utils.py`.
3. Reduced CLI module to argument parsing/dispatch behavior.
4. Removed unused helper from old monolith path during extraction.

## Contract Preservation Checks

- CLI command names unchanged.
- Script entrypoint unchanged (`scripts/skill_safety_assessment.py` still delegates to CLI module).
- `scan` alias preserved as compatibility command.
- JSON output structure preserved (`version/tool/run/context_profile/integrity/layers/summary/scoring/findings/...`).

## Characterization + Regression Strategy

1. Added characterization tests for:
   - required output sections present in `evaluate --json` payload,
   - stable evidence IDs across repeated scans on unchanged repo content.
2. Retained/expanded existing behavioral tests for scanner rules and validator constraints.

## Validation Results

- `python3 -m unittest tests.test_skill_safety_assessment` passes.
- `python3 scripts/skill_safety_assessment.py --help` works.
- `python3 scripts/skill_safety_assessment.py evaluate --target-repo . --json` works.
- Baseline and fresh benchmark runs remain executable post-refactor.

## Remaining Improvement Opportunities

1. Add unit tests per scanner module (beyond current CLI-driven coverage).
2. Add schema-level tests for `validation.py` independent of subprocess invocation.
3. Introduce richer dataclasses for runtime findings/report (currently typed dicts for compatibility and migration speed).
4. Add benchmark runner script that consumes `benchmarks/repo_sets/*.json` directly for repeatability.
