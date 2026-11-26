Box handover (handover-rules skill v1)

# bakeoff/rules

Task: the bake-off in `docs/bakeoff.md`, approach "rules" (no LLM, no API calls).

- Code: `bakeoff/rules/extract_rules.py` (pdfplumber for the text layer, tesseract OCR for the scans, then regexes)
- Outputs: `bakeoff/rules/clean/*.json`, `bakeoff/rules/scan/*.json`
- Report: `bakeoff/rules/RESULTS.md`; it has the reproduce commands
- Score: 80/80 clean, 80/80 scan. The rules were tuned on these same 5 invoices and there is no held-out set, so treat this as a best case. Changing the scan render from 300 dpi to 150 or 200 dpi already drops a field.
- `05-math-error` is flagged by `validate.py` (line items add up to 1030, but subtotal is 1130).
- Cost $0. About 0.03 s per text PDF and 3–8 s per scanned page.
- Setup: installed `tesseract-ocr` and `tesseract-ocr-deu` with apt. pdfplumber and pytesseract run through `uv run --with`, so `pyproject.toml` and `uv.lock` are unchanged.
- Nothing pushed.
