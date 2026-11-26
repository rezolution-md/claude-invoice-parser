# Invoice extraction bake-off

Three boxes, three approaches, the same 10 documents and the same scorer.

## Documents
- `samples/invoices/*.pdf`: the 5 original invoices (real text layer).
- `samples/scanned/*-scan.pdf`: the same 5 invoices as image-only "scans" (130 dpi, grey, slightly rotated, blurred, JPEG). No text layer. Expected answers are identical to the originals.

## Scoring
`scripts/score.py` compares a folder of JSON files with `samples/expected/`, matched by file name. Write your results as:
- `bakeoff/<approach>/clean/<name>.json` for the originals (e.g. `01-us-table.json`)
- `bakeoff/<approach>/scan/<name>.json` for the scans, using the ORIGINAL name (drop `-scan`) so the scorer matches it.
Then run `uv run python scripts/score.py bakeoff/<approach>/clean` and `.../scan`. Do not edit `scripts/score.py` or `samples/expected/`.

Every JSON file must have the same shape as `src/claude_invoice_parser/schema.py` (the `Invoice` model), so the scorer can read it.

## Report
Write `bakeoff/<approach>/RESULTS.md` with:
1. Score on clean and on scan (fields correct / total, as score.py prints), and every miss.
2. Whether `05-math-error` was flagged as needing review (run the repo's validator, `validate.py`, on your output).
3. Cost: API tokens in and out per document and the dollar total if you used the API (state the per-token prices you assumed), or $0.
4. Wall-clock time per document.
5. What broke, what you'd change, and when a client should pick this approach.

## Rules
- Fictional data only; nothing leaves the box except API calls to api.anthropic.com.
- Commit on your own branch `bakeoff/<approach>`; never push.
