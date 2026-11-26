# Held-out invoice set

Twelve **fictional** invoices for testing the bake-off extractors on layouts they were never developed on. Every company, person, address, tax number and bank detail is invented. IBANs and tax IDs are dummies with fake check digits. Every page also carries a "FICTIONAL SAMPLE" footer.

## Layout

| Path | What |
|---|---|
| `generate_holdout.py` | The single source of truth: one dict per invoice. It writes the PDFs, the photos and `expected/*.json` from that same data. Expected answers are never read back from the PDFs. |
| `invoices/<name>.pdf` | Text-layer PDFs |
| `expected/<name>.json` | Expected extraction, same shape as `samples/expected/*.json` (`Invoice` in `src/claude_invoice_parser/schema.py`) |
| `photos/<name>-photo.pdf` | Image-only "phone photos" of 4 invoices, with no text layer. They have the same expected answers as the originals. |

Regenerate with `uv run python samples/holdout/generate_holdout.py`. The photos need `pdftoppm` (poppler-utils), and the Hungarian invoice needs DejaVu Sans for ő/ű. Before writing, the generator runs the repo's validator on each invoice's data. It stops unless every invoice passes cleanly, except `h11`, which must fail exactly the tax check. The photo noise is not seeded, so regenerated photos differ in their pixels but not in their content.

## Scoring

```bash
uv run python scripts/score.py bakeoff/<approach>/holdout       samples/holdout/expected
uv run python scripts/score.py bakeoff/<approach>/holdout-photo samples/holdout/expected
```

Name the output JSON files after the original invoice: drop `-photo`, as you would drop `-scan` for the scans. The scorer compares 16 fields per invoice: 11 scalars, 4 payment fields and the list of line totals. Strings are compared case-insensitively with spaces removed. `bank_name`, line descriptions, quantities, unit prices and `notes` are in the JSON but are not scored.

## The invoices

| Name | Photo | What makes it hard |
|---|---|---|
| `h01-fr-tva` | | French. TVA 20 %, a SIRET (`000 000 001 00012`) as the only tax ID, dates written as `3 novembre 2026`, space thousands with comma decimals (`1 336,80 €`), a fractional quantity (`3,5`) and a serif font. |
| `h02-es-iva` | | Spanish. IVA 21 %, `NIF: B00000001`, dot thousands (`1.596,47 €`), `dd/mm/yyyy`. The due date is printed only as "30 días fecha factura" and must be computed (2026-11-14). The customer's own NIF is printed too; it is a decoy for `vendor_tax_id`. |
| `h03-hu-afa` | ✓ | Hungarian. HUF with no decimals and space thousands (`1 135 380 Ft`), 27 % ÁFA, adószám `00000001-2-41`. There are three dates (`kelte` = issue, `teljesítés` = fulfilment, a decoy, and `határidő` = due) in `2026. november 3.` format. Lines show net, ÁFA and gross columns; `line_total` is the **net** value, because that is what sums to the subtotal. Both the Hungarian account number and the IBAN are expected. The customer's adószám is a decoy. |
| `h04-it-iva` | | Italian. IVA 22 %, `Partita IVA: IT00000000001`, the vendor block is right-aligned while the customer sits top left, `dd/mm/yyyy`. The invoice number (`457/2026`) appears only inside the title line "FATTURA n. 457/2026 del 07/10/2026". A per-line "IVA %" column is a decoy for quantity or amount. |
| `h05-us-commas` | | US Letter. Comma thousands (`$14,709.01`), `Nov 3, 2026` dates, 8.25 % sales tax, vendor name printed in capitals. Only a *contractor licence number* is printed, so `vendor_tax_id` is **null**. |
| `h06-uk-ddmm` | ✓ | UK. Every date is `dd/mm/yyyy` with day ≤ 12 (`04/11/2026` is 4 November and `02/12/2026` is 2 December), so swapping day and month still gives a valid date. Also has a "Tax point" and a service period as extra dates, and area as the quantity (`420` m² × £1.20). |
| `h07-two-column-totals-top` | | Irish, VAT 23 %. Two-column layout: a tinted left sidebar holds the vendor, customer, invoice number and bank, while the right column opens with a big **AMOUNT DUE** box and the net, VAT and total summary *before* the line items. |
| `h08-banner-logo` | | Australian. A full-width **TAX INVOICE** banner, then a logo with a big brand word **HELIX** and a tagline, all before the legal vendor name `Helix Fieldworks Pty Ltd`. Amounts use a bare `$` (currency is AUD, stated once). GST 10 %, ABN, BSB as the routing code, due date only as "Terms: 14 days". |
| `h09-two-page` | ✓ | Swiss, CHF with apostrophe thousands (`2'642.61`), VAT 8.1 %, `dd.mm.yyyy`. 30 line items: 22 on page 1 and 8 on page 2. The "Carried forward" / "Brought forward" rows (`1'924.20`) are **not** line items. Totals and bank details appear only on page 2. Due date only as "payable within 30 days". |
| `h10-odd-labels` | | New Zealand, in a monospace font, with labels nobody would guess: "Prepared by" (vendor), "Invoiced party" (customer), "Document reference", "Raised", "Settle by", "Particulars / Count / Each / Extended", "Value before GST", "GST component @ 15%", "Amount payable" (NZ$). The bank account is a single NZ-format number with no routing code. |
| `h11-vat-error` | ✓ | Dutch. BTW 21 %. **Deliberate vendor error:** 21 % of €1.840,00 is €386,40 but the invoice prints **€386,90**. Everything else is consistent (the total is net plus the printed tax), so `validate.py` must flag exactly one issue: `21.0% of 1840.0 is 386.4, but tax amount is 386.9`. The expected JSON holds the figures *as printed*. Also has a KvK number next to the BTW-id (decoy) and Dutch month names. |
| `h12-comma-customer` | | Canadian. The customer is `Halloran, Pike & Co`, with a comma and an ampersand, which tests naive splitting and CSV output. GST 5 %, a GST/HST registration number, due date only as "Net 15", `$` amounts in CAD. |

## Phone photos

`photos/` holds hand-held phone shots, not flatbed scans. Each page is rendered at 110 dpi in colour, placed on a textured desk with a soft drop shadow, and given a perspective warp (the top edge is further away, so narrower) plus up to ±3.2° of rotation. On top of that come uneven lighting from one corner, a soft diagonal shadow band, a warm tint, slight defocus and sensor noise, and JPEG compression at quality 55. The JPEG is embedded in the PDF as-is, with no text layer (`pdftotext` returns nothing). The photographed invoices are `h03` (space-separated HUF), `h06` (day/month order), `h09` (both pages) and `h11` (the VAT error must still be read exactly to be flagged).

## Verification

`uv run python scripts/score.py samples/holdout/expected samples/holdout/expected` gives `192/192 fields correct (100.0%)`. Running the validator over `expected/` passes 11 invoices and flags only `h11-vat-error`.
