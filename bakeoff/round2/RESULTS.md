# Bake-off round 2: held-out set

All three round-1 approaches were run **unchanged** on `samples/holdout`: 12 text-layer PDFs and 4 image-only phone photos. None of them had seen these invoices before. Each approach ran once per document, on 26 November 2026, with no retries and no re-runs.

## Summary

| Approach | Text score (12 docs) | Photo score (4 docs) | Crashes / no output | h11 VAT error flagged | False flags | Cost (16 docs) | Time per doc, text / photo |
|---|---|---|---|---|---|---|---|
| **rules** (no LLM) | 108/192 (56.2%) | 27/64 (42.2%) | 0 | **No** (text and photo). Both get `needs_review`, but only for the extractor's own errors: tax read as 0, IBAN missing. The real 386.40 vs 386.90 error is never raised. | 0 | $0 | 0.05 s / 10.6 s |
| **vision** (Opus 5.5, PDF in) | **188/192 (97.9%)** | **63/64 (98.4%)** | 0 | **Yes**, on text and photo, with exactly the expected issue | 0 | $0.551 (3.4 ¢/doc) | 7.1 s / 8.6 s |
| **text-haiku** (local text/OCR, Haiku 5.5) | **188/192 (97.9%)** | 52/64 (81.2%) | 0 | **Yes**, on text and photo, with exactly the expected issue | 0 | $0.018 (0.11 ¢/doc) | 5.1 s / 14.4 s |

How to read the columns:
- **Score** is `scripts/score.py`: 16 fields per invoice. The photo score uses `expected-photo/`, which holds the 4 matching answers.
- **h11 flagged** means the repo validator returned `21.0% of 1840.0 is 386.4, but tax amount is 386.9`.
- **False flags** counts outputs that were fully correct (16/16) but still flagged. There were none. Every flag except h11's real one was caused by a real extraction error, so every flag pointed at something worth checking.
- **The flip side is silent errors:** outputs that passed the validator with wrong fields in them. The validator only checks arithmetic, dates, currency format and whether a bank account is present. It never checks names or tax IDs, and checks IBANs only by a loose format regex.
  - rules: 1 document (h05). The other 10 non-h11 text outputs and all 3 non-h11 photos were flagged, so a person would review nearly every document.
  - vision: 4 text, 1 photo.
  - text-haiku: 3 text, 2 photo. h11-photo is flagged for the VAT error, but its name and tax-ID errors would not be noticed.
- **Cost** uses Opus 5.5 at $4 / $20 per million tokens (in/out) and Haiku 5.5 at $0.10 / $0.50, from the `usage` in each API response. Per-document breakdowns are below.
- **Time** is the mean per document as measured by each approach's own timer. That covers extract + API for text-haiku, the `extract_invoice()` call for vision, and render + OCR + rules for rules. Runs were sequential and include network latency.
  - Whole-folder wall-clock including `uv` start-up, text / photo: rules 4.3 s / 43.0 s, vision 89.7 s / 37.0 s, text-haiku 64.0 s / 59.1 s (in `logs/`).

## Every miss, by approach

### rules: 84 text misses, 37 photo misses

Text-layer PDFs (in `rules/text/`):

| Doc | Misses |
|---|---|
| h01-fr-tva (9/16) | vendor_name `Atelier Lumière Bleue SARL FACTURE` (title glued on); vendor_tax_id null (SIRET); invoice_number `12` (expected `F-2026-1103`); issue_date null; due_date null; subtotal null; total `336.8` (expected 1336.8, the space thousands separator cut the number) |
| h02-es-iva (9/16) | customer_name `e`; invoice_number `''`; issue_date null; due_date null (only "30 días"); subtotal null; IBAN `ES00…0000BIC` (label glued on); line totals included the subtotal 1319.4 as a 5th item |
| h03-hu-afa (2/16) | vendor_name `SZÁMLA`; vendor_tax_id null; customer_name null; invoice_number `''`; issue_date null; due_date null; currency `USD` (expected HUF); subtotal null; tax_rate null; tax_amount null; total `0.0`; IBAN `HU00…0001SWIFT`; account_number null; no line items |
| h04-it-iva (8/16) | vendor_tax_id null; customer_name null; invoice_number `''`; issue_date null; due_date null; subtotal null; total `451.22` (the VAT amount, expected 2502.22); line totals `[2051.0]` (the subtotal, not the 4 items) |
| h05-us-commas (15/16) | vendor_name `INVOICE`. **Passed the validator.** |
| h06-uk-ddmm (12/16) | vendor_name `Fernhollow Facilities Ltd VAT INVOICE`; customer_name null; subtotal null; no line items. The dates were right. |
| h07-two-column-totals-top (9/16) | vendor_name `Invoice`; vendor_tax_id `IE0000001` (trailing `T` lost); issue_date null; due_date null; subtotal null; IBAN null; line totals `[1561.0]` (the subtotal) |
| h08-banner-logo (11/16) | vendor_name `TAX INVOICE`; customer_name `7 Dune Road`; currency `USD` (expected AUD); routing (BSB) null; no line items |
| h09-two-page (10/16) | vendor_tax_id null; customer_name `no. 10077 Seeweg 2`; due_date `2026-11-05` (expected 2026-12-03); subtotal null; total `642.61` (expected 2642.61, the apostrophe thousands separator cut the number); line items stop at page 1 and add the "Carried forward" row `924.2` as an item |
| h10-odd-labels (6/16) | vendor_name `STATEMENT OF WORK COMPLETED / TAX INVOICE`; vendor_tax_id null; customer_name null; invoice_number `''`; issue_date null; due_date null; currency `USD` (expected NZD); subtotal null; total `849.96` (the GST amount); no line items |
| h11-vat-error (5/16) | vendor_name `FACTUUR`; vendor_tax_id null; customer_name null; invoice_number `''`; due_date null; subtotal null; tax_rate null; tax_amount null; total `0.0`; IBAN null; line totals include subtotal, VAT and total as items. With tax_amount null, the real VAT error cannot be seen. |
| h12-comma-customer (12/16) | vendor_tax_id null; customer_name `Invoice No. LSI-55102`; currency `USD` (expected CAD); no line items |

Photos (in `rules/photo/`, OCR):

| Doc | Misses |
|---|---|
| h03-hu-afa (2/16) | the same 14 fields as the text version. vendor_name `Sorszam: DK-2026/0517`; IBAN `HU000000000000000001SWIFT` (too short and label glued on) |
| h06-uk-ddmm (12/16) | vendor_name `; I`; customer_name null; subtotal null; no line items |
| h09-two-page (8/16) | vendor_name `Alpenrand Laborbedart AG Invoice AL-2026-1190`; vendor_tax_id null; customer_name `no 10077 Seeweg 2`; due_date `2026-11-05`; subtotal null; total `642.61`; IBAN null; line items stop at page 1 and add the carried-forward row `1924.2` |
| h11-vat-error (5/16) | vendor_name `Polderwind Inst: niek B.V. FACTUUR`; the other 10 misses are the same as the text version |

In short, the rules were fitted to 5 known invoices and do not carry over. They fail on non-English labels, on totals using space or apostrophe thousands separators, on logos or banners printed above the vendor name, on currency stated only as `$` (it defaults to USD), and on items continuing to page 2. They did not crash on any document.

### vision: 4 text misses, 1 photo miss

| Set | Doc | Field | Got | Expected | Validator |
|---|---|---|---|---|---|
| text | h01-fr-tva | vendor_tax_id | null | `000 000 001 00012` (SIRET, the only ID printed) | passed |
| text | h02-es-iva | payment.iban | `ES000000000000000000000000` (26 chars) | `ES0000000000000000000000` (24) | passed |
| text | h08-banner-logo | vendor_tax_id | `ABN 00 000 000 001` | `00 000 000 001` (the label was kept) | passed |
| text | h09-two-page | payment.iban | `CH000000000000000000001` (23) | `CH0000000000000000001` (21) | passed |
| photo | h09-two-page | payment.iban | `CH00000000000000000001` (22) | `CH0000000000000000001` (21) | passed |

Three of the five misses are miscounted zeros in the fictional all-zero IBANs. Real IBANs aren't long runs of zeros, so this test is probably harsher than real data. But a wrong IBAN is the most costly error in the table, and the validator let all three through. It checks only `^[A-Z]{2}\d{2}[A-Z0-9]{8,30}$`, not the length for each country or mod-97. The ABN miss is a formatting difference: the number itself is right.

### text-haiku: 4 text misses, 12 photo misses

| Set | Doc | Field | Got | Expected | Validator |
|---|---|---|---|---|---|
| text | h01-fr-tva | vendor_tax_id | null | `000 000 001 00012` | passed |
| text | h04-it-iva | payment.iban | `IT00X00000000000000000000000` (28) | `IT00X0000000000000000000000` (27) | passed |
| text | h08-banner-logo | vendor_tax_id | `ABN 00 000 000 001` | `00 000 000 001` | passed |
| text | h08-banner-logo | payment.routing_or_sort_code | `BSB 000-002` | `000-002` | passed |
| photo | h03-hu-afa | vendor_name | `Dunakavics informatikal Kft.` | `Dunakavics Informatikai Kft.` | flagged (issue date missing) |
| photo | h03-hu-afa | customer_name | `Gyongyvirég Fogaszati Bt.` | `Gyöngyvirág Fogászati Bt.` | ″ |
| photo | h03-hu-afa | issue_date | null | `2026-11-03` | ″ |
| photo | h03-hu-afa | due_date | null | `2026-11-18` | ″ |
| photo | h03-hu-afa | payment.iban | `HU000000900000000001` (20, with a stray 9) | `HU00000000000000000000000001` (28) | ″ |
| photo | h03-hu-afa | payment.account_number | `00-5000000-00000001` | `00000000-00000000-00000001` | ″ |
| photo | h06-uk-ddmm | vendor_tax_id | `GB0000000002` | `GB000000002` (an extra 0) | passed |
| photo | h09-two-page | due_date | null | `2026-12-03` | flagged (no bank account) |
| photo | h09-two-page | payment.iban | null | `CH0000000000000000001` | ″ |
| photo | h11-vat-error | vendor_name | `Polderwind Inst: niek B.V.` | `Polderwind Installatietechniek B.V.` | flagged (VAT error only) |
| photo | h11-vat-error | vendor_tax_id | null | `NL000000001B01` | ″ |
| photo | h11-vat-error | customer_name | `Huisartsenpraktijk De lav. de praktijkmanag` | `Huisartsenpraktijk De Linde` | ″ |

On the text-layer PDFs, text-haiku matches vision exactly (188/192). On photos it drops to 81%. Each photo miss comes from tesseract reading the photo text wrongly, and the model then passes the mistakes on: mangled Hungarian accents and dates, a garbled IBAN and account number, a lost tax ID. All amounts and line totals were still correct on every photo, which is why h11's VAT error was still caught.

## Cost and tokens per document

| Doc | vision text: in / out / $ | vision photo: in / out / $ | text-haiku text: in / out / $ | text-haiku photo: in / out / $ |
|---|---|---|---|---|
| h01-fr-tva | 4,520 / 723 / 0.0325 | | 3,124 / 1,309 / 0.00097 | |
| h02-es-iva | 4,525 / 623 / 0.0306 | | 3,130 / 1,196 / 0.00091 | |
| h03-hu-afa | 4,718 / 730 / 0.0335 | 4,098 / 888 / 0.0342 | 3,322 / 1,054 / 0.00086 | 3,303 / 2,671 / 0.00167 |
| h04-it-iva | 4,549 / 466 / 0.0275 | | 3,155 / 1,549 / 0.00109 | |
| h05-us-commas | 4,520 / 552 / 0.0291 | | 3,146 / 777 / 0.00070 | |
| h06-uk-ddmm | 4,489 / 398 / 0.0259 | 4,098 / 398 / 0.0244 | 3,093 / 846 / 0.00073 | 3,116 / 2,050 / 0.00134 |
| h07-two-column-totals-top | 4,492 / 432 / 0.0266 | | 3,095 / 1,233 / 0.00093 | |
| h08-banner-logo | 4,489 / 426 / 0.0265 | | 3,093 / 1,088 / 0.00085 | |
| h09-two-page | 6,998 / 2,601 / 0.0800 | 5,651 / 2,127 / 0.0651 | 4,037 / 3,067 / 0.00194 | 3,879 / 4,333 / 0.00255 |
| h10-odd-labels | 4,500 / 424 / 0.0265 | | 3,106 / 873 / 0.00075 | |
| h11-vat-error | 4,589 / 639 / 0.0311 | 4,098 / 717 / 0.0307 | 3,192 / 995 / 0.00082 | 3,123 / 1,666 / 0.00115 |
| h12-comma-customer | 4,485 / 434 / 0.0266 | | 3,109 / 713 / 0.00067 | |
| **Total** | 56,874 / 8,448 / **$0.397** | 17,945 / 4,130 / **$0.154** | 38,602 / 14,700 / **$0.0112** | 13,421 / 10,720 / **$0.0067** |

Every vision response was served by `claude-opus-5-5`, so the fallback model never ran. Vision costs about 30× as much as text-haiku per document. The two-page h09 is the most expensive document for both approaches: 8 ¢ and 29 s for vision.

Per-document times are in `vision/{text,photo}/metrics.json`, `text-haiku/metrics-{text,photo}.json` and `logs/rules-*.log`.

## Verdict for a small business

- **Use vision (Opus 5.5) if you can only run one approach.** It was the only one that stayed at ~98% on both clean PDFs and phone photos, it caught the VAT error both times, and it needs no OCR install. At about 3–4 cents and 5–10 seconds per invoice, it costs a business handling a few hundred invoices a month roughly $10–15.
- **Use text-haiku when most invoices are real digital PDFs (emailed from accounting software) and volume or privacy matters.** On those it was exactly as accurate as vision for about a thirtieth of the price (~0.1 ¢), and the PDF never leaves your machine. Don't trust it on phone photos: it scored 81% there and silently got names and tax IDs wrong. A sensible setup is text-haiku for text-layer PDFs, sending image-only files and anything the validator flags to vision.
- **Don't use rules for an open inbox.** It scored 56% on text and 42% on photos for invoices it hadn't been tuned on, and missed the VAT error. It only "caught" problems because it broke so badly that nearly every document was flagged. It's only worth considering for a few fixed vendors whose layouts you write templates for.
- **Whichever you choose, a person still has to check IBANs and tax IDs.** All 5 vision misses, all 4 of text-haiku's text misses and several of its photo misses passed the validator. 6 of them were wrong IBANs or tax IDs. Adding an IBAN length and mod-97 check to the validator is the cheapest improvement left, but it is outside this frozen round.

## How it was run

- `run_all.sh` symlinks the photos under their original names (dropping `-photo`) into a temporary folder, because the frozen scripts strip only `-scan`. It copies the 4 matching answers into `expected-photo/`, then runs each approach's own entry point (`bakeoff/rules/extract_rules.py`, `bakeoff/vision/run.py`, `python -m claude_invoice_parser.text_haiku`) unchanged.
- `ANTHROPIC_API_KEY` is set from `$INVOICE_ANTHROPIC_KEY` only for the vision and text-haiku runs.
- tesseract 5.5.4 (`tesseract-ocr`, `tesseract-ocr-deu`) was installed with apt, as in round 1. It is the same version.
- Raw console output is in `logs/`.
- `analyse.py` runs the scorer's `score_one` and the repo validator on every output and adds up the metrics files. It produced the flag, silent-error and cost columns above.

```sh
eval "$(discobox-access env)"
bash bakeoff/round2/run_all.sh            # or: run_all.sh rules | vision | text-haiku
uv run python scripts/score.py bakeoff/round2/<approach>/text  samples/holdout/expected
uv run python scripts/score.py bakeoff/round2/<approach>/photo bakeoff/round2/expected-photo
uv run python bakeoff/rules/validate_outputs.py bakeoff/round2/*/text bakeoff/round2/*/photo
uv run python bakeoff/round2/analyse.py
```

No existing `.py` file, prompt, regex, model or setting was changed This commit only adds files under `bakeoff/round2/`; `git diff 18ea1f1 HEAD -- src scripts bakeoff/rules bakeoff/vision bakeoff/text-haiku` is empty.
