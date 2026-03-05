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

`modeio-redact` focuses on anonymize/deanonymize + local detection only.
See `ARCHITECTURE.md` for full package layout and boundary rules.

## Scope

- Included:
  - anonymize (`scripts/anonymize.py`)
  - deanonymize (`scripts/deanonymize.py`)
  - local detector diagnostics (`scripts/detect_local.py`)
  - map lifecycle and file workflow helpers
  - file-output assurance pipeline (coverage verification, residual scan)
- Not included:
  - prompt gateway / runtime request proxying (use `modeio-middleware`)
  - git pre-commit staged diff scanning

## Dependencies

Core dependencies (always required): none beyond the Python standard library.

Optional dependencies (required for specific features):

| Package | Required for | Install |
|---|---|---|
| `requests` | Non-`lite` levels (remote API calls) | `pip install requests` |
| `python-docx` | `.docx` file read/write | `pip install python-docx` |
| `PyMuPDF` (`fitz`) | `.pdf` file read/redact | `pip install PyMuPDF` |

Missing optional packages raise a clear error at runtime when the feature is invoked.

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
- Non-lite API calls retry up to 2 times with exponential backoff (1s base) on 502/503/504 and network errors.
- `.pdf` anonymization supports all levels for text-layer PDFs; non-lite requires API mapping entries for fail-closed projection.
- `.pdf` de-anonymization is not supported.
- Default file output path is `<name>.redacted.<ext>` with collision-safe suffixing.
- Sidecar map ref file `<output>.map.json` is written for file workflows.
- For file outputs, an assurance pipeline runs automatically: `.docx`/`.pdf` use `verified` policy (fail on coverage mismatch or residual findings); all other file types use `best_effort` with coverage enforcement.

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

Map marker embedding styles per file type:

| File type | Marker style | Example |
|---|---|---|
| `.txt` | Hash-comment on first line | `# modeio-redact-map-id: <id>` |
| `.md`, `.markdown` | HTML comment on first line | `<!-- modeio-redact-map-id: <id> -->` |
| All others | No embedded marker | (uses sidecar `.map.json` only) |

```bash
python scripts/deanonymize.py --input "Email: [EMAIL_1]" --json
python scripts/deanonymize.py --input ./notes.redacted.txt --json
```

### `scripts/detect_local.py`

- `-i, --input`: required input text
- `--profile`: `strict`, `balanced`, `precision` (default: `balanced`)
- `--allowlist-file`: optional JSON allowlist rules
- `--blocklist-file`: optional JSON blocklist rules
- `--thresholds-file`: optional JSON threshold overrides
- `--explain`: print heuristic diagnostics in non-JSON mode
- `--json`: output full detector payload

Detects 13 entity types: `phone`, `email`, `idCard`, `creditCard`, `bankCard`, `address`, `name`, `password`, `apiKey`, `ipAddress`, `ssn`, `passport`, `dateOfBirth`.

Profile thresholds: `strict` lowers base thresholds by -0.12, `balanced` uses defaults, `precision` raises by +0.10.

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

### `anonymize.py --json`

Top-level envelope: `success`, `tool`, `mode`, `level`, `data`.

`data` fields:

- `anonymizedContent`: redacted text
- `hasPII`: boolean
- `mapRef`: `{ mapId, mapPath, sidecarPath? }`
- `outputPath`: written file path (file mode only)
- `warnings`: `[{ code, message }]` (present when applicable)

File-output-only fields (present when input is a file path):

- `applyReport`: `{ expectedCount, foundCount, appliedCount, missingCount, missedSpans, warnings }`
- `verificationReport`: `{ passed, skipped, residualCount, residuals, warnings }`
- `assurancePolicy`: `{ level, failOnCoverageMismatch, failOnResidualFindings }`

### `deanonymize.py --json`

Top-level envelope: `success`, `tool`, `mode`, `data`.

`data` fields:

- `deanonymizedContent`: restored text
- `replacementSummary`: `{ totalReplacements, replacementsByType }`
- `mapRef`: `{ mapId, mapPath }`

### `detect_local.py --json`

Full output fields:

- `originalText`: the unmodified input
- `sanitizedText`: text with PII replaced by placeholders
- `items`: array of detected entities with `type`, `value`, `maskedValue`, `detectionScore`, `scoreReasons`, and positional fields (`startIndex`, `endIndex`)
- `riskScore`: 0.0–1.0 aggregate risk
- `riskLevel`: `low`, `medium`, `high`
- `profile`: active profile name
- `thresholds`: threshold values used per entity type
- `scoringMethod`: scoring algorithm identifier
- `detectorVersion`: detector version string
- `stats`: `{ candidateCount, keptCount }`

## When not to use

- Runtime LLM request/response gateway hooks (`modeio-middleware`)
- Command safety analysis (`modeio-guardrail`)

## Resources

- `scripts/anonymize.py` — CLI entry point for anonymization
- `scripts/deanonymize.py` — CLI entry point for de-anonymization
- `scripts/detect_local.py` — CLI entry point for local PII detection
- `ARCHITECTURE.md` — package layout and boundary rules
- `ANONYMIZE_API_URL` env var — optional endpoint override (default: `https://safety-cf.modeio.ai/api/cf/anonymize`)
- `MODEIO_REDACT_MAP_DIR` env var — optional local map directory override (default: `~/.modeio/redact/maps/`)
