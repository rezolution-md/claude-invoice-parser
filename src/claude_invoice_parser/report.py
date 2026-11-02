"""Write extraction results to CSV and a three-sheet Excel workbook."""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .schema import Invoice

INVOICE_COLUMNS = [
    "file", "status", "vendor_name", "vendor_tax_id", "customer_name", "invoice_number",
    "issue_date", "due_date", "currency", "subtotal", "tax_rate_percent", "tax_amount", "total",
    "bank_name", "iban", "bic_swift", "account_number", "routing_or_sort_code", "notes", "issues",
]


@dataclass
class Row:
    file: str
    invoice: Invoice | None
    issues: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def status(self) -> str:
        if self.error:
            return "failed"
        return "needs_review" if self.issues else "ok"


def _invoice_record(row: Row) -> dict:
    record = {"file": row.file, "status": row.status, "issues": "; ".join(row.issues or ([row.error] if row.error else []))}
    if row.invoice:
        inv = row.invoice
        record.update(inv.model_dump(exclude={"line_items", "payment"}))
        record.update(inv.payment.model_dump())
    return {col: record.get(col) for col in INVOICE_COLUMNS}


def write_csv(rows: list[Row], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INVOICE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_invoice_record(row))


def write_xlsx(rows: list[Row], path: Path) -> None:
    wb = Workbook()
    bold = Font(bold=True)
    flag = PatternFill("solid", fgColor="FCE4D6")

    invoices = wb.active
    invoices.title = "Invoices"
    invoices.append(INVOICE_COLUMNS)
    for row in rows:
        record = _invoice_record(row)
        invoices.append([record[c] for c in INVOICE_COLUMNS])
        if row.status != "ok":
            for cell in invoices[invoices.max_row]:
                cell.fill = flag

    items = wb.create_sheet("Line items")
    items.append(["file", "invoice_number", "line", "description", "quantity", "unit_price", "line_total"])
    for row in rows:
        if row.invoice:
            for i, item in enumerate(row.invoice.line_items, start=1):
                items.append([row.file, row.invoice.invoice_number, i, item.description,
                              item.quantity, item.unit_price, item.line_total])

    review = wb.create_sheet("Needs review")
    review.append(["file", "status", "issue"])
    for row in rows:
        for issue in row.issues or ([row.error] if row.error else []):
            review.append([row.file, row.status, issue])

    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.font = bold
        sheet.freeze_panes = "A2"
    wb.save(path)
