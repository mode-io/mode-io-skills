# modeio-redact Architecture

## Goals

- Keep `modeio-redact` focused on anonymize/deanonymize and local detection.
- Keep script wrappers thin and stable for redact core commands.
- Keep file-output assurance fail-closed for supported file workflows.
- Route LLM middleware responsibilities to `modeio-middleware`.

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
  scripts/
    anonymize.py
    deanonymize.py
    detect_local.py
    file_workflow.py
    input_source.py
    map_store.py
```

## Boundary Rules

- Detection core (`modeio_redact/detection/detect_local.py`) remains deterministic and local-only.
- Redact package owns anonymize/deanonymize + map workflows only.
- Middleware gateway routing and prompt request/response hooks live in `modeio-middleware`.
- Pre-commit staged-diff scanning is not part of redact scope.
- File/map helpers under `modeio_redact/workflow/` are shared by anonymize/deanonymize paths.

## Pipeline Notes

- `core/pipeline.py` orchestrates local-regex (`lite`) and remote API providers.
- `planning/*` builds canonical span plans from mapping entries.
- `adapters/*` isolate file-format behavior (`text`, `docx`, `pdf`).
- `assurance/*` applies residual-leak verification for fail-closed output policy.

## Regression Checklist

- `python3 -m unittest discover modeio-redact/tests -p "test_*.py"`
- `python3 -m unittest discover modeio-redact/tests -p "test_smoke_matrix_extensive.py"`
- CLI smoke checks:
  - `python3 modeio-redact/scripts/anonymize.py --help`
  - `python3 modeio-redact/scripts/deanonymize.py --help`
  - `python3 modeio-redact/scripts/detect_local.py --help`
