---
name: modeio-redact
description: >-
  Runs PII anonymization, local de-anonymization, and deterministic local
  detector checks for text and supported files. Use for redact/restore flows,
  file-first anonymization, or offline detector tuning with allowlist,
  blocklist, and threshold controls.
---

# Run anonymization and restore flows

Use this skill when you need to anonymize text/files, restore placeholders with a saved map, or tune the local detector.

## Scope

- Included:
  - anonymize (`scripts/anonymize.py`)
  - deanonymize (`scripts/deanonymize.py`)
  - local detector diagnostics (`scripts/detect_local.py`)
  - file/map workflow helpers
  - fail-closed assurance for rich-file outputs
- Not included:
  - request/response gateway routing (`modeio-middleware`)
  - command safety analysis (`modeio-guardrail`)
  - staged-diff or git pre-commit scanning

## First-run path

From the repo root:

```bash
python scripts/bootstrap_env.py
python scripts/doctor_env.py
modeio-redact/scripts/smoke_redact.sh
```

Optional packages:

- `requests` for non-`lite` API-backed anonymization
- `python-docx` for `.docx`
- `PyMuPDF` for `.pdf`

## Core commands

### Anonymize text

```bash
python modeio-redact/scripts/anonymize.py \
  --input "Email: alice@example.com, Phone: 415-555-1234" \
  --level lite \
  --json
```

### Anonymize a file

```bash
python modeio-redact/scripts/anonymize.py \
  --input ./incident.docx \
  --level lite \
  --json
```

### Restore from a saved map

```bash
python modeio-redact/scripts/deanonymize.py \
  --input "Email: [EMAIL_1]" \
  --map ~/.modeio/redact/maps/<map-id>.json \
  --json
```

### Tune the local detector

```bash
python modeio-redact/scripts/detect_local.py \
  --input "Project codename Phoenix is approved. Reach support@example.com." \
  --allowlist-file modeio-redact/examples/detect-local/allowlist.json \
  --blocklist-file modeio-redact/examples/detect-local/blocklist.json \
  --thresholds-file modeio-redact/examples/detect-local/thresholds.json \
  --json
```

## Level selection

| Scenario | Level |
|---|---|
| Offline or no network | `lite` |
| General anonymization | `dynamic` |
| Compliance-sensitive review | `strict` |
| Cross-region transfer analysis | `crossborder` |

For `crossborder`, pass both `--sender-code` and `--recipient-code`.

## Validation

```bash
python -m unittest discover modeio-redact/tests -p "test_*.py"
python -m unittest discover modeio-redact/tests -p "test_smoke_matrix_extensive.py"
modeio-redact/scripts/smoke_redact.sh
```

Set `MODEIO_REDACT_SKIP_API_SMOKE=1` when you want the extensive smoke matrix to skip remote API coverage.

## Resources

- `ARCHITECTURE.md` for package boundaries
- `references/cli-contracts.md` for flags and output contracts
- `references/file-workflows.md` for map linkage and assurance behavior
- `references/local-detector.md` for profiles and shipped config examples
- `examples/detect-local/` for ready-to-edit tuning files

## When not to use

- Middleware interception or policy routing
- Safety approval/block decisions
