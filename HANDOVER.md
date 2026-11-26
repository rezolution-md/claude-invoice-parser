Box handover (handover-rules skill v1)

# Bake-off: "vision" baseline (branch `bakeoff/vision`, not pushed)

**Result:** 80/80 fields on clean, 80/80 on scans. `05-math-error` was flagged
`needs_review` on both. Cost $0.263 for all 10 documents at $4 / $20 per million tokens
(`claude-opus-5-5`). About 4.8 s per document.
Full report: `bakeoff/vision/RESULTS.md`.

## What's on the branch
- `bakeoff/vision/run.py`: calls the repo's unchanged `extract_invoice()` and records
  each response's tokens, serving model, wall-clock time and validator issues. `src/`,
  the prompt and the model were not touched.
- `bakeoff/vision/clean/*.json`, `bakeoff/vision/scan/*.json`: extractions (scan files
  use the original names, as the brief says), plus `metrics.json` per set.
- `bakeoff/vision/RESULTS.md`: the report the brief asks for.

## Things to know
- The per-token price comes from Claude Code's built-in Claude API reference (cached
  2026-11-03), not the live pricing page. The bake-off rules allow no traffic except to
  api.anthropic.com.
- Key setup: `ANTHROPIC_API_KEY` is kept for the Claude Code harness. The run used
  `eval "$(discobox-access env)"` then `export ANTHROPIC_API_KEY="$INVOICE_ANTHROPIC_KEY"`
  only for the invoice script. The key is not stored anywhere in the repo.
- Re-run: `uv run python bakeoff/vision/run.py samples/invoices bakeoff/vision/clean`
  (and `samples/scanned bakeoff/vision/scan`), then `uv run python scripts/score.py <dir>`.
- Single run only; timings and `notes` wording vary between runs.
