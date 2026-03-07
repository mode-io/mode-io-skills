# Local Detector

The local detector is deterministic and offline. It combines:

- regex candidate extraction
- per-type validators
- contextual scoring
- allowlist/blocklist policy hooks
- per-type threshold overrides

## Profiles

- `strict`: lower thresholds, catch more
- `balanced`: default profile
- `precision`: higher thresholds, reduce false positives

## Shipped example configs

Use the example files in `examples/detect-local/`:

- `allowlist.json`
- `blocklist.json`
- `thresholds.json`

Example:

```bash
python modeio-redact/scripts/detect_local.py \
  --input "Reach support@example.com or 10.0.4.12. Project codename Phoenix is approved." \
  --allowlist-file modeio-redact/examples/detect-local/allowlist.json \
  --blocklist-file modeio-redact/examples/detect-local/blocklist.json \
  --thresholds-file modeio-redact/examples/detect-local/thresholds.json \
  --json
```

## Notes

- Placeholders already in redact form (for example `[EMAIL_1]`) are automatically allowlisted.
- Blocklist entries override scoring and force a finding.
- Threshold overrides are best used sparingly and should be validated with the shipped smoke script.
