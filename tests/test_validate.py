import json
from pathlib import Path

import pytest

from claude_invoice_parser.schema import Invoice
from claude_invoice_parser.validate import validate_invoice

EXPECTED = Path(__file__).parent.parent / "samples" / "expected"


def load(name: str) -> Invoice:
    return Invoice.model_validate_json((EXPECTED / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["01-us-table", "02-eu-vat", "03-freelancer-text", "04-uk-discount"])
def test_clean_invoices_pass(name):
    assert validate_invoice(load(name)) == []


def test_math_error_is_flagged():
    issues = validate_invoice(load("05-math-error"))
    assert any("add up to 1030.0, but subtotal is 1130.0" in i for i in issues)
    assert any("no bank account" in i for i in issues)


def test_line_arithmetic_is_checked():
    inv = load("01-us-table")
    inv.line_items[0].line_total = 550.0
    issues = validate_invoice(inv)
    assert any(i.startswith("line 1") for i in issues)


def test_tax_rate_mismatch():
    inv = load("02-eu-vat")
    inv.tax_rate_percent = 7
    assert any("7% of 725.0" in i for i in validate_invoice(inv))


def test_bad_dates():
    inv = load("04-uk-discount")
    inv.issue_date = "01/11/2026"
    inv.due_date = "2026-02-30"
    issues = validate_invoice(inv)
    assert any("issue_date is not an ISO date" in i for i in issues)
    assert any("due_date is not a real date" in i for i in issues)


def test_due_before_issue():
    inv = load("01-us-table")
    inv.due_date = "2026-10-01"
    assert any("before issue date" in i for i in validate_invoice(inv))


def test_discount_lines_count_towards_subtotal():
    inv = load("04-uk-discount")
    inv.line_items.pop()  # drop the -360 discount
    assert any("add up to 4250.0" in i for i in validate_invoice(inv))
