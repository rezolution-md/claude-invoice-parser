"""Deterministic checks on extracted invoices.

The model reads the document; plain arithmetic decides whether the numbers hold up.
Anything that fails goes to a human instead of straight into the books.
"""

import re
import unicodedata
from datetime import date

from .schema import Invoice

TOLERANCE = 0.01  # one cent, to absorb rounding on printed figures
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")

# Official IBAN lengths per country (SWIFT IBAN registry), for the countries most invoices come from.
IBAN_LENGTHS = {
    "AD": 24, "AE": 23, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24, "DE": 22, "DK": 18,
    "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22, "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IS": 26,
    "IT": 27, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MT": 31, "NL": 18, "NO": 15, "PL": 28,
    "PT": 25, "RO": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "TR": 26,
}
# IBAN-shaped runs in document text; spaces between groups allowed, line breaks not.
IBAN_IN_TEXT = re.compile(r"[A-Z]{2}\d{2}(?: ?[A-Z0-9]){10,32}")
# Characters that render as nothing but change the value: zero-width space, non-joiner, joiner, word joiner, BOM.
INVISIBLE_CHARS = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
# Words that mix Latin with Cyrillic or Greek letters, like "RХ-2026" with a Cyrillic Х.
MIXED_SCRIPT_WORD = re.compile(r"\S*[A-Za-z]\S*")

# Phrases the extractor writes in `notes` when the document itself looks wrong. The model reports
# these; this list turns the report into a review flag instead of leaving it in a free-text field.
NOTE_WARNINGS = [
    r"bank (?:details|account|information)s? (?:\w+ ){0,3}(?:changed|change|updated)",
    r"(?:conflicting|different|second|two|new) (?:sets? of )?(?:bank|payment|account|iban)",
    r"\bfraud",
    r"tamper",
    r"phishing",
    r"prompt injection",
    r"(?:hidden|invisible|white) text",
    r"text layer",
    r"(?:addressed|aimed|directed) (?:to|at) (?:an? )?(?:ai|automated|software|ocr)",
    r"verify .{0,80}before (?:paying|payment|booking)",
]
NOTE_WARNING = re.compile("|".join(NOTE_WARNINGS), re.IGNORECASE)


def _normalize_iban(value: str) -> str:
    return re.sub(r"\s", "", value).upper()


def ibans_in_text(text: str) -> set[str]:
    """IBANs printed anywhere in the document text, cut to their country's length."""
    found = set()
    for match in IBAN_IN_TEXT.finditer(text):
        candidate = _normalize_iban(match.group())
        length = IBAN_LENGTHS.get(candidate[:2])
        if length and len(candidate) >= length:
            found.add(candidate[:length])
    return found


def _script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    for script in ("LATIN", "CYRILLIC", "GREEK"):
        if name.startswith(script):
            return script
    return None


def _mixed_script_words(text: str) -> list[str]:
    words = []
    for match in MIXED_SCRIPT_WORD.finditer(text):
        scripts = {_script(ch) for ch in match.group()} - {None}
        if "LATIN" in scripts and len(scripts) > 1:
            words.append(match.group())
    return words


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


def validate_invoice(inv: Invoice, document_text: str | None = None) -> list[str]:
    """Return a list of human-readable issues. An empty list means the invoice passed.

    `document_text` is the PDF's raw text layer (see document.pdf_text). When given, the
    extraction is also compared with everything hidden or printed in the document.
    """
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
    elif pay.iban:
        iban = _normalize_iban(pay.iban)
        length = IBAN_LENGTHS.get(iban[:2])
        if length and len(iban) != length:
            issues.append(f"IBAN {iban} has {len(iban)} characters, but {iban[:2]} IBANs have {length}")

    for field_name, value in (("invoice_number", inv.invoice_number), ("iban", pay.iban), ("vendor_name", inv.vendor_name)):
        if value and (INVISIBLE_CHARS.search(value) or _mixed_script_words(value)):
            issues.append(f"{field_name} contains invisible or look-alike characters: {value!r}")

    if inv.notes and (warning := NOTE_WARNING.search(inv.notes)):
        issues.append(f"the extractor's notes warn about the document ({warning.group()!r}): read the notes before paying")

    if document_text:
        others = ibans_in_text(document_text) - ({_normalize_iban(pay.iban)} if pay.iban else set())
        if others:
            listed = ", ".join(sorted(others))
            issues.append(f"the document contains another IBAN than the one extracted ({listed}): check which account is real")
        if INVISIBLE_CHARS.search(document_text):
            issues.append("the document's text contains invisible zero-width characters")
        if mixed := _mixed_script_words(document_text):
            issues.append(f"the document's text mixes Latin with Cyrillic or Greek look-alike letters: {mixed[:3]!r}")

    return issues
