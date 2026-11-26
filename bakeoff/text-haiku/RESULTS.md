# Bake-off: text-haiku

This is the cheapest Claude route. Text is extracted on the machine. pdfplumber reads the text layer, and tesseract 5.5.4 OCRs pages with no text layer (rendered at 300 dpi in grey, `--psm 6`). Only that plain text goes to `claude-haiku-5-5`, never the PDF. The output is the repo's `Invoice` schema as structured output (`client.messages.parse`, effort `medium`). The system prompt is the repo's, plus a short section on extracted text and OCR misreads.

Code: `src/claude_invoice_parser/text_haiku.py`. The existing pipeline is unchanged.
Run: `uv run --group bakeoff python -m claude_invoice_parser.text_haiku samples/invoices bakeoff/text-haiku/clean`, and the same for `samples/scanned` → `bakeoff/text-haiku/scan`.
Raw numbers per document: `metrics-clean.json`, `metrics-scan.json`.

## 1. Score

| Set | `score.py` |
|---|---|
| clean (text layer) | **80/80 fields correct (100.0%)** |
| scan (OCR) | **80/80 fields correct (100.0%)** |

`score.py` found no misses. It doesn't check line descriptions, quantities, unit prices, `bank_name` or `notes`. I compared those with `samples/expected` by hand, and they contain these errors:

| Set | Document | Field | Got | Expected | Cause |
|---|---|---|---|---|---|
| clean | 05-math-error | line 1 description / quantity | `Monthly bookkeeping, October 1` / `null` | `Monthly bookkeeping, October` / `1` | pdfplumber's text joins the quantity column onto the description, so the model can't separate them |
| scan | 05-math-error | line 1 description / quantity | same as clean | same | same |
| scan | 02-eu-vat | line 2 description | `Ersatzlifter 120 mm` | `Ersatzlüfter 120 mm` | OCR misread (ü → i) |
| scan | 03-freelancer-text | line description | `Licensed stock image stttseetesseeessesersseserseesreseeeerse` | `Licensed stock image` | OCR read the dotted leader as letters. The model mentioned the garbled text in `notes`. The amount is correct. |
| scan | 04-uk-discount | `payment.bank_name` | `Demo Bank ple` | `Demo Bank plc` | OCR misread (c → e) |
| clean/scan | 03-freelancer-text | `notes` | adds "Payment terms: within 14 days" | reverse-charge note only | wording only. The scan's note also contains the OCR typo `2006/1 12/EC`. |

The scans have no errors in tax IDs, IBANs, account numbers or amounts, even though raw tesseract output got them wrong. On `02-eu-vat-scan`, tesseract printed `DEQ00000001` and `DEO0 0000 …`. Haiku corrected them to `DE000000001` and `DE00000000000000000000`, following the prompt rule: correct O/Q/D → 0 only where the field's format leaves no doubt. I didn't tune the OCR settings to the scores. 400 dpi happened to fix one ID in a quick check, but I kept the untuned 300 dpi so as not to overfit to five documents.

## 2. Was `05-math-error` flagged?

**Yes, on both sets.** `validate_invoice` returned the same two issues for each:
- `line items add up to 1030.0, but subtotal is 1130.0` (the real arithmetic error)
- `no bank account or IBAN found` (this invoice prints no bank details, so this check would flag it on its own)

The model copied the printed figures without "fixing" them, as the prompt says. On the scan, it also described the mismatch in `notes`. The other 8 documents passed the validator with no issues.

## 3. Cost

Prices assumed: **Claude Haiku 5.5 list price, $0.10 per million input tokens and $0.50 per million output tokens** (prompts ≤ 100K tokens; Anthropic first-party API pricing as of 2026-11-03). Every prompt here is about 3K tokens. Output tokens include adaptive thinking.

| Document | clean in / out | clean $ | scan in / out | scan $ |
|---|---|---|---|---|
| 01-us-table | 3,017 / 762 | 0.000683 | 3,006 / 775 | 0.000688 |
| 02-eu-vat | 3,090 / 881 | 0.000749 | 3,070 / 1,667 | 0.001141 |
| 03-freelancer-text | 2,982 / 1,149 | 0.000873 | 3,000 / 1,504 | 0.001052 |
| 04-uk-discount | 3,003 / 735 | 0.000668 | 3,003 / 1,135 | 0.000868 |
| 05-math-error | 2,927 / 782 | 0.000684 | 2,924 / 1,394 | 0.000989 |
| **Total** | 15,019 / 4,309 | **$0.0037** | 15,003 / 6,475 | **$0.0047** |

All 10 documents cost **$0.0084**, about $0.0008 each, or roughly $0.84 per 1,000 invoices. Most of the ~3K input tokens are the schema and system prompt, not the invoice. Scans use more output tokens because the model spends more thinking on noisy text.

## 4. Wall-clock per document

The run was sequential on the sandbox, so times include network latency.

| Document | clean: extract + API = total (s) | scan: OCR + API = total (s) |
|---|---|---|
| 01-us-table | 0.02 + 5.07 = 5.09 | 1.52 + 4.39 = 5.91 |
| 02-eu-vat | 0.03 + 4.34 = 4.36 | 1.45 + 6.96 = 8.42 |
| 03-freelancer-text | 0.02 + 5.32 = 5.33 | 1.55 + 6.67 = 8.22 |
| 04-uk-discount | 0.02 + 3.34 = 3.35 | 1.63 + 4.88 = 6.52 |
| 05-math-error | 0.02 + 4.43 = 4.44 | 1.15 + 6.09 = 7.24 |
| **Mean** | **4.5 s** | **7.3 s** |

## 5. What broke, what I'd change, when to pick it

**What broke**
- In this sandbox the API key arrived as `INVOICE_ANTHROPIC_KEY`, not `ANTHROPIC_API_KEY`. It had to be exported for the scripts only.
- Converting to text loses the layout. Table columns get merged, which lost the quantity on 05 even with a clean text layer. The PDF-input pipeline doesn't have this problem, because the model sees the page.
- OCR noise reaches free-text fields such as descriptions, bank names and notes. None of the scored fields were affected, but a bookkeeper would see `Demo Bank ple` and the garbled stock-image line.
- The 100% score covers only 16 fields per invoice on 5 synthetic invoices. It shows the route works, not that it's as accurate as the vision route on messy real invoices.

**What I'd change**
- Use `pdfplumber`'s `extract_words`/table extraction, or `layout=True`, to keep columns apart. The quantity column should then survive.
- Have the validator check the whole IBAN (mod-97 checksum) and the format of each tax ID. If OCR plus the model "corrects" a digit wrongly, it would then be caught. The format regex alone can't catch that.
- If a document fails validation, send it again as the PDF or page image to a vision model, instead of straight to a human.
- Try effort `low` to save output tokens, and cache the system prompt and schema to cut input cost at volume. That needs a check that accuracy holds.

**When a client should pick this**
- Large volume of fairly clean invoices with a real text layer, or decent scans, where cost per document matters most. It costs about a tenth of a cent each, and the PDF itself never leaves the machine.
- Clients who don't want the document image sent to an API. Only extracted text is sent.
- Not for layout-heavy, handwritten or very poor scans, or where descriptions and quantities must be exact. Use the PDF/vision route there, or as the fallback for anything the validator flags.
