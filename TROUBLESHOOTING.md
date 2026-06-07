# Troubleshooting

## `DEEPSEEK_API_KEY is required`

Set a live API key only in your shell environment:

```bash
export DEEPSEEK_API_KEY=...
```

Do not commit the key or place it in a script.

## `deepseek-runtime: command not found`

Install the package in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
deepseek-runtime doctor --json
```

## Doctor Warns That API Key Is Absent

This is expected if you only want local diagnostics. `doctor --json` does not call the live DeepSeek API.

## Live Smoke Fails With HTTP Status

Check:

- `DEEPSEEK_API_KEY` is present and current.
- `DEEPSEEK_BASE_URL` is not accidentally set to a third-party endpoint.
- `DEEPSEEK_MODEL` is `deepseek-v4-flash` or `deepseek-v4-pro`.
- The official DeepSeek platform account has available balance or quota.

## Release Gate Fails Redaction

Delete generated artifacts and rerun:

```bash
rm -f live-smoke.json release-drill.json release-gate-audit.json
python3 scripts/live_api_smoke.py --out live-smoke.json
python3 scripts/release_drill.py
python3 scripts/release_gate_audit.py \
  --release-drill-result release-drill.json \
  --live-smoke-result live-smoke.json
```

If it still fails, inspect only the leak check booleans first. Do not paste the full live response into public channels.
