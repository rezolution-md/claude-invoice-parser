# Bake-off: "vision" (baseline)

The repo's existing pipeline, unchanged: each PDF is sent as a `document` block to
`claude-opus-5-5` (effort `medium`, the default), with the `Invoice` model as a strict
structured-output schema and the existing system prompt. No OCR, no preprocessing.
`run.py` in this folder only calls `extract_invoice()` and records each response's
`usage`, the model that served it, and wall-clock time; per-document numbers are in
`clean/metrics.json` and `scan/metrics.json`.

Run on 26 November 2026, once per document (no retries, no cherry-picking).

## 1. Score (`scripts/score.py`)

| Set | Fields correct |
|---|---|
| Clean (`samples/invoices`) | **80 / 80** (100.0%) |
| Scan (`samples/scanned`) | **80 / 80** (100.0%) |

Misses: none on either set.

Unscored fields: line-item descriptions, quantities and unit prices are identical
between the clean and scan output for all five invoices. Only the free-text `notes`
field differs (rewording). On `02-eu-vat`, the scan run also added a note that the bank
details look like placeholders: the IBAN is all zeros and the BIC is `DEMODEXXX`. That
is true of the fictional sample. The clean run did not add it.

## 2. `05-math-error` flagged?

Yes, on both sets. `validate.py` marked it `needs_review` with:

- `line items add up to 1030.0, but subtotal is 1130.0`
- `no bank account or IBAN found`

The model copied the wrong subtotal (1130.0) as printed instead of correcting it, which
is what lets the validator catch it. The other four invoices are `ok` on both sets.

## 3. Cost

Price used: **$4.00 per million input tokens, $20.00 per million output tokens**. This is
the standard first-party rate for `claude-opus-5-5`, from the model table in Claude Code's
built-in Claude API reference (cached 2026-11-03). I did not check it against the live
pricing page, because the bake-off rules allow no traffic except to api.anthropic.com.
No prompt caching, batching or fast mode. Every response was served by `claude-opus-5-5`,
so the backup model never ran. Output tokens include the model's (hidden) thinking at
effort `medium`.

| Document | Clean in | Clean out | Clean $ | Scan in | Scan out | Scan $ |
|---|---:|---:|---:|---:|---:|---:|
| 01-us-table | 4,390 | 352 | 0.0246 | 4,108 | 352 | 0.0235 |
| 02-eu-vat | 4,484 | 369 | 0.0253 | 4,132 | 622 | 0.0290 |
| 03-freelancer-text | 4,376 | 642 | 0.0303 | 4,132 | 640 | 0.0293 |
| 04-uk-discount | 4,397 | 448 | 0.0265 | 4,119 | 449 | 0.0255 |
| 05-math-error | 4,300 | 385 | 0.0249 | 4,108 | 379 | 0.0240 |
| **Total** | **21,947** | **2,196** | **$0.1317** | **20,599** | **2,442** | **$0.1312** |

All 10 documents: 42,546 in, 4,638 out, **$0.263** (about 2.6 cents per invoice).

Scans cost slightly *less* input than the originals (about 4,100 vs 4,400 tokens). A PDF
with a text layer is sent as extracted text plus a page image; an image-only scan has no
text to extract, so only the image counts.

## 4. Wall-clock per document

The time for one API call, measured around `extract_invoice()` (encoding, request, parse).
It includes network round-trip from this sandbox.

| Document | Clean (s) | Scan (s) |
|---|---:|---:|
| 01-us-table | 6.2 | 4.2 |
| 02-eu-vat | 3.9 | 5.9 |
| 03-freelancer-text | 5.7 | 6.2 |
| 04-uk-discount | 4.4 | 4.5 |
| 05-math-error | 3.8 | 3.6 |
| **Total / mean** | 24.0 / 4.8 | 24.4 / 4.9 |

Single run; expect a second or two of variation between runs.

## 5. What broke, what I'd change, when to pick this

**What broke:** nothing in the extraction. The only problem was setup: the harness keeps
`ANTHROPIC_API_KEY` for itself, so the run used `INVOICE_ANTHROPIC_KEY`, exported as
`ANTHROPIC_API_KEY` only for the invoice script.

**What I'd change (none of it tested here, since this is the baseline):**
- Five invoices is a small sample, and these scans are mild (130 dpi, slight rotation).
  Before quoting accuracy to a client, test harder scans: phone photos, low contrast,
  stamps over figures, multi-page invoices.
- `extract.py` uses the deprecated `output_format=` parameter. It works today; move it
  into `output_config.format` when the prompt and model are next allowed to change.
- For backlogs, the Message Batches API halves the token price. Effort `low` is worth
  measuring against this same scorer.
- `notes` wording changes from run to run, so don't build downstream logic on it.

**When a client should pick this approach:** when invoices arrive as a mix of digital
PDFs and scans, and the volume makes about 2.5 cents per invoice and about 5 seconds per
call acceptable. It needs no OCR stack, and on this set the scans lost no accuracy. Pick
something else if documents may not leave the client's machines (each PDF goes to
api.anthropic.com), or if the volume is so high that per-call API cost dominates.
