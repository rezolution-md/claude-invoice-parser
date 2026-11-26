Box handover (handover-rules skill v1)

# Held-out test set for the invoice bake-off

Branch: `bakeoff/holdout` (not pushed).

## What was built
- `samples/holdout/generate_holdout.py`: one dict per invoice is the single source of truth. It writes 12 PDFs, 12 expected JSON files and 4 phone-photo PDFs. Before writing, it runs `validate.py` on every invoice's data: 11 must pass cleanly, and `h11-vat-error` must fail only the tax check.
- `samples/holdout/invoices/`: French, Spanish, Hungarian, Italian, US (comma thousands), UK (dd/mm, day ≤ 12), two-column with totals at the top, banner + logo, two pages with carried-forward rows, odd labels, VAT error, and a customer name containing a comma.
- `samples/holdout/photos/`: phone shots of h03, h06, h09 (2 pages) and h11, with perspective, rotation, uneven light, a shadow band, low resolution and JPEG. They have no text layer (checked with pdftotext).
- `samples/holdout/README.md`: what each invoice tests and how to score it.
- `scripts/score.py`: new optional second argument for the expected folder. The default is still `samples/expected`.

## Verified
- `uv run python scripts/score.py samples/holdout/expected samples/holdout/expected` → 192/192 (100.0%).
- The default call on the original set is unchanged: 80/80.
- `uv run pytest` → 13 passed.
- Every vendor, customer, invoice number, tax ID and line description is in its PDF's text layer. The one exception is h05, where the vendor is printed in capitals; the scorer compares case-insensitively.

## Things to know
- `docs/bakeoff.md` still says "Do not edit scripts/score.py". The change was requested and is backward compatible, but the brief may need a line about the holdout set and the new argument.
- Judgement calls in the expected answers: h03 `line_total` is the net column (the gross column is a decoy); h05 `vendor_tax_id` is null (only a licence number is printed); h11 holds the figures as printed (tax 386.90, total 2226.90).
- Regenerating needs `pdftoppm` and DejaVu Sans. Photo noise is not seeded, so regenerated photos differ pixel by pixel.
