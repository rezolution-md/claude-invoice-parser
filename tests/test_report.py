from pathlib import Path

from openpyxl import load_workbook

from claude_invoice_parser.report import Row, write_csv, write_xlsx
from claude_invoice_parser.schema import Invoice
from claude_invoice_parser.validate import validate_invoice

EXPECTED = Path(__file__).parent.parent / "samples" / "expected"


def test_reports_from_expected(tmp_path):
    rows = []
    for path in sorted(EXPECTED.glob("*.json")):
        inv = Invoice.model_validate_json(path.read_text(encoding="utf-8"))
        rows.append(Row(file=f"{path.stem}.pdf", invoice=inv, issues=validate_invoice(inv)))
    rows.append(Row(file="broken.pdf", invoice=None, error="request declined"))

    write_csv(rows, tmp_path / "invoices.csv")
    write_xlsx(rows, tmp_path / "invoices.xlsx")

    wb = load_workbook(tmp_path / "invoices.xlsx")
    assert wb.sheetnames == ["Invoices", "Line items", "Needs review"]
    statuses = [r[1] for r in wb["Invoices"].iter_rows(min_row=2, values_only=True)]
    assert statuses == ["ok", "ok", "ok", "ok", "needs_review", "failed"]
    assert wb["Line items"].max_row == 1 + 15
    review_files = {r[0] for r in wb["Needs review"].iter_rows(min_row=2, values_only=True)}
    assert review_files == {"05-math-error.pdf", "broken.pdf"}
