"""Command line entry point: invoice-parser <folder of PDFs> [--out output]"""

import argparse
import json
import sys
from pathlib import Path

import anthropic

from .extract import ExtractionError, extract_invoice
from .report import Row, write_csv, write_xlsx
from .validate import validate_invoice


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract structured data from PDF invoices with the Claude API.")
    parser.add_argument("folder", type=Path, help="Folder containing PDF invoices")
    parser.add_argument("--out", type=Path, default=Path("output"), help="Output folder (default: output)")
    parser.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"],
                        help="Claude effort level (default: medium)")
    args = parser.parse_args(argv)

    pdfs = sorted(args.folder.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {args.folder}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "json").mkdir(exist_ok=True)
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY or an `ant auth login` profile

    rows: list[Row] = []
    total_in = total_out = 0
    for pdf in pdfs:
        try:
            result = extract_invoice(pdf, client, effort=args.effort)
        except ExtractionError as e:
            rows.append(Row(file=pdf.name, invoice=None, error=str(e)))
            print(f"FAILED        {pdf.name}: {e}")
            continue
        except anthropic.AuthenticationError:
            print("Claude rejected the credentials. Check ANTHROPIC_API_KEY or run `ant auth login`.", file=sys.stderr)
            return 2
        except TypeError as e:
            if "authentication" not in str(e):
                raise
            # The SDK raises this before sending anything when no credentials are configured at all.
            print("No Claude credentials found. Set ANTHROPIC_API_KEY or run `ant auth login`.", file=sys.stderr)
            return 2
        except anthropic.RateLimitError:
            print("Rate limited by the API. Wait a minute and run again.", file=sys.stderr)
            return 3
        except anthropic.APIStatusError as e:
            rows.append(Row(file=pdf.name, invoice=None, error=f"API error {e.status_code}: {e.message}"))
            print(f"FAILED        {pdf.name}: API error {e.status_code}")
            continue
        except anthropic.APIConnectionError:
            print("Network error reaching the Claude API.", file=sys.stderr)
            return 4

        issues = validate_invoice(result.invoice)
        row = Row(file=pdf.name, invoice=result.invoice, issues=issues)
        rows.append(row)
        total_in += result.input_tokens
        total_out += result.output_tokens
        (args.out / "json" / f"{pdf.stem}.json").write_text(
            json.dumps(result.invoice.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        label = row.status.upper().ljust(13)
        print(f"{label} {pdf.name}: {result.invoice.vendor_name}, {result.invoice.currency} {result.invoice.total}")
        for issue in issues:
            print(f"              - {issue}")

    write_csv(rows, args.out / "invoices.csv")
    write_xlsx(rows, args.out / "invoices.xlsx")

    ok = sum(r.status == "ok" for r in rows)
    print(f"\n{len(rows)} invoices: {ok} ok, {len(rows) - ok} need review or failed.")
    print(f"Tokens: {total_in} in, {total_out} out. Report: {args.out / 'invoices.xlsx'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
