# Example External Plugin

This directory contains a shipped `stdio-jsonrpc` example for `modeio-middleware`.

Use it to validate the protocol toolchain before writing your own plugin:

```bash
modeio-middleware-validate-plugin /path/to/manifest.json
modeio-middleware-plugin-conformance /path/to/manifest.json python3 /path/to/plugin.py
```

Behavior:

- `pre.request` returns an `annotate` decision with a low-severity finding.
- Other hooks return `pass`.

This example is intentionally non-intrusive and is safe to keep disabled in the bundled default config.
