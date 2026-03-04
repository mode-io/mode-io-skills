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
    cli/
      anonymize.py
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
- File type support is registry-driven via `workflow/file_types.py`:
  - `input_source.py` uses the registry and dispatches extension-aware readers.
  - `file_handlers.py` owns format-specific reads/writes (`text`, `docx`, `pdf`).
  - `file_workflow.py` uses registry marker policies (`hash`, `html_comment`, `none`) to decide inline marker behavior.
  - Most structured types use sidecar-only map linkage to avoid mutating file syntax.
  - `.pdf` anonymization uses true PDF redaction (remove text + black fill), and `.pdf` de-anonymization is intentionally unsupported.

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
