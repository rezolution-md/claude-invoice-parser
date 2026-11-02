"""Generate fictional sample invoices in deliberately different layouts.

Every vendor, customer, address, tax number and bank detail here is made up.
Run: uv run python samples/generate_samples.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "invoices"
STYLES = getSampleStyleSheet()


def p(text, style="Normal"):
    return Paragraph(text, STYLES[style])


def grid(data, widths, header_bg="#1f3a5f"):
    t = Table(data, colWidths=widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return t


def us_table_invoice():
    """Classic US layout: header block, line-item table, totals with sales tax."""
    doc = SimpleDocTemplate(str(OUT / "01-us-table.pdf"), pagesize=LETTER)
    rows = [
        ["Description", "Qty", "Unit price", "Amount"],
        ["Fiber optic patch cable, 10 ft", "40", "$12.50", "$500.00"],
        ["Rack-mount patch panel, 24 port", "3", "$89.00", "$267.00"],
        ["On-site installation (hours)", "6", "$95.00", "$570.00"],
    ]
    doc.build(
        [
            p("<b>Bluepine Network Supply LLC</b>", "Title"),
            p("410 Cedar Ridge Rd, Boise, ID 83702 · EIN 00-0000001"),
            Spacer(1, 6 * mm),
            p("<b>INVOICE</b> #BNS-24817"),
            p("Invoice date: October 14, 2026 · Due date: November 13, 2026 (Net 30)"),
            p("Bill to: Harbor Clinic Group, 22 Lake St, Spokane, WA 99201"),
            Spacer(1, 6 * mm),
            grid(rows, [90 * mm, 20 * mm, 30 * mm, 30 * mm]),
            Spacer(1, 4 * mm),
            p("Subtotal: $1,337.00"),
            p("Sales tax (6%): $80.22"),
            p("<b>Total due: $1,417.22 USD</b>"),
            Spacer(1, 6 * mm),
            p("Pay by ACH: First Demo Bank, routing 000000001, account 000123456789"),
        ]
    )


def eu_vat_invoice():
    """German style: comma decimals, dd.mm.yyyy dates, VAT, IBAN, columns in a different order."""
    doc = SimpleDocTemplate(str(OUT / "02-eu-vat.pdf"), pagesize=A4)
    rows = [
        ["Pos.", "Bezeichnung", "Menge", "Einzelpreis", "Gesamt"],
        ["1", "Wartungsvertrag Server, Oktober", "1", "450,00 €", "450,00 €"],
        ["2", "Ersatzlüfter 120 mm", "4", "18,75 €", "75,00 €"],
        ["3", "Fernsupport (Std.)", "2,5", "80,00 €", "200,00 €"],
    ]
    doc.build(
        [
            p("<b>Nordlicht IT-Service GmbH</b>", "Title"),
            p("Hafenstraße 9, 20457 Hamburg · USt-IdNr. DE000000001"),
            Spacer(1, 6 * mm),
            p("<b>Rechnung</b> Nr. NL-2026-0931"),
            p("Rechnungsdatum: 03.10.2026 · Zahlbar bis: 17.10.2026"),
            p("Kunde: Praxis am Stadtpark, Parkallee 4, 28209 Bremen"),
            Spacer(1, 6 * mm),
            grid(rows, [15 * mm, 75 * mm, 20 * mm, 30 * mm, 30 * mm], header_bg="#3b3b3b"),
            Spacer(1, 4 * mm),
            p("Nettobetrag: 725,00 €"),
            p("zzgl. 19 % MwSt.: 137,75 €"),
            p("<b>Rechnungsbetrag: 862,75 €</b>"),
            Spacer(1, 6 * mm),
            p("Bankverbindung: Demo Sparkasse · IBAN DE00 0000 0000 0000 0000 00 · BIC DEMODEXXX"),
        ]
    )


def freelancer_text_invoice():
    """No table at all: line items written as prose lines, typical of a freelancer's simple PDF."""
    c = canvas.Canvas(str(OUT / "03-freelancer-text.pdf"), pagesize=A4)
    y = 270 * mm
    lines = [
        ("Helvetica-Bold", 16, "Mara Velasquez Design"),
        ("Helvetica", 10, "mara@example.com · Lisbon, Portugal · NIF 000000001"),
        ("Helvetica", 10, ""),
        ("Helvetica-Bold", 12, "Invoice 2026/017"),
        ("Helvetica", 10, "Issued 21 September 2026. Please pay within 14 days."),
        ("Helvetica", 10, "Client: Quillstone Publishing Ltd, London"),
        ("Helvetica", 10, ""),
        ("Helvetica", 10, "Book cover design, 'The Long Tide' (flat fee) ........ EUR 1,200.00"),
        ("Helvetica", 10, "Two extra revision rounds at EUR 150.00 each ......... EUR 300.00"),
        ("Helvetica", 10, "Licensed stock image ........................................ EUR 45.00"),
        ("Helvetica", 10, ""),
        ("Helvetica", 10, "VAT: reverse charge (Article 196, Directive 2006/112/EC)"),
        ("Helvetica-Bold", 11, "Amount due: EUR 1,545.00"),
        ("Helvetica", 10, ""),
        ("Helvetica", 10, "Bank transfer to IBAN PT50 0000 0000 0000 0000 0000 0, BIC DEMOPTPL"),
    ]
    for font, size, text in lines:
        c.setFont(font, size)
        c.drawString(20 * mm, y, text)
        y -= 7 * mm
    c.save()


def uk_discount_invoice():
    """UK layout with a discount line, VAT at 20%, and totals in a right-hand box."""
    doc = SimpleDocTemplate(str(OUT / "04-uk-discount.pdf"), pagesize=A4)
    rows = [
        ["Item", "Units", "Rate", "Line total"],
        ["Annual software licence, 15 seats", "15", "£240.00", "£3,600.00"],
        ["Onboarding workshop (half day)", "1", "£650.00", "£650.00"],
        ["Loyalty discount 10% on licences", "1", "-£360.00", "-£360.00"],
    ]
    totals = Table(
        [["Net", "£3,890.00"], ["VAT 20%", "£778.00"], ["Total", "£4,668.00"]],
        colWidths=[30 * mm, 35 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.black), ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    doc.build(
        [
            p("<b>Kestrel Ledger Software Ltd</b>", "Title"),
            p("Unit 5, Mill Yard, Leeds LS1 4AB · VAT reg. GB000000001"),
            Spacer(1, 6 * mm),
            p("Tax invoice KLS-INV-5530 · Date: 1 November 2026 · Payment terms: 30 days"),
            p("Customer: Northfield Physio Partners, 8 Mount Pleasant, York YO1 7EZ"),
            Spacer(1, 6 * mm),
            grid(rows, [85 * mm, 20 * mm, 30 * mm, 35 * mm], header_bg="#2f5d50"),
            Spacer(1, 4 * mm),
            totals,
            Spacer(1, 6 * mm),
            p("Pay to: Demo Bank plc, sort code 00-00-00, account 00001234"),
        ]
    )


def broken_math_invoice():
    """Looks normal, but the subtotal does not match the line items. Validation should flag it."""
    doc = SimpleDocTemplate(str(OUT / "05-math-error.pdf"), pagesize=LETTER)
    rows = [
        ["Service", "Qty", "Price", "Total"],
        ["Monthly bookkeeping, October", "1", "$600.00", "$600.00"],
        ["Payroll run (per employee)", "12", "$15.00", "$180.00"],
        ["Year-end prep deposit", "1", "$250.00", "$250.00"],
    ]
    doc.build(
        [
            p("<b>Copperfield Accounts &amp; Payroll</b>", "Title"),
            p("77 Market St, Austin, TX 78701"),
            Spacer(1, 6 * mm),
            p("Invoice CAP-1042 · Date: 2026-10-31 · Due: 2026-11-15"),
            p("Bill to: Sunrise Dental Studio, Austin, TX"),
            Spacer(1, 6 * mm),
            grid(rows, [90 * mm, 20 * mm, 30 * mm, 30 * mm], header_bg="#7a4b1f"),
            Spacer(1, 4 * mm),
            p("Subtotal: $1,130.00"),
            p("Tax: $0.00"),
            p("<b>Balance due: $1,130.00</b>"),
        ]
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for build in (us_table_invoice, eu_vat_invoice, freelancer_text_invoice, uk_discount_invoice, broken_math_invoice):
        build()
    print(f"Wrote {len(list(OUT.glob('*.pdf')))} sample invoices to {OUT}")
