---
name: modeio-redact
description: >-
  Runs PII anonymization and local de-anonymization for text/JSON strings and
  supported file-path input (`.txt`, `.md`, `.markdown`, `.csv`, `.tsv`,
  `.json`, `.jsonl`, `.yaml`, `.yml`, `.xml`, `.html`, `.htm`, `.rst`, `.log`,
  `.docx`, `.pdf`). Supports local regex masking in `lite` mode, remote API
  anonymization in `dynamic`/`strict`/`crossborder`, and local placeholder
  restore using saved map files.
---

# Run anonymization checks for text and files

`modeio-redact` now focuses on anonymize/deanonymize + local detection only.

## Scope

- Included:
  - anonymize (`scripts/anonymize.py`)
  - deanonymize (`scripts/deanonymize.py`)
  - local detector diagnostics (`scripts/detect_local.py`)
  - map lifecycle and file workflow helpers
- Not included:
  - prompt gateway / runtime request proxying (use `modeio-middleware`)
  - git pre-commit staged diff scanning

## Execution policy

1. Default to `scripts/anonymize.py --json` for structured output.
2. Use `scripts/deanonymize.py` for local restore (no network call).
3. Use `--level lite` for offline/no-network anonymization.
4. Use `scripts/detect_local.py` only when detailed local diagnostics are requested.

## Level selection

| Scenario | Level | Reason |
|---|---|---|
| Offline or no network available | `lite` | Local regex only, no API call |
| General anonymization (default) | `dynamic` | Remote API path for broad coverage |
| Compliance-sensitive workflows | `strict` | Includes compliance analysis |
| Cross-region transfer workflows | `crossborder` | Requires jurisdiction codes |

## Scripts

### `scripts/anonymize.py`

- `-i, --input`: required, literal content or supported file path
- `--level`: `lite`, `dynamic`, `strict`, `crossborder` (default: `dynamic`)
- `--sender-code`: required for `crossborder` (example: `CN SHA`)
- `--recipient-code`: required for `crossborder` (example: `US NYC`)
- `--json`: output structured JSON envelope
- `--output`: explicit output file path
- `--in-place`: overwrite input file in place (file-path input only)

Notes:

- Existing supported file paths are auto-read as file input.
- `lite` is local-only; non-lite levels call backend anonymize API.
- `.pdf` anonymization supports all levels for text-layer PDFs; non-lite requires API mapping entries for fail-closed projection.
- `.pdf` de-anonymization is not supported.
- Default file output path is `<name>.redacted.<ext>` with collision-safe suffixing.
- Sidecar map ref file `<output>.map.json` is written for file workflows.

```bash
python scripts/anonymize.py --input "Email: alice@example.com" --level dynamic --json
python scripts/anonymize.py --input "Phone 13812345678" --level lite --json
python scripts/anonymize.py --input ./incident.docx --level lite --json
python scripts/anonymize.py --input ./incident.pdf --level lite --json
python scripts/anonymize.py --input ./incident.pdf --level dynamic --json
```

### `scripts/deanonymize.py`

- `-i, --input`: required, anonymized text or supported file path
- `--map`: optional map ID or map file path
- `--output`: explicit output file path
- `--in-place`: overwrite file input in place
- `--json`: output structured JSON envelope

Map resolution order when `--map` is omitted:

1. Embedded marker in `.txt`/`.md`/`.markdown`
2. Sidecar map file `<input>.map.json`
3. Latest local map fallback (literal text input only)

```bash
python scripts/deanonymize.py --input "Email: [EMAIL_1]" --json
python scripts/deanonymize.py --input ./notes.redacted.txt --json
```

### `scripts/detect_local.py`

- `-i, --input`: required input
- `--profile`: `strict`, `balanced`, `precision` (default: `balanced`)
- `--allowlist-file`: optional JSON allowlist rules
- `--blocklist-file`: optional JSON blocklist rules
- `--thresholds-file`: optional JSON threshold overrides
- `--explain`: print heuristic diagnostics in non-JSON mode
- `--json`: output full detector payload

```bash
python scripts/detect_local.py --input "Phone 13812345678 Email test@example.com" --json
python scripts/detect_local.py --input "Name: Alice Wang" --profile precision --json
```

## Testing

```bash
python -m unittest discover tests -p "test_*.py"
python -m unittest discover tests -p "test_smoke_matrix_extensive.py"
```

## Output contracts

- `anonymize.py --json`:
  - `success`, `tool`, `mode`, `level`, `data`
  - `data.anonymizedContent`, `data.hasPII`, `data.mapRef`, `data.outputPath` (file mode)
- `deanonymize.py --json`:
  - `success`, `tool`, `mode`, `data`
  - `data.deanonymizedContent`, `data.replacementSummary`, `data.mapRef`
- `detect_local.py --json`:
  - `sanitizedText`, `items`, `riskScore`, `riskLevel`, `profile`, `thresholds`

## When not to use

- Runtime LLM request/response gateway hooks (`modeio-middleware`)
- Command safety analysis (`modeio-guardrail`)

## Resources

- `scripts/anonymize.py`
- `scripts/deanonymize.py`
- `scripts/detect_local.py`
- `scripts/map_store.py`
- `ANONYMIZE_API_URL` (optional endpoint override)
- `MODEIO_REDACT_MAP_DIR` (optional local map directory override)
