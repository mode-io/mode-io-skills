# modeio-redact Architecture

## Goals

- Keep existing `modeio-redact/scripts/*.py` entrypoints stable.
- Separate detection, workflow, gateway, pre-commit, and setup concerns.
- Keep gateway shielding local-only (no remote detection path).
- Keep pre-commit scanning local and optional.

## Package Layout

```text
modeio-redact/
  modeio_redact/
    core/
      models.py
      policy.py
      pipeline.py
      errors.py
    adapters/
      base.py
      registry.py
      text_adapter.py
      docx_adapter.py
      pdf_adapter.py
    planning/
      resolver.py
      plan_builder.py
    assurance/
      residual_scan.py
      verifier.py
    providers/
      base.py
      local_regex_provider.py
      remote_api_provider.py
    cli/
      anonymize.py
      anonymize_output.py
      deanonymize.py
    detection/
      detect_local.py
    workflow/
      file_types.py
      file_handlers.py
      input_source.py
      file_workflow.py
      map_store.py
    precommit/
      scan.py
    gateway/
      prompt_gateway.py
    setup/
      precommit_scan.py
      prompt_gateway.py
  scripts/
    ... compatibility wrappers ...
```

## Compatibility Strategy

- `scripts/*.py` remain the public command surface for `Makefile`, docs, and existing automation.
- Each script bootstraps the package path, imports the new module, and aliases import-time module references for backward compatibility.
- Existing CLI flags, JSON envelope shapes, and exit-code semantics are preserved.

## Boundary Rules

- Detection core (`modeio_redact/detection/detect_local.py`) remains deterministic and local-only.
- Gateway (`modeio_redact/gateway/prompt_gateway.py`) depends on local detection and local map store only.
- Pre-commit scanner (`modeio_redact/precommit/scan.py`) depends on local detection only.
- File/map helpers live under `modeio_redact/workflow/` and are shared by anonymize/deanonymize and gateway mapping.
- Shared file-output orchestration now has a modular skeleton under `modeio_redact/core|adapters|planning|assurance|providers`:
  - `core/pipeline.py` now includes provider orchestration (`lite` local regex vs non-lite remote API) via provider adapters.
  - `core/pipeline.py` standardizes extract -> plan -> apply -> verify -> finalize for file outputs.
  - `adapters/*` keep file-type details isolated (`text`, `docx`, `pdf`).
  - `planning/*` centralizes canonical span planning from mapping entries.
  - `assurance/*` provides residual-leak verification primitives for fail-closed policies.
  - `providers/*` defines local/remote provider interfaces and wrappers used by the pipeline.
- File type support is registry-driven via `workflow/file_types.py`:
  - `input_source.py` uses the registry and dispatches extension-aware readers.
  - `file_handlers.py` owns format-specific reads/writes (`text`, `docx`, `pdf`).
  - `file_workflow.py` uses registry marker policies (`hash`, `html_comment`, `none`) to decide inline marker behavior.
  - Most structured types use sidecar-only map linkage to avoid mutating file syntax.
  - `.pdf` anonymization uses true PDF redaction (remove text + black fill), and `.pdf` de-anonymization is intentionally unsupported.
- CLI orchestration notes:
  - `cli/anonymize.py` focuses on argument validation, provider dispatch, and top-level error policy.
  - `cli/anonymize_output.py` centralizes file-output pipeline + assurance report serialization.
  - `cli/deanonymize.py` now uses a shared error-emission helper to keep failure paths consistent.

## Regression Checklist

- `python3 -m unittest discover modeio-redact/tests -p "test_*.py"`
- `make precommit-scan-tests`
- `make prompt-gateway-tests`
- CLI smoke checks:
  - `python3 modeio-redact/scripts/anonymize.py --help`
  - `python3 modeio-redact/scripts/deanonymize.py --help`
  - `python3 modeio-redact/scripts/precommit_scan.py --help`
  - `python3 modeio-redact/scripts/prompt_gateway.py --help`
  - `python3 modeio-redact/scripts/setup_precommit_scan.py --help`
  - `python3 modeio-redact/scripts/setup_prompt_gateway.py --help`
