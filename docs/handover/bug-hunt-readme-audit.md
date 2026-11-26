Box handover (handover-rules skill v3)

# README check on a clean machine and one bug, proved with a failing test

Branch: `bug-hunt-readme-audit` (from `main` at `cb32559`). I fixed nothing. The only code change is a new test in `tests/test_report.py`.

## (a) README setup on a clean machine

Machine: Linux arm64. uv was already installed. The system Python is 3.14, and uv installed 3.12 itself from `.python-version`. There was no Anthropic key and no `ant` CLI.

| README step | Result |
|---|---|
| `uv sync` | Works. It installs the `dev` group by default, so pytest and reportlab are there. |
| `uv run python samples/generate_samples.py` | Runs, but it **overwrites the five PDFs that are already committed** in `samples/invoices/`. The bytes differ, probably because each PDF embeds a timestamp, so `git status` shows 5 modified files. The README doesn't say the PDFs are already in the repo or that this step dirties the tree. I restored them with `git checkout samples/invoices`. |
| `export ANTHROPIC_API_KEY=...  # or: ant auth login` | The **`ant` CLI is not a dependency and the README never says how to install it**, so `ant auth login` gives "command not found". I had no key, so I couldn't run the extraction step. This is a limit of this box, not a README fault. |
| `uv run invoice-parser samples/invoices` | With no credentials it prints "No Claude credentials found..." and exits 2. That's a clear message. It still creates an empty `output/json/` before failing. |
| `uv run python scripts/score.py` | With no output it prints "no output found" for all five invoices and **exits 0** with no overall score. A missing invoice is skipped, not counted as a miss, so if one invoice failed, the overall percentage would still look perfect. The README doesn't warn about this. |
| `uv run pytest` | **43 passed**, no key needed, as documented. |

The README never says that the bakeoff (`text_haiku`, `uv run --group bakeoff`) needs the system packages **tesseract** and **poppler** (for pdf2image). The README doesn't ask you to run it, so this blocks nothing.

## (b) The bug

**File:** `src/claude_invoice_parser/report.py`, line 79 (`invoices.append(...)`, which writes vendor, notes and the other text fields) and line 89 (`items.append(...)`, which writes line-item descriptions). The "Needs review" sheet at line 96 has the same flaw, because issue text quotes extracted values.

**What's wrong:** `write_xlsx` passes the extracted strings straight to openpyxl. openpyxl saves any string that starts with `=` as a **formula**, not as text. So text taken from an invoice (an outside, untrusted document, and the prompt says "copy exactly as printed") becomes a live formula in `invoices.xlsx`:

- An attacker's line description `=HYPERLINK("https://evil","Pay here")` shows up in the bookkeeper's report as a clickable link. This is spreadsheet formula injection, which the attack test in `samples/attacks/` doesn't cover.
- An honest description or note like `== Payment terms ==` becomes the broken formula `= Payment terms ==`. Excel shows an error or offers to repair the file, and the printed text is lost.

**How to trigger it:** pass a `Row` to `write_xlsx` where `invoice.line_items[0].description` (or `notes`) starts with `=`. In the saved sheet XML the cell is `<c r="A1"><f>HYPERLINK(...)</f><v /></c>`, a formula, not a string. I checked the raw XML directly.

`write_csv` writes the literal text, which is correct for a CSV. Escaping for spreadsheet apps that open the CSV would be a separate decision.

## (c) The failing test

`tests/test_report.py::test_text_starting_with_equals_is_written_as_text_not_formula` sets the first line description of `01-us-table` to `=HYPERLINK("https://example.invalid/pay","Pay here")` and the notes to `== Payment terms ==`. It writes the workbook, reloads it, and asserts that both cells hold the same text with `data_type == "s"`.

```
>       assert (description.value, description.data_type) == (payload, "s")
E       assert ('=HYPERLINK(... here")', 'f') == ('=HYPERLINK(... here")', 's')
E         At index 1 diff: 'f' != 's'
FAILED tests/test_report.py::test_text_starting_with_equals_is_written_as_text_not_formula
1 failed, 43 passed
```

It fails because of the bug: the value is kept, but its type is formula (`'f'`), not text (`'s'`). To check that it would pass once fixed, I ran it with a temporary patch that set string cells starting with `=` to `data_type = "s"` after each append. Both report tests then passed. The patch was applied only while the test ran and lived in the scratchpad, so the repo is unchanged.

A possible fix, not applied: after each `append`, set `cell.data_type = "s"` on any string cell that starts with `=`. Or write each cell with an explicit string type.

## (d) Confidence

**High** that this is a real defect. openpyxl's behaviour is documented and I reproduced it in the saved file XML. The project treats invoices as untrusted input and copies text from them verbatim. The result is wrong output: text turns into a formula or a broken cell, and an attacker can put a live link in the review spreadsheet.

Other things I looked at but didn't count as the bug, because each is a judgement call or less clear:
- `score.py` leaves missing outputs out of the overall percentage, so a failed invoice can't lower the score.
- `MIXED_SCRIPT_WORD` treats `\S*` as one word, so honest bilingual labels like `Фактура/Invoice` (common on Bulgarian and Cypriot invoices) would go to review.
- The `$` in `ISO_DATE`/`CURRENCY` lets a trailing newline through (`"EUR\n"` passes the currency check).
