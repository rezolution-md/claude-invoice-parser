"""Checks that compare the extraction with the PDF itself, plus the review flags added after the
attack test (samples/attacks, bakeoff/attacks/RESULTS.md)."""

from pathlib import Path

import pytest

from claude_invoice_parser.document import pdf_text
from claude_invoice_parser.schema import Invoice
from claude_invoice_parser.validate import ibans_in_text, validate_invoice

SAMPLES = Path(__file__).parent.parent / "samples"


def load(folder: str, name: str) -> Invoice:
    return Invoice.model_validate_json((SAMPLES / folder / "expected" / f"{name}.json").read_text(encoding="utf-8"))


def holdout(name: str) -> Invoice:
    return Invoice.model_validate_json((SAMPLES / "holdout" / "expected" / f"{name}.json").read_text(encoding="utf-8"))


CLEAN = [(p, SAMPLES / "expected" / f"{p.stem}.json") for p in sorted((SAMPLES / "invoices").glob("*.pdf"))] + [
    (p, SAMPLES / "holdout" / "expected" / f"{p.stem}.json") for p in sorted((SAMPLES / "holdout" / "invoices").glob("*.pdf"))
]
KNOWN_ISSUES = {"05-math-error": 2, "h11-vat-error": 1}  # the deliberate vendor errors, nothing more


@pytest.mark.parametrize("pdf,expected", CLEAN, ids=[p.stem for p, _ in CLEAN])
def test_honest_invoices_get_no_new_flags(pdf, expected):
    inv = Invoice.model_validate_json(expected.read_text(encoding="utf-8"))
    assert len(validate_invoice(inv, pdf_text(pdf))) == KNOWN_ISSUES.get(pdf.stem, 0)


def test_image_only_pdf_has_no_text_and_does_not_crash():
    photo = SAMPLES / "holdout" / "photos" / "h06-uk-ddmm-photo.pdf"
    assert pdf_text(photo).strip() == ""
    assert validate_invoice(holdout("h06-uk-ddmm"), pdf_text(photo)) == []


def test_ibans_in_text_handles_spaced_groups():
    text = "IBAN: GB00 DEMO 0000 1234 5678 90 BIC: DEMOGB21XXX\nVAT reg GB000000101"
    assert ibans_in_text(text) == {"GB00DEMO00001234567890"}


@pytest.mark.parametrize("name", ["a02-tiny-footer-iban", "a04-fake-json", "a06-hidden-second-invoice", "a10-bank-details-changed"])
def test_second_iban_in_document_goes_to_review(name):
    """Even a perfect extraction is flagged: the document itself offers another account."""
    issues = validate_invoice(load("attacks", name), pdf_text(SAMPLES / "attacks" / "invoices" / f"{name}.pdf"))
    assert any("another IBAN" in i for i in issues)


def test_zero_width_and_lookalike_characters_in_document():
    issues = validate_invoice(load("attacks", "a09-hidden-chars"), pdf_text(SAMPLES / "attacks" / "invoices" / "a09-hidden-chars.pdf"))
    assert any("zero-width" in i for i in issues)
    assert any("look-alike" in i for i in issues)


def test_lookalike_characters_in_extracted_fields():
    inv = holdout("h06-uk-ddmm")
    inv.invoice_number = "RХ-2026-0907"  # Cyrillic Ha
    assert any("invoice_number contains invisible or look-alike" in i for i in validate_invoice(inv))
    inv = holdout("h06-uk-ddmm")
    inv.payment.iban = "GB00DEMO0000​1234567890"
    assert any("iban contains invisible or look-alike" in i for i in validate_invoice(inv))


def test_iban_length_per_country():
    inv = holdout("h06-uk-ddmm")
    inv.payment.iban = "GB00DEMO000012345678901"  # one digit too many
    assert any("GB IBANs have 22" in i for i in validate_invoice(inv))


def test_notes_warning_becomes_review_flag():
    inv = holdout("h06-uk-ddmm")
    inv.notes = "Conflicting bank details: a notice says the bank account has changed. Verify with the vendor before paying."
    assert any("notes warn" in i for i in validate_invoice(inv))


@pytest.mark.parametrize("note", [
    "Document is marked as a fictional sample: every company, number and bank detail is invented.",
    "Payment by bank transfer. Quote FF-2026-0412 as payment reference.",
    "VAT reverse charge: customer accounts for VAT.",
])
def test_ordinary_notes_are_not_flagged(note):
    inv = holdout("h06-uk-ddmm")
    inv.notes = note
    assert validate_invoice(inv) == []
