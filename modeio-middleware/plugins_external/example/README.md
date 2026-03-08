# Example External Plugin

This directory contains a shipped `stdio-jsonrpc` example for `modeio-middleware`.

Use it to validate the protocol toolchain before writing your own plugin:

```bash
modeio-middleware-validate-plugin plugins_external/example/manifest.json
modeio-middleware-plugin-conformance plugins_external/example/manifest.json python3 plugins_external/example/plugin.py
```

Behavior:

- `pre.request` returns an `annotate` decision with a low-severity finding.
- Other hooks return `pass`.

This example is intentionally non-intrusive and stays disabled in `config/default.json` until you explicitly wire it into a profile.
