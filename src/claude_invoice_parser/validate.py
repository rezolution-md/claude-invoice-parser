"""Deterministic checks on extracted invoices.

The model reads the document; plain arithmetic decides whether the numbers hold up.
Anything that fails goes to a human instead of straight into the books.
"""

import re
from datetime import date

from .schema import Invoice

TOLERANCE = 0.01  # one cent, to absorb rounding on printed figures
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE + 1e-9


def _parse_date(value: str | None, field: str, issues: list[str]) -> date | None:
    if value is None:
        return None
    if not ISO_DATE.match(value):
        issues.append(f"{field} is not an ISO date: {value!r}")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        issues.append(f"{field} is not a real date: {value!r}")
        return None


def validate_invoice(inv: Invoice) -> list[str]:
    """Return a list of human-readable issues. An empty list means the invoice passed."""
    issues: list[str] = []

    if not inv.line_items:
        issues.append("no line items found")

    for i, item in enumerate(inv.line_items, start=1):
        if item.quantity is not None and item.unit_price is not None:
            expected = round(item.quantity * item.unit_price, 2)
            if not _close(expected, item.line_total):
                issues.append(
                    f"line {i} ({item.description[:40]}): {item.quantity} x {item.unit_price} = {expected}, "
                    f"but line total is {item.line_total}"
                )

    lines_sum = round(sum(item.line_total for item in inv.line_items), 2)
    net = inv.subtotal if inv.subtotal is not None else lines_sum
    if inv.subtotal is not None and not _close(lines_sum, inv.subtotal):
        issues.append(f"line items add up to {lines_sum}, but subtotal is {inv.subtotal}")

    tax = inv.tax_amount or 0.0
    if inv.tax_rate_percent is not None and inv.tax_amount is not None:
        expected_tax = round(net * inv.tax_rate_percent / 100, 2)
        if not _close(expected_tax, inv.tax_amount):
            issues.append(f"{inv.tax_rate_percent}% of {net} is {expected_tax}, but tax amount is {inv.tax_amount}")

    if not _close(round(net + tax, 2), inv.total):
        issues.append(f"net {net} + tax {tax} = {round(net + tax, 2)}, but total is {inv.total}")

    issued = _parse_date(inv.issue_date, "issue_date", issues)
    due = _parse_date(inv.due_date, "due_date", issues)
    if issued and due and due < issued:
        issues.append(f"due date {due} is before issue date {issued}")
    if inv.issue_date is None:
        issues.append("issue date missing")

    if not CURRENCY.match(inv.currency):
        issues.append(f"currency is not a 3-letter ISO code: {inv.currency!r}")

    pay = inv.payment
    if not any([pay.iban, pay.account_number]):
        issues.append("no bank account or IBAN found")
    if pay.iban and not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{8,30}$", pay.iban.replace(" ", "")):
        issues.append(f"IBAN format looks wrong: {pay.iban!r}")

    return issues
