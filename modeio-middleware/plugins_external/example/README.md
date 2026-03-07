# Example External Plugin

This directory contains a shipped `stdio-jsonrpc` example for `modeio-middleware`.

Use it to validate the protocol toolchain before writing your own plugin:

```bash
python modeio-middleware/scripts/validate_plugin_manifest.py plugins_external/example/manifest.json
python modeio-middleware/scripts/run_plugin_conformance.py plugins_external/example/manifest.json python3 plugins_external/example/plugin.py
```

Behavior:

- `pre.request` returns an `annotate` decision with a low-severity finding.
- Other hooks return `pass`.

This example is intentionally non-intrusive and is safe to keep disabled in `config/default.json`.
