# claude-invoice-parser

Turn PDF invoices into structured data with the Claude API, then check the arithmetic before anything reaches the books.

Most invoice extraction demos stop at "the model returned JSON". In bookkeeping that isn't enough: a misread digit or a vendor's own mistake becomes a wrong payment. This project splits the job in two:

1. **Claude reads the document.** The PDF goes to the Claude API with a strict output schema, so every response is valid JSON in one fixed shape, whatever the invoice looks like or what language it's in.
2. **Plain code checks the numbers.** Line totals, subtotal, tax and total are recalculated, and dates, currency and bank details are sanity-checked. Anything that doesn't add up is flagged for a person instead of passed through.

## What it handles

The `samples/` folder has five fictional invoices in deliberately different layouts:

| File | What makes it tricky |
|---|---|
| `01-us-table.pdf` | Standard US table, sales tax, ACH details |
| `02-eu-vat.pdf` | German: comma decimals, `dd.mm.yyyy` dates, 19% VAT, IBAN, fractional quantity |
| `03-freelancer-text.pdf` | No table at all: items written as text lines, reverse-charge VAT, due date given only as "within 14 days" |
| `04-uk-discount.pdf` | Negative discount line, totals in a side box, sort code |
| `05-math-error.pdf` | Looks normal, but the subtotal is $100 more than the line items. Validation must catch it. |

Every vendor, address, tax number and bank detail in the samples is made up.

## Output

For a folder of PDFs it writes:

- `output/json/<file>.json`: the extracted invoice
- `output/invoices.csv`: one row per invoice
- `output/invoices.xlsx`: three sheets: **Invoices** (flagged rows highlighted), **Line items**, and **Needs review** (one row per issue)

Each invoice gets a status: `ok`, `needs_review` (it extracted, but a check failed) or `failed` (no usable output).

## How it works

```
PDF ──> Claude API (PDF document input + strict JSON schema) ──> Invoice (Pydantic)
                                                                      │
                                         validate.py: arithmetic, dates, currency, IBAN
                                                                      │
                                            ok / needs_review ──> JSON, CSV, Excel
```

- `schema.py`: one Pydantic model is both the schema sent to Claude and the type the pipeline uses, so they can't drift apart.
- `extract.py`: sends the PDF as a document block and asks for structured output. The prompt tells the model to copy figures as printed and never correct them, because correcting is the validator's job. Refusals, truncated responses and schema failures each raise a clear error instead of producing a half-filled row.
- `validate.py`: deterministic checks with a one-cent tolerance. No model involved.
- `report.py`: CSV and Excel output.
- `scripts/score.py`: compares extracted JSON with hand-checked expected answers in `samples/expected/`, field by field, so a prompt or model change can be measured instead of eyeballed.

## Data handling

- Only the PDF being processed is sent to the API, one invoice per request. Nothing else from your machine or inbox goes with it.
- No invoice data is stored anywhere except the local `output/` folder.
- The API key is read from the environment, never from code or config files in the repo.

## Run it

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python samples/generate_samples.py      # builds the five sample PDFs
export ANTHROPIC_API_KEY=sk-ant-...             # or: ant auth login
uv run invoice-parser samples/invoices          # extract, validate, write output/
uv run python scripts/score.py                  # accuracy against samples/expected
```

Options: `--out <folder>` and `--effort low|medium|high|xhigh|max` (default `medium`).

Tests run without an API key (the extraction test uses a mocked HTTP transport):

```bash
uv run pytest
```

## Results

Fill in after the first real run with `scripts/score.py`.

## Extending it

- **Gmail intake:** watch a label, save PDF attachments, run the parser (an n8n or Apps Script trigger works well).
- **Accounting push:** send `ok` invoices to Xero or QuickBooks as draft bills, and keep `needs_review` ones out until a person approves them.
- **Batch mode:** for large backlogs, the Message Batches API halves the cost when results aren't needed immediately.
