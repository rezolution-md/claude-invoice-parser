Box handover (handover-rules skill v1)

# bakeoff/text-haiku

Approach: text is extracted on the machine (pdfplumber for the text layer, tesseract OCR for image-only pages). Only that text goes to `claude-haiku-5-5`, with the repo's `Invoice` schema as structured output. The PDF is never sent.

- Code: `src/claude_invoice_parser/text_haiku.py`. The existing pipeline is unchanged. The new dependencies (`pdfplumber`, `pytesseract`, `pdf2image`) are in a separate `bakeoff` dependency group in `pyproject.toml`. System packages from apt: `tesseract-ocr`, `poppler-utils`.
- Full report: `bakeoff/text-haiku/RESULTS.md`.
- Results: clean 80/80 and scan 80/80 on `score.py`. `05-math-error` was flagged by `validate.py` on both sets (line items 1030 vs subtotal 1130).
- Cost: $0.0084 for all 10 documents. Prices assumed: Haiku 5.5 at $0.10 per million input tokens and $0.50 per million output tokens.
- Mean wall-clock: 4.5 s per clean document, 7.3 s per scan.
- Misses `score.py` doesn't check: on 05 the line-1 quantity was merged into the description (both sets), and OCR misread three free-text fields on the scans ("Ersatzlifter", "Demo Bank ple", a garbled stock-image description). Details are in RESULTS.md.

Running it again: the key is delivered as `INVOICE_ANTHROPIC_KEY`. Run `eval "$(discobox-access env)"; export ANTHROPIC_API_KEY="$INVOICE_ANTHROPIC_KEY"` before the scripts, then:
`uv run --group bakeoff python -m claude_invoice_parser.text_haiku samples/invoices bakeoff/text-haiku/clean`
`uv run --group bakeoff python -m claude_invoice_parser.text_haiku samples/scanned bakeoff/text-haiku/scan`

Nothing was pushed.
