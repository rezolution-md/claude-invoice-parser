"""Generate the HELD-OUT invoice set for the extraction bake-off.

Every company, person, address, tax number and bank detail in this file is invented.
IBANs and tax numbers are dummies with fake check digits. Nothing here is a real invoice.

Single source of truth: each invoice below is ONE Python dict.
  - dict["invoice"] is exactly the shape of src/claude_invoice_parser/schema.py (Invoice).
    It is written verbatim to expected/<name>.json AND it is what the PDF prints.
  - dict["print"] holds layout-only details (addresses, labels, extra dates) that are not
    part of the schema.
The renderers only format values taken from these dicts. Expected answers are never read
back from the PDFs.

Outputs (all under samples/holdout/):
  invoices/<name>.pdf        text-layer PDFs
  expected/<name>.json       expected extraction, same shape as samples/expected/*.json
  photos/<name>-photo.pdf    image-only "phone photo" versions of 4 invoices (needs pdftoppm)

Run: uv run python samples/holdout/generate_holdout.py
"""

import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))
from claude_invoice_parser.schema import Invoice  # noqa: E402
from claude_invoice_parser.validate import validate_invoice  # noqa: E402

FICTIONAL = "FICTIONAL SAMPLE - every company, number and bank detail on this document is invented."


# --------------------------------------------------------------------------- data helpers

def li(description, quantity, unit_price):
    """One line item. line_total = quantity x unit_price, rounded half-up to cents."""
    total = (Decimal(str(quantity)) * Decimal(str(unit_price))).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return {"description": description, "quantity": quantity, "unit_price": float(unit_price),
            "line_total": float(total)}


def pay(bank_name=None, iban=None, bic_swift=None, account_number=None, routing_or_sort_code=None):
    return {"bank_name": bank_name, "iban": iban, "bic_swift": bic_swift,
            "account_number": account_number, "routing_or_sort_code": routing_or_sort_code}


# --------------------------------------------------------------------------- the 12 invoices

INVOICES = [
    {
        "name": "h01-fr-tva",
        "photo": False,
        "invoice": {
            "vendor_name": "Atelier Lumière Bleue SARL",
            "vendor_tax_id": "000 000 001 00012",
            "customer_name": "Cabinet Dentaire des Tilleuls",
            "invoice_number": "F-2026-1103",
            "issue_date": "2026-11-03",
            "due_date": "2026-12-03",
            "currency": "EUR",
            "line_items": [
                li("Maintenance éclairage LED, novembre", 1, 380.00),
                li("Dalle LED 60×60 cm", 12, 42.50),
                li("Intervention technicien (heures)", 3.5, 64.00),
            ],
            "subtotal": 1114.00,
            "tax_rate_percent": 20,
            "tax_amount": 222.80,
            "total": 1336.80,
            "payment": pay("Banque Démo du Littoral", "FR7600000000000000000000000", "DEMOFRPPXXX"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["12 rue des Quatre-Vents, 44000 Nantes", "SIRET 000 000 001 00012"],
            "customer_lines": ["14 avenue des Tilleuls", "49100 Angers"],
        },
    },
    {
        "name": "h02-es-iva",
        "photo": False,
        "invoice": {
            "vendor_name": "Talleres Brisamar S.L.",
            "vendor_tax_id": "B00000001",
            "customer_name": "Clínica Veterinaria Los Almendros",
            "invoice_number": "FV-2026/0388",
            "issue_date": "2026-10-15",
            "due_date": "2026-11-14",  # printed only as "30 días fecha factura"
            "currency": "EUR",
            "line_items": [
                li("Revisión anual climatización", 1, 290.00),
                li("Filtro HEPA H13", 6, 137.40),
                li("Mano de obra (horas)", 4, 45.00),
                li("Desplazamiento", 1, 25.00),
            ],
            "subtotal": 1319.40,
            "tax_rate_percent": 21,
            "tax_amount": 277.07,
            "total": 1596.47,
            "payment": pay("Banco Ficticio Mediterráneo", "ES0000000000000000000000", "DEMOESMMXXX"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["Calle del Puerto 27, 46011 Valencia", "NIF: B00000001"],
            "customer_lines": ["Avenida de los Almendros 3", "03001 Alicante"],
        },
    },
    {
        "name": "h03-hu-afa",
        "photo": True,
        "invoice": {
            "vendor_name": "Dunakavics Informatikai Kft.",
            "vendor_tax_id": "00000001-2-41",
            "customer_name": "Gyöngyvirág Fogászati Bt.",
            "invoice_number": "DK-2026/0517",
            "issue_date": "2026-11-03",
            "due_date": "2026-11-18",
            "currency": "HUF",
            "line_items": [
                li("Hálózati audit", 1, 485000),
                li("Wi-Fi hozzáférési pont telepítése", 4, 48500),
                li("Rendszergazdai óradíj", 7, 14000),
                li("Szoftverlicenc, 1 év", 5, 23400),
            ],
            "subtotal": 894000.0,
            "tax_rate_percent": 27,
            "tax_amount": 241380.0,
            "total": 1135380.0,
            "payment": pay("Próba Bank Zrt.", "HU00000000000000000000000001", "DEMOHUHB",
                           "00000000-00000000-00000001"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["1036 Budapest, Kavics utca 8.", "Adószám: 00000001-2-41"],
            "customer_lines": ["9021 Győr, Virág sor 5."],
            "fulfilment_date": "2026-10-31",
        },
    },
    {
        "name": "h04-it-iva",
        "photo": False,
        "invoice": {
            "vendor_name": "Officine Grafiche Vallerosa S.r.l.",
            "vendor_tax_id": "IT00000000001",
            "customer_name": "Studio Legale Bramante",
            "invoice_number": "457/2026",
            "issue_date": "2026-10-07",
            "due_date": "2026-11-06",
            "currency": "EUR",
            "line_items": [
                li("Biglietti da visita, 500 pz", 4, 38.00),
                li("Carta intestata A4, risma", 10, 24.90),
                li("Brochure pieghevole, 1.000 pz", 2, 615.00),
                li("Progetto grafico (forfait)", 1, 420.00),
            ],
            "subtotal": 2051.00,
            "tax_rate_percent": 22,
            "tax_amount": 451.22,
            "total": 2502.22,
            "payment": pay("Banca Dimostrativa Veneta", "IT00X0000000000000000000000", "DEMOITMMXXX"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["Via dei Tipografi 19, 37121 Verona", "Partita IVA: IT00000000001"],
            "customer_lines": ["Corso Bramante 42", "20121 Milano"],
        },
    },
    {
        "name": "h05-us-commas",
        "photo": False,
        "invoice": {
            "vendor_name": "Redwater Mechanical Contractors Inc.",
            "vendor_tax_id": None,  # only a contractor licence number is printed, not a tax ID
            "customer_name": "Lakeshore Senior Living",
            "invoice_number": "RMC-30917",
            "issue_date": "2026-11-03",
            "due_date": "2026-12-03",
            "currency": "USD",
            "line_items": [
                li("Rooftop HVAC unit replacement, 10 ton", 1, 9850.00),
                li("Crane rental (day)", 1, 1275.00),
                li("Ductwork modification (hours)", 15, 118.00),
                li("Refrigerant R-454B (lb)", 22, 31.50),
            ],
            "subtotal": 13588.00,
            "tax_rate_percent": 8.25,
            "tax_amount": 1121.01,
            "total": 14709.01,
            "payment": pay("First Demo Bank", account_number="000987654321", routing_or_sort_code="000000002"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["1800 Foundry Ave, Cleveland, OH 44114", "Contractor License #000001"],
            "customer_lines": ["55 Shoreline Dr", "Sandusky, OH 44870"],
        },
    },
    {
        "name": "h06-uk-ddmm",
        "photo": True,
        "invoice": {
            "vendor_name": "Fernhollow Facilities Ltd",
            "vendor_tax_id": "GB000000002",
            "customer_name": "St Brannoc Primary School",
            "invoice_number": "FF-2026-0412",
            "issue_date": "2026-11-04",  # printed 04/11/2026: 4 November, not April 11
            "due_date": "2026-12-02",    # printed 02/12/2026
            "currency": "GBP",
            "line_items": [
                li("Window cleaning, October", 1, 340.00),
                li("Gutter clearance", 2, 95.00),
                li("Pressure washing, playground (m²)", 420, 1.20),
            ],
            "subtotal": 1034.00,
            "tax_rate_percent": 20,
            "tax_amount": 206.80,
            "total": 1240.80,
            "payment": pay("Demo Bank plc", account_number="00004321", routing_or_sort_code="00-00-01"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["3 Tannery Lane, Barnstaple EX31 1AA", "VAT No. GB000000002"],
            "customer_lines": ["Church Street", "Braunton EX33 2AA"],
            "period": ("2026-10-01", "2026-10-31"),
        },
    },
    {
        "name": "h07-two-column-totals-top",
        "photo": False,
        "invoice": {
            "vendor_name": "Glasán Data Services Ltd",
            "vendor_tax_id": "IE0000001T",
            "customer_name": "Ballymore Veterinary Hospital",
            "invoice_number": "GDS-7781",
            "issue_date": "2026-10-28",
            "due_date": "2026-11-27",
            "currency": "EUR",
            "line_items": [
                li("Managed backup, 2 TB tier", 1, 220.00),
                li("Email hosting, per mailbox", 18, 4.50),
                li("Firewall subscription, annual", 1, 640.00),
                li("Remote support block (5 h)", 2, 310.00),
            ],
            "subtotal": 1561.00,
            "tax_rate_percent": 23,
            "tax_amount": 359.03,
            "total": 1920.03,
            "payment": pay("Demo Bank Ireland", "IE00DEMO00000000000000", "DEMOIE2D"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["Unit 4, Quay Business Park", "Galway H91 AAAA", "VAT IE0000001T"],
            "customer_lines": ["Main Street", "Ballymore, Co. Westmeath"],
        },
    },
    {
        "name": "h08-banner-logo",
        "photo": False,
        "invoice": {
            "vendor_name": "Helix Fieldworks Pty Ltd",
            "vendor_tax_id": "00 000 000 001",
            "customer_name": "Coorong Water Testing Co-op",
            "invoice_number": "HX-00862",
            "issue_date": "2026-11-06",
            "due_date": "2026-11-20",  # printed only as "Terms: 14 days"
            "currency": "AUD",         # amounts printed with a bare "$"
            "line_items": [
                li("Soil moisture probe, 1.2 m", 8, 186.00),
                li("Data logger, 4-channel", 2, 349.00),
                li("Calibration service", 1, 260.00),
                li("Freight, Adelaide", 1, 45.00),
            ],
            "subtotal": 2491.00,
            "tax_rate_percent": 10,
            "tax_amount": 249.10,
            "total": 2740.10,
            "payment": pay("Demo Bank Australia", account_number="00012345", routing_or_sort_code="000-002"),
            "notes": None,
        },
        "print": {
            "brand": "HELIX",
            "tagline": "field instruments that survive the field",
            "vendor_lines": ["7 Dune Road, Goolwa SA 5214", "ABN 00 000 000 001"],
            "customer_lines": ["PO Box 12", "Meningie SA 5264"],
        },
    },
    {
        "name": "h09-two-page",
        "photo": True,
        "invoice": {
            "vendor_name": "Alpenrand Laborbedarf AG",
            "vendor_tax_id": "CHE-000.000.001",
            "customer_name": "Labor Seeblick GmbH",
            "invoice_number": "AL-2026-1190",
            "issue_date": "2026-11-03",
            "due_date": "2026-12-03",  # printed only as "payable within 30 days"
            "currency": "CHF",
            "line_items": [
                li("Nitrile gloves, size M, box of 100", 12, 8.90),
                li("Nitrile gloves, size L, box of 100", 8, 8.90),
                li("Pipette tips 200 µl, rack of 96", 20, 6.40),
                li("Pipette tips 1000 µl, rack of 96", 15, 7.10),
                li("Microcentrifuge tubes 1.5 ml, bag of 500", 6, 14.50),
                li("Conical tubes 15 ml, pack of 50", 10, 11.80),
                li("Conical tubes 50 ml, pack of 25", 10, 9.60),
                li("Petri dishes 90 mm, sleeve of 20", 25, 5.20),
                li("Serological pipettes 10 ml, case of 200", 2, 68.00),
                li("Cryo boxes, 81 places", 12, 4.75),
                li("Lab marker, black, pack of 10", 3, 13.20),
                li("Ethanol 70%, 5 l", 4, 29.50),
                li("Disinfectant wipes, tub of 150", 9, 12.40),
                li("Parafilm roll, 10 cm × 38 m", 2, 47.00),
                li("Weighing boats 100 ml, pack of 500", 1, 39.90),
                li("Glass beakers 250 ml, pack of 12", 2, 54.00),
                li("Magnetic stir bars, assorted set", 1, 32.50),
                li("Disposable lab coat, size L", 4, 27.80),
                li("Safety goggles, anti-fog", 6, 11.90),
                li("Sharps container 2 l", 10, 3.85),
                li("Biohazard bags 600 × 800 mm, roll of 50", 4, 18.60),
                li("pH buffer solution pH 7, 500 ml", 3, 16.20),
                # ---- page 2 starts here (PAGE_BREAK_AFTER = 22)
                li("pH buffer solution pH 4, 500 ml", 3, 16.20),
                li("Filter paper Ø 125 mm, pack of 100", 5, 9.40),
                li("Syringe filters 0.22 µm, pack of 50", 4, 42.00),
                li("Bench protector sheets, roll", 2, 36.50),
                li("Freezer labels, 1000 pcs", 2, 24.00),
                li("Tube rack, 4-way, blue", 6, 7.30),
                li("Cooling block for 1.5 ml tubes", 1, 64.00),
                li("Delivery, temperature-controlled", 1, 28.00),
            ],
            "subtotal": 2444.60,
            "tax_rate_percent": 8.1,
            "tax_amount": 198.01,
            "total": 2642.61,
            "payment": pay("Demo Kantonalbank", "CH0000000000000000001", "DEMOCHZZ"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["Bergstrasse 61, 6003 Luzern", "VAT no. CHE-000.000.001"],
            "customer_lines": ["Seeweg 2", "8800 Thalwil"],
            "page_break_after": 22,
        },
    },
    {
        "name": "h10-odd-labels",
        "photo": False,
        "invoice": {
            "vendor_name": "Kowhai Ridge Joinery Limited",
            "vendor_tax_id": "000-000-001",
            "customer_name": "Tui Bay Holiday Park",
            "invoice_number": "KRJ/26/114",
            "issue_date": "2026-11-19",
            "due_date": "2026-12-03",
            "currency": "NZD",
            "line_items": [
                li("Rimu bookshelf, built-in", 1, 2850.00),
                li("Kitchen cabinet doors, refaced", 14, 165.00),
                li("Site measure & quote", 1, 120.00),
                li("Hardware & fittings (lot)", 1, 386.40),
            ],
            "subtotal": 5666.40,
            "tax_rate_percent": 15,
            "tax_amount": 849.96,
            "total": 6516.36,
            "payment": pay("Demo Bank NZ", account_number="00-0000-0000001-00"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["22 Totara Street, Whakatane 3120", "GST registration 000-000-001"],
            "customer_lines": ["Beach Road", "Tui Bay 3191"],
        },
    },
    {
        "name": "h11-vat-error",
        "photo": True,
        "invoice": {
            "vendor_name": "Polderwind Installatietechniek B.V.",
            "vendor_tax_id": "NL000000001B01",
            "customer_name": "Huisartsenpraktijk De Linde",
            "invoice_number": "PW-2026-0219",
            "issue_date": "2026-11-09",
            "due_date": "2026-11-23",
            "currency": "EUR",
            "line_items": [
                li("Onderhoud warmtepomp", 1, 245.00),
                li("Vervangen expansievat", 1, 189.00),
                li("Arbeid (uur)", 6, 68.50),
                li("Voorrijkosten", 1, 35.00),
                li("Thermostaat, slim", 2, 480.00),
            ],
            "subtotal": 1840.00,
            "tax_rate_percent": 21,
            # DELIBERATE VENDOR ERROR: 21% of 1840.00 is 386.40; the invoice prints 386.90.
            # The total is net + the printed (wrong) tax, so only the tax-rate check fails.
            "tax_amount": 386.90,
            "total": 2226.90,
            "payment": pay("Demobank Noord", "NL00DEMO0000000001", "DEMONL2A"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["Dijkweg 140, 1619 AA Andijk", "KvK 00000001 · BTW-id NL000000001B01"],
            "customer_lines": ["Lindelaan 9", "1621 AB Hoorn"],
            "deliberate_tax_error": True,
        },
    },
    {
        "name": "h12-comma-customer",
        "photo": False,
        "invoice": {
            "vendor_name": "Larchmont Survey Instruments Inc.",
            "vendor_tax_id": "000000001RT0001",
            "customer_name": "Halloran, Pike & Co",
            "invoice_number": "LSI-55102",
            "issue_date": "2026-11-05",
            "due_date": "2026-11-20",  # printed only as "Net 15"
            "currency": "CAD",
            "line_items": [
                li("Total station rental, weekly", 2, 675.00),
                li("GNSS rover rental, weekly", 2, 540.00),
                li("Tripod & prism kit", 2, 60.00),
                li("Delivery & pickup, Calgary", 1, 85.00),
            ],
            "subtotal": 2635.00,
            "tax_rate_percent": 5,
            "tax_amount": 131.75,
            "total": 2766.75,
            "payment": pay("Demo Bank of Canada", account_number="0001234567", routing_or_sort_code="000000011"),
            "notes": None,
        },
        "print": {
            "vendor_lines": ["940 Industrial Way NE, Calgary AB T2E 0A0", "GST/HST Reg. No. 000000001RT0001"],
            "customer_lines": ["Suite 300, 505 5 Ave SW", "Calgary AB T2P 0A0"],
        },
    },
]


# --------------------------------------------------------------------------- formatting

def num(value, decimals=2, thousands=",", point="."):
    d = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    whole, _, frac = f"{abs(d):f}".partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    out = thousands.join(groups)
    return sign + out + (point + frac if decimals else "")


def qty(value, point="."):
    return (f"{value:g}").replace(".", point)


MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
           "octobre", "novembre", "décembre"],
    "nl": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september",
           "oktober", "november", "december"],
    "hu": ["január", "február", "március", "április", "május", "június", "július", "augusztus",
           "szeptember", "október", "november", "december"],
}


def ymd(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return y, m, d


def d_long(iso, lang):                    # 3 novembre 2026 / 9 november 2026 / 5 November 2026
    y, m, d = ymd(iso)
    return f"{d} {MONTHS[lang][m - 1]} {y}"


def d_us_long(iso):                       # November 5, 2026
    y, m, d = ymd(iso)
    return f"{MONTHS['en'][m - 1]} {d}, {y}"


def d_us_short(iso):                      # Nov 3, 2026
    y, m, d = ymd(iso)
    return f"{MONTHS['en'][m - 1][:3]} {d}, {y}"


def d_hu(iso):                            # 2026. november 3.
    y, m, d = ymd(iso)
    return f"{y}. {MONTHS['hu'][m - 1]} {d}."


def d_num(iso, sep):                      # 04/11/2026 or 03.11.2026
    y, m, d = ymd(iso)
    return f"{d:02d}{sep}{m:02d}{sep}{y}"


def d_short_en(iso):                      # 19 Nov 2026
    y, m, d = ymd(iso)
    return f"{d} {MONTHS['en'][m - 1][:3]} {y}"


def iban_print(iban):
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))


def pct(rate, point="."):
    return f"{rate:g}".replace(".", point)


# --------------------------------------------------------------------------- drawing helpers

def find_font(*candidates):
    for c in candidates:
        if Path(c).exists():
            return c
    raise SystemExit(f"Need a TTF with Hungarian glyphs (ő, ű); none of {candidates} found.")


pdfmetrics.registerFont(TTFont("DejaVu", find_font(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/DejaVuSans.ttf",
    "/opt/homebrew/share/fonts/DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", find_font(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/Library/Fonts/DejaVuSans-Bold.ttf",
    "/opt/homebrew/share/fonts/DejaVuSans-Bold.ttf")))


class Pen:
    """Thin wrapper over a reportlab canvas: text in points from the top-left corner."""

    def __init__(self, path, pagesize=A4, regular="Helvetica", bold="Helvetica-Bold", title=""):
        self.c = canvas.Canvas(str(path), pagesize=pagesize)
        self.c.setTitle(f"{title} (fictional sample)")
        self.c.setAuthor("Fictional sample generator")
        self.w, self.h = pagesize
        self.regular, self.bold = regular, bold

    def text(self, x, y, s, size=9.5, bold=False, align="left", color=colors.black):
        c = self.c
        c.setFillColor(color)
        c.setFont(self.bold if bold else self.regular, size)
        yy = self.h - y
        if align == "left":
            c.drawString(x, yy, s)
        elif align == "right":
            c.drawRightString(x, yy, s)
        else:
            c.drawCentredString(x, yy, s)
        c.setFillColor(colors.black)

    def lines(self, x, y, items, size=9.5, gap=13, bold_first=False, align="left"):
        for i, s in enumerate(items):
            self.text(x, y + i * gap, s, size, bold=bold_first and i == 0, align=align)
        return y + len(items) * gap

    def rect(self, x, y, w, h, fill=None, stroke=None, width=0.6):
        c = self.c
        if fill is not None:
            c.setFillColor(fill)
        if stroke is not None:
            c.setStrokeColor(stroke)
        c.setLineWidth(width)
        c.rect(x, self.h - y - h, w, h, fill=fill is not None, stroke=stroke is not None)
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)

    def hline(self, x1, x2, y, color=colors.grey, width=0.5):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.line(x1, self.h - y, x2, self.h - y)
        self.c.setStrokeColor(colors.black)

    def table(self, x, y, cols, rows, header_fill=colors.HexColor("#333333"), header_color=colors.white,
              size=9, row_h=16, zebra=None, grid=False):
        """cols: [(header, width, align)]. Returns y below the table."""
        total_w = sum(w for _, w, _ in cols)
        self.rect(x, y, total_w, row_h, fill=header_fill)
        self._row(x, y, cols, [h for h, _, _ in cols], size, row_h, bold=True, color=header_color)
        y += row_h
        for i, r in enumerate(rows):
            if zebra and i % 2:
                self.rect(x, y, total_w, row_h, fill=zebra)
            self._row(x, y, cols, r, size, row_h)
            y += row_h
            if grid:
                self.hline(x, x + total_w, y, colors.lightgrey)
        return y

    def _row(self, x, y, cols, cells, size, row_h, bold=False, color=colors.black):
        cx = x
        for (_, w, align), cell in zip(cols, cells):
            base = y + row_h - 4.5
            if align == "right":
                self.text(cx + w - 4, base, cell, size, bold, "right", color)
            elif align == "center":
                self.text(cx + w / 2, base, cell, size, bold, "center", color)
            else:
                self.text(cx + 4, base, cell, size, bold, "left", color)
            cx += w

    def footer(self, extra=""):
        self.text(self.w / 2, self.h - 22, FICTIONAL + extra, 7, align="center", color=colors.grey)

    def save(self):
        self.c.showPage()
        self.c.save()


# --------------------------------------------------------------------------- renderers

def r_fr(inv, pr, path):
    """French: TVA 20%, SIRET, long French dates, space thousands + comma decimals, serif font."""
    eur = lambda v: num(v, 2, " ", ",") + " €"  # noqa: E731
    p = Pen(path, A4, "Times-Roman", "Times-Bold", inv["invoice_number"])
    p.text(50, 70, inv["vendor_name"], 20, bold=True)
    p.lines(50, 90, pr["vendor_lines"], 10)
    p.text(545, 70, "FACTURE", 22, bold=True, align="right", color=colors.HexColor("#1d3c78"))
    p.lines(545, 92, [f"N° {inv['invoice_number']}", f"Date : {d_long(inv['issue_date'], 'fr')}",
                      f"Échéance : {d_long(inv['due_date'], 'fr')}"], 10, align="right")
    p.text(320, 160, "Client", 10, bold=True)
    p.lines(320, 175, [inv["customer_name"], *pr["customer_lines"]], 10)
    rows = [[i["description"], qty(i["quantity"], ","), eur(i["unit_price"]), eur(i["line_total"])]
            for i in inv["line_items"]]
    y = p.table(50, 240, [("Désignation", 245, "left"), ("Qté", 50, "right"), ("Prix unitaire HT", 100, "right"),
                          ("Montant HT", 100, "right")], rows, colors.HexColor("#1d3c78"), size=10, row_h=18,
                grid=True)
    y += 20
    for label, val, b in [("Total HT", inv["subtotal"], False),
                          (f"TVA {pct(inv['tax_rate_percent'])} %", inv["tax_amount"], False),
                          ("Total TTC", inv["total"], True)]:
        p.text(440, y, label, 11, bold=b, align="right")
        p.text(545, y, eur(val), 11, bold=b, align="right")
        y += 16
    pm = inv["payment"]
    p.lines(50, y + 30, ["Règlement par virement :", f"{pm['bank_name']}",
                         f"IBAN {iban_print(pm['iban'])} · BIC {pm['bic_swift']}",
                         "En cas de retard, pénalités au taux légal en vigueur."], 9.5)
    p.footer()
    p.save()


def r_es(inv, pr, path):
    """Spanish: IVA 21%, NIF, dd/mm/yyyy, '30 días fecha factura', dot thousands + comma decimals."""
    eur = lambda v: num(v, 2, ".", ",") + " €"  # noqa: E731
    p = Pen(path, A4, title=inv["invoice_number"])
    p.rect(0, 0, p.w, 8, fill=colors.HexColor("#c0392b"))
    p.text(50, 60, inv["vendor_name"], 17, bold=True)
    p.lines(50, 78, pr["vendor_lines"], 9)
    p.rect(330, 45, 215, 70, stroke=colors.HexColor("#c0392b"))
    p.lines(340, 62, ["FACTURA", f"Número: {inv['invoice_number']}", f"Fecha: {d_num(inv['issue_date'], '/')}",
                      "Vencimiento: 30 días fecha factura"], 9.5, gap=14, bold_first=True)
    p.text(50, 140, "Datos del cliente", 9, bold=True, color=colors.HexColor("#c0392b"))
    p.lines(50, 155, [inv["customer_name"], *pr["customer_lines"], "NIF: B00000099"], 9.5)
    rows = [[i["description"], qty(i["quantity"], ","), eur(i["unit_price"]), eur(i["line_total"])]
            for i in inv["line_items"]]
    y = p.table(50, 230, [("Concepto", 235, "left"), ("Cantidad", 60, "right"), ("Precio", 100, "right"),
                          ("Importe", 100, "right")], rows, colors.HexColor("#c0392b"), zebra=colors.HexColor("#f6e3e1"))
    y += 18
    for label, val, b in [("Base imponible", inv["subtotal"], False),
                          (f"IVA ({pct(inv['tax_rate_percent'])} %)", inv["tax_amount"], False),
                          ("TOTAL FACTURA", inv["total"], True)]:
        p.text(400, y, label, 10, bold=b, align="right")
        p.text(545, y, eur(val), 10, bold=b, align="right")
        y += 15
    pm = inv["payment"]
    p.lines(50, y + 30, ["Forma de pago: transferencia bancaria", pm["bank_name"],
                         f"IBAN: {iban_print(pm['iban'])}   BIC: {pm['bic_swift']}"], 9)
    p.footer()
    p.save()


def r_hu(inv, pr, path):
    """Hungarian: HUF without decimals, space thousands, 27% ÁFA, three different dates, net and gross columns."""
    ft = lambda v: num(v, 0, " ") + " Ft"  # noqa: E731
    p = Pen(path, A4, "DejaVu", "DejaVu-Bold", inv["invoice_number"])
    p.text(297, 50, "SZÁMLA", 18, bold=True, align="center")
    p.text(297, 66, f"Sorszám: {inv['invoice_number']}", 10, align="center")
    p.rect(40, 85, 255, 95, stroke=colors.black)
    p.rect(300, 85, 255, 95, stroke=colors.black)
    p.text(48, 100, "Eladó", 8.5, bold=True)
    p.lines(48, 116, [inv["vendor_name"], *pr["vendor_lines"]], 9, bold_first=True)
    p.text(308, 100, "Vevő", 8.5, bold=True)
    p.lines(308, 116, [inv["customer_name"], *pr["customer_lines"], "Adószám: 00000099-1-08"], 9, bold_first=True)
    pm = inv["payment"]
    y = 198
    for label, val in [("Fizetési mód", "átutalás"), ("Számla kelte", d_hu(inv["issue_date"])),
                       ("Teljesítés dátuma", d_hu(pr["fulfilment_date"])),
                       ("Fizetési határidő", d_hu(inv["due_date"]))]:
        p.text(48, y, label + ":", 9)
        p.text(160, y, val, 9, bold=True)
        y += 13
    rate = inv["tax_rate_percent"]
    rows = []
    for i in inv["line_items"]:
        vat = (Decimal(str(i["line_total"])) * Decimal(rate) / 100).quantize(Decimal(1), ROUND_HALF_UP)
        rows.append([i["description"], qty(i["quantity"]), "db", num(i["unit_price"], 0, " "),
                     num(i["line_total"], 0, " "), f"{rate}%", num(vat, 0, " "),
                     num(Decimal(str(i["line_total"])) + vat, 0, " ")])
    y = p.table(40, y + 12, [("Megnevezés", 150, "left"), ("Menny.", 36, "right"), ("Egys.", 30, "center"),
                             ("Nettó egységár", 72, "right"), ("Nettó érték", 60, "right"), ("ÁFA", 30, "right"),
                             ("ÁFA érték", 54, "right"), ("Bruttó érték", 63, "right")],
                rows, colors.HexColor("#e6e6e6"), colors.black, size=7.5, grid=True)
    y += 20
    for label, val, b in [("Nettó összesen:", inv["subtotal"], False), (f"ÁFA ({rate}%):", inv["tax_amount"], False),
                          ("Fizetendő végösszeg:", inv["total"], True)]:
        p.text(430, y, label, 10, bold=b, align="right")
        p.text(555, y, ft(val), 10, bold=b, align="right")
        y += 15
    p.lines(40, y + 25, [f"Bankszámlaszám: {pm['account_number']} ({pm['bank_name']})",
                         f"IBAN: {iban_print(pm['iban'])}   SWIFT: {pm['bic_swift']}",
                         "Késedelmes fizetés esetén a Ptk. szerinti késedelmi kamatot számítjuk fel."], 9)
    p.footer()
    p.save()


def r_it(inv, pr, path):
    """Italian: IVA 22%, Partita IVA, dd/mm/yyyy, vendor block right-aligned, customer top-left."""
    eur = lambda v: "€ " + num(v, 2, ".", ",")  # noqa: E731
    p = Pen(path, A4, "Times-Roman", "Times-Bold", inv["invoice_number"])
    p.text(545, 60, inv["vendor_name"], 16, bold=True, align="right", color=colors.HexColor("#2e6b3a"))
    p.lines(545, 78, [*pr["vendor_lines"], "Cod. destinatario SDI: 0000000"], 9.5, align="right")
    p.text(50, 140, "Spett.le", 9.5)
    p.lines(50, 154, [inv["customer_name"], *pr["customer_lines"]], 10.5, bold_first=True)
    p.text(50, 225, f"FATTURA n. {inv['invoice_number']} del {d_num(inv['issue_date'], '/')}", 13, bold=True)
    rows = [[i["description"], qty(i["quantity"], ","), eur(i["unit_price"]), eur(i["line_total"]),
             f"{pct(inv['tax_rate_percent'])}"] for i in inv["line_items"]]
    y = p.table(50, 245, [("Descrizione", 210, "left"), ("Q.tà", 45, "right"), ("Prezzo unit.", 85, "right"),
                          ("Importo", 85, "right"), ("IVA %", 70, "right")], rows,
                colors.HexColor("#2e6b3a"), size=10, row_h=18, grid=True)
    y += 20
    p.rect(330, y - 12, 215, 58, stroke=colors.HexColor("#2e6b3a"))
    for label, val, b in [("Imponibile", inv["subtotal"], False),
                          (f"IVA {pct(inv['tax_rate_percent'])}%", inv["tax_amount"], False),
                          ("Totale documento", inv["total"], True)]:
        p.text(340, y, label, 10.5, bold=b)
        p.text(538, y, eur(val), 10.5, bold=b, align="right")
        y += 17
    pm = inv["payment"]
    p.lines(50, y + 30, [f"Modalità di pagamento: bonifico bancario, scadenza {d_num(inv['due_date'], '/')}",
                         f"{pm['bank_name']} - IBAN {iban_print(pm['iban'])} - BIC {pm['bic_swift']}"], 9.5)
    p.footer()
    p.save()


def r_us(inv, pr, path):
    """US: Letter size, comma thousands, 'Nov 3, 2026' dates, licence number that is not a tax ID."""
    usd = lambda v: "$" + num(v)  # noqa: E731
    p = Pen(path, LETTER, title=inv["invoice_number"])
    p.text(40, 55, inv["vendor_name"].upper(), 15, bold=True)
    p.lines(40, 72, [*pr["vendor_lines"], "(555) 010-0199 · billing@example.com"], 9)
    p.text(572, 55, "INVOICE", 26, bold=True, align="right", color=colors.HexColor("#8a1c1c"))
    y = 85
    for label, val in [("Invoice #", inv["invoice_number"]), ("Date", d_us_short(inv["issue_date"])),
                       ("Due", d_us_short(inv["due_date"])), ("Job", "Building B rooftop")]:
        p.text(490, y, label, 9, bold=True, align="right")
        p.text(572, y, val, 9, align="right")
        y += 13
    p.text(40, 150, "BILL TO", 9, bold=True, color=colors.HexColor("#8a1c1c"))
    p.lines(40, 164, [inv["customer_name"], *pr["customer_lines"]], 10)
    rows = [[i["description"], qty(i["quantity"]), usd(i["unit_price"]), usd(i["line_total"])]
            for i in inv["line_items"]]
    y = p.table(40, 225, [("DESCRIPTION", 270, "left"), ("QTY", 50, "right"), ("RATE", 90, "right"),
                          ("AMOUNT", 122, "right")], rows, colors.HexColor("#8a1c1c"), zebra=colors.HexColor("#f4eded"),
                row_h=18)
    y += 18
    for label, val, b in [("Subtotal", inv["subtotal"], False),
                          (f"Sales tax ({pct(inv['tax_rate_percent'])}%)", inv["tax_amount"], False),
                          ("TOTAL DUE", inv["total"], True)]:
        p.text(470, y, label, 10, bold=b, align="right")
        p.text(572, y, usd(val), 10, bold=b, align="right")
        y += 15
    pm = inv["payment"]
    p.lines(40, y + 30, ["Remit by ACH or wire:", f"{pm['bank_name']} · Routing {pm['routing_or_sort_code']} · "
                                                  f"Account {pm['account_number']}",
                         "Thank you for your business!"], 9)
    p.footer()
    p.save()


def r_uk(inv, pr, path):
    """UK: dd/mm/yyyy where day <= 12 for both dates and a service period, so month order matters."""
    gbp = lambda v: "£" + num(v)  # noqa: E731
    p = Pen(path, A4, title=inv["invoice_number"])
    p.text(50, 60, inv["vendor_name"], 16, bold=True, color=colors.HexColor("#4a3b6b"))
    p.lines(50, 77, pr["vendor_lines"], 9)
    p.text(545, 60, "VAT INVOICE", 13, bold=True, align="right")
    y = 78
    for label, val in [("Invoice no.", inv["invoice_number"]), ("Invoice date", d_num(inv["issue_date"], "/")),
                       ("Tax point", d_num(inv["issue_date"], "/")), ("Due date", d_num(inv["due_date"], "/"))]:
        p.text(400, y, label, 9)
        p.text(545, y, val, 9, bold=True, align="right")
        y += 13
    p.text(50, 140, "Invoice to:", 9, bold=True)
    p.lines(50, 154, [inv["customer_name"], *pr["customer_lines"]], 9.5)
    a, b = pr["period"]
    p.text(50, 210, f"Services for the period {d_num(a, '/')} to {d_num(b, '/')}", 9.5)
    rows = [[i["description"], qty(i["quantity"]), gbp(i["unit_price"]), gbp(i["line_total"])]
            for i in inv["line_items"]]
    y = p.table(50, 222, [("Description", 250, "left"), ("Qty", 55, "right"), ("Unit price", 90, "right"),
                          ("Net", 100, "right")], rows, colors.HexColor("#4a3b6b"), grid=True)
    y += 18
    for label, val, bb in [("Total net", inv["subtotal"], False),
                           (f"VAT @ {pct(inv['tax_rate_percent'])}%", inv["tax_amount"], False),
                           ("Total payable", inv["total"], True)]:
        p.text(440, y, label, 10, bold=bb, align="right")
        p.text(545, y, gbp(val), 10, bold=bb, align="right")
        y += 15
    pm = inv["payment"]
    p.lines(50, y + 30, ["BACS payment details", f"Bank: {pm['bank_name']}",
                         f"Sort code: {pm['routing_or_sort_code']}   Account no.: {pm['account_number']}",
                         f"Please quote {inv['invoice_number']} as your reference."], 9)
    p.footer()
    p.save()


def r_ie_two_column(inv, pr, path):
    """Two columns; the amount due and the net/VAT/total summary sit at the TOP, items come last."""
    eur = lambda v: "€" + num(v)  # noqa: E731
    p = Pen(path, A4, title=inv["invoice_number"])
    accent = colors.HexColor("#0f6e6e")
    p.rect(0, 0, 230, p.h, fill=colors.HexColor("#eef5f5"))
    # left column: who
    p.text(30, 60, inv["vendor_name"], 13, bold=True, color=accent)
    p.lines(30, 78, pr["vendor_lines"], 8.5, gap=12)
    p.text(30, 150, "BILLED TO", 8, bold=True, color=accent)
    p.lines(30, 163, [inv["customer_name"], *pr["customer_lines"]], 9, gap=12)
    p.text(30, 230, "INVOICE NO.", 8, bold=True, color=accent)
    p.text(30, 243, inv["invoice_number"], 10)
    p.text(30, 265, "ISSUED", 8, bold=True, color=accent)
    p.text(30, 278, d_long(inv["issue_date"], "en"), 10)
    pm = inv["payment"]
    p.text(30, 310, "PAYMENT", 8, bold=True, color=accent)
    p.lines(30, 323, [pm["bank_name"], "IBAN", iban_print(pm["iban"]), f"BIC {pm['bic_swift']}"], 8.5, gap=12)
    # right column: money first
    p.text(255, 60, "Invoice", 26, bold=True)
    p.rect(255, 80, 300, 70, fill=accent)
    p.text(270, 100, "AMOUNT DUE", 9, bold=True, color=colors.white)
    p.text(540, 132, eur(inv["total"]), 24, bold=True, align="right", color=colors.white)
    p.text(270, 142, f"by {d_long(inv['due_date'], 'en')}", 9, color=colors.white)
    y = 175
    for label, val, b in [("Net", inv["subtotal"], False),
                          (f"VAT {pct(inv['tax_rate_percent'])}%", inv["tax_amount"], False),
                          ("Total", inv["total"], True)]:
        p.text(255, y, label, 10, bold=b)
        p.text(555, y, eur(val), 10, bold=b, align="right")
        p.hline(255, 555, y + 5, colors.lightgrey)
        y += 17
    p.text(255, 250, "Details", 11, bold=True)
    rows = [[i["description"], qty(i["quantity"]), eur(i["unit_price"]), eur(i["line_total"])]
            for i in inv["line_items"]]
    p.table(255, 260, [("Item", 140, "left"), ("Qty", 35, "right"), ("Price", 60, "right"), ("Amount", 65, "right")],
            rows, accent, size=8.5, grid=True)
    p.footer()
    p.save()


def r_au_banner(inv, pr, path):
    """A big TAX INVOICE banner and a logo/brand mark come before the legal vendor name. '$' means AUD."""
    aud = lambda v: "$" + num(v)  # noqa: E731
    p = Pen(path, A4, title=inv["invoice_number"])
    c = p.c
    p.rect(0, 0, p.w, 95, fill=colors.HexColor("#f2a900"))
    p.text(297, 68, "TAX INVOICE", 44, bold=True, align="center", color=colors.white)
    # logo: a ring and a bold brand word with a tagline
    c.setStrokeColor(colors.HexColor("#1b1b1b"))
    c.setLineWidth(5)
    c.circle(78, p.h - 150, 26, stroke=1, fill=0)
    c.setLineWidth(3)
    c.line(62, p.h - 160, 94, p.h - 140)
    c.line(62, p.h - 140, 94, p.h - 160)
    p.text(118, 162, pr["brand"], 36, bold=True)
    p.text(120, 178, pr["tagline"], 9, color=colors.grey)
    p.text(50, 220, inv["vendor_name"], 11, bold=True)
    p.lines(50, 234, pr["vendor_lines"], 9)
    y = 125
    for label, val in [("Invoice", inv["invoice_number"]), ("Date", d_long(inv["issue_date"], "en")),
                       ("Terms", "14 days"), ("Currency", "All amounts in AUD")]:
        p.text(400, y, label, 9, bold=True)
        p.text(545, y, val, 9, align="right")
        y += 13
    p.text(330, 220, "Bill to", 9, bold=True)
    p.lines(330, 234, [inv["customer_name"], *pr["customer_lines"]], 9)
    rows = [[i["description"], qty(i["quantity"]), aud(i["unit_price"]), aud(i["line_total"])]
            for i in inv["line_items"]]
    y = p.table(50, 290, [("Description", 245, "left"), ("Qty", 50, "right"), ("Unit (ex GST)", 100, "right"),
                          ("Amount (ex GST)", 100, "right")], rows, colors.HexColor("#1b1b1b"), grid=True)
    y += 18
    for label, val, b in [("Subtotal (ex GST)", inv["subtotal"], False),
                          (f"GST {pct(inv['tax_rate_percent'])}%", inv["tax_amount"], False),
                          ("Total (inc GST)", inv["total"], True)]:
        p.text(440, y, label, 10, bold=b, align="right")
        p.text(545, y, aud(val), 10, bold=b, align="right")
        y += 15
    pm = inv["payment"]
    p.lines(50, y + 30, ["Direct deposit", f"{pm['bank_name']} · BSB {pm['routing_or_sort_code']} · "
                                           f"Account {pm['account_number']}"], 9)
    p.footer()
    p.save()


def r_ch_two_page(inv, pr, path):
    """Two pages: line items run onto page 2, with carried/brought-forward rows that are NOT line items."""
    chf = lambda v: num(v, 2, "'", ".")  # noqa: E731
    p = Pen(path, A4, title=inv["invoice_number"])
    cols = [("Pos.", 30, "right"), ("Article", 255, "left"), ("Qty", 40, "right"), ("Unit CHF", 80, "right"),
            ("Amount CHF", 90, "right")]
    items = inv["line_items"]
    br = pr["page_break_after"]
    rows = [[str(n), i["description"], qty(i["quantity"]), chf(i["unit_price"]), chf(i["line_total"])]
            for n, i in enumerate(items, start=1)]
    carried = sum(Decimal(str(i["line_total"])) for i in items[:br])
    accent = colors.HexColor("#b3122e")

    def header(page):
        p.text(50, 55, inv["vendor_name"], 15, bold=True, color=accent)
        p.lines(50, 72, pr["vendor_lines"], 8.5, gap=11)
        p.text(545, 55, f"Invoice {inv['invoice_number']}", 11, bold=True, align="right")
        p.text(545, 70, f"Page {page} of 2", 8.5, align="right")

    header(1)
    p.text(330, 115, "Invoice address", 8.5, bold=True)
    p.lines(330, 128, [inv["customer_name"], *pr["customer_lines"]], 9.5, gap=12)
    y = 115
    for label, val in [("Invoice date", d_num(inv["issue_date"], ".")), ("Your order", "PO-SB-0042"),
                       ("Customer no.", "10077")]:
        p.text(50, y, label, 8.5)
        p.text(140, y, val, 8.5)
        y += 12
    y = p.table(50, 185, cols, rows[:br], accent, size=8.5, row_h=17, zebra=colors.HexColor("#f7f1f2"))
    p.hline(50, 545, y + 3, colors.black)
    p.text(410, y + 16, "Carried forward", 9, bold=True, align="right")
    p.text(541, y + 16, chf(carried), 9, bold=True, align="right")
    p.text(545, y + 40, "continued on page 2", 8, align="right", color=colors.grey)
    p.footer()
    p.c.showPage()

    header(2)
    p.text(410, 110, "Brought forward", 9, bold=True, align="right")
    p.text(541, 110, chf(carried), 9, bold=True, align="right")
    y = p.table(50, 120, cols, rows[br:], accent, size=8.5, row_h=17, zebra=colors.HexColor("#f7f1f2"))
    y += 20
    for label, val, b in [("Total net", inv["subtotal"], False),
                          (f"VAT {pct(inv['tax_rate_percent'])}%", inv["tax_amount"], False),
                          ("Total CHF", inv["total"], True)]:
        p.text(410, y, label, 10, bold=b, align="right")
        p.text(541, y, chf(val), 10, bold=b, align="right")
        y += 15
    pm = inv["payment"]
    p.lines(50, y + 30, ["Terms: payable within 30 days net.", f"{pm['bank_name']} · IBAN {iban_print(pm['iban'])} "
                                                               f"· BIC {pm['bic_swift']}"], 9)
    p.footer()
    p.save()


def r_nz_odd_labels(inv, pr, path):
    """Labels nobody would guess: 'Prepared by', 'Invoiced party', 'Raised', 'Settle by', 'Amount payable'."""
    nzd = lambda v: "NZ$" + num(v)  # noqa: E731
    p = Pen(path, A4, "Courier", "Courier-Bold", inv["invoice_number"])
    p.text(50, 60, "STATEMENT OF WORK COMPLETED / TAX INVOICE", 12, bold=True)
    p.hline(50, 545, 68, colors.black, 1)
    kv = [("Prepared by", inv["vendor_name"]), ("", pr["vendor_lines"][0]), ("", pr["vendor_lines"][1]),
          ("Invoiced party", inv["customer_name"]), ("", ", ".join(pr["customer_lines"])),
          ("Document reference", inv["invoice_number"]), ("Raised", d_short_en(inv["issue_date"])),
          ("Settle by", d_short_en(inv["due_date"]))]
    y = 90
    for label, val in kv:
        p.text(50, y, label, 9.5, bold=True)
        p.text(200, y, val, 9.5)
        y += 14
    rows = [[i["description"], qty(i["quantity"]), num(i["unit_price"]), num(i["line_total"])]
            for i in inv["line_items"]]
    y = p.table(50, y + 15, [("Particulars", 255, "left"), ("Count", 50, "right"), ("Each", 90, "right"),
                             ("Extended", 100, "right")], rows, colors.white, colors.black, size=9, grid=True)
    p.hline(50, 545, y - len(rows) * 16, colors.black, 1)
    y += 18
    for label, val, b in [("Value before GST", inv["subtotal"], False),
                          (f"GST component @ {pct(inv['tax_rate_percent'])}%", inv["tax_amount"], False),
                          ("Amount payable", inv["total"], True)]:
        p.text(400, y, label, 9.5, bold=b, align="right")
        p.text(545, y, nzd(val), 9.5, bold=b, align="right")
        y += 15
    pm = inv["payment"]
    p.lines(50, y + 30, [f"Deposit to {pm['bank_name']} account {pm['account_number']}",
                         f"Use {inv['invoice_number']} as the particulars."], 9)
    p.footer()
    p.save()


def r_nl(inv, pr, path):
    """Dutch: BTW 21% with a deliberately wrong tax amount; KvK number printed next to the VAT id."""
    eur = lambda v: "€ " + num(v, 2, ".", ",")  # noqa: E731
    p = Pen(path, A4, title=inv["invoice_number"])
    accent = colors.HexColor("#e05a00")
    p.text(50, 60, inv["vendor_name"], 15, bold=True)
    p.lines(50, 77, pr["vendor_lines"], 9)
    p.text(545, 60, "FACTUUR", 20, bold=True, align="right", color=accent)
    p.lines(50, 130, [inv["customer_name"], "t.a.v. de praktijkmanager", *pr["customer_lines"]], 10)
    y = 130
    for label, val in [("Factuurnummer", inv["invoice_number"]), ("Factuurdatum", d_long(inv["issue_date"], "nl")),
                       ("Vervaldatum", d_long(inv["due_date"], "nl")), ("Klantnummer", "D-0381")]:
        p.text(350, y, label, 9)
        p.text(545, y, val, 9, align="right")
        y += 13
    rows = [[i["description"], qty(i["quantity"], ","), eur(i["unit_price"]), eur(i["line_total"])]
            for i in inv["line_items"]]
    y = p.table(50, 215, [("Omschrijving", 245, "left"), ("Aantal", 55, "right"), ("Prijs", 95, "right"),
                          ("Bedrag", 100, "right")], rows, accent, grid=True)
    y += 18
    for label, val, b in [("Subtotaal", inv["subtotal"], False),
                          (f"BTW {pct(inv['tax_rate_percent'])}%", inv["tax_amount"], False),
                          ("Totaal te betalen", inv["total"], True)]:
        p.text(430, y, label, 10, bold=b, align="right")
        p.text(545, y, eur(val), 10, bold=b, align="right")
        y += 15
    pm = inv["payment"]
    p.lines(50, y + 30, [f"Gelieve het totaalbedrag vóór {d_long(inv['due_date'], 'nl')} over te maken op",
                         f"{iban_print(pm['iban'])} (BIC {pm['bic_swift']}, {pm['bank_name']}) "
                         f"o.v.v. {inv['invoice_number']}."], 9)
    p.footer()
    p.save()


def r_ca(inv, pr, path):
    """Canadian: the customer name contains a comma and an ampersand; due date only as 'Net 15'."""
    cad = lambda v: "$" + num(v)  # noqa: E731
    p = Pen(path, LETTER, title=inv["invoice_number"])
    accent = colors.HexColor("#234e8c")
    p.text(40, 55, inv["vendor_name"], 16, bold=True, color=accent)
    p.lines(40, 72, pr["vendor_lines"], 9)
    p.rect(40, 115, 250, 70, stroke=accent)
    p.text(50, 130, "BILL TO", 8.5, bold=True, color=accent)
    p.lines(50, 144, [inv["customer_name"], *pr["customer_lines"]], 9.5, bold_first=True)
    p.rect(322, 115, 250, 70, stroke=accent)
    y = 130
    for label, val in [("Invoice No.", inv["invoice_number"]), ("Invoice Date", d_us_long(inv["issue_date"])),
                       ("Terms", "Net 15"), ("Currency", "CAD")]:
        p.text(332, y, label, 9, bold=True)
        p.text(562, y, val, 9, align="right")
        y += 13
    rows = [[i["description"], qty(i["quantity"]), cad(i["unit_price"]), cad(i["line_total"])]
            for i in inv["line_items"]]
    y = p.table(40, 210, [("Description", 270, "left"), ("Qty", 50, "right"), ("Unit Price", 100, "right"),
                          ("Line Total", 112, "right")], rows, accent, zebra=colors.HexColor("#eaf0f8"))
    y += 18
    for label, val, b in [("Subtotal", inv["subtotal"], False),
                          (f"GST {pct(inv['tax_rate_percent'])}%", inv["tax_amount"], False),
                          ("Balance Due (CAD)", inv["total"], True)]:
        p.text(470, y, label, 10, bold=b, align="right")
        p.text(572, y, cad(val), 10, bold=b, align="right")
        y += 15
    pm = inv["payment"]
    p.lines(40, y + 30, ["EFT payment:", f"{pm['bank_name']} · Routing no. {pm['routing_or_sort_code']} · "
                                         f"Account {pm['account_number']}",
                         f"Questions? Quote {inv['invoice_number']}."], 9)
    p.footer()
    p.save()


RENDER = {
    "h01-fr-tva": r_fr, "h02-es-iva": r_es, "h03-hu-afa": r_hu, "h04-it-iva": r_it, "h05-us-commas": r_us,
    "h06-uk-ddmm": r_uk, "h07-two-column-totals-top": r_ie_two_column, "h08-banner-logo": r_au_banner,
    "h09-two-page": r_ch_two_page, "h10-odd-labels": r_nz_odd_labels, "h11-vat-error": r_nl,
    "h12-comma-customer": r_ca,
}


# --------------------------------------------------------------------------- self-check

def check(entry):
    """The data must be internally consistent, except for the one deliberate tax error."""
    inv = Invoice.model_validate(entry["invoice"])
    issues = validate_invoice(inv)
    if entry["print"].get("deliberate_tax_error"):
        assert len(issues) == 1 and "but tax amount is" in issues[0], (entry["name"], issues)
    else:
        assert issues == [], (entry["name"], issues)


# --------------------------------------------------------------------------- phone photos

def _solve(a, b):
    """Gaussian elimination for the 8x8 perspective system (no numpy dependency)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][n] / m[i][i] for i in range(n)]


def _perspective_coeffs(dst, src):
    """Coefficients for PIL's PERSPECTIVE transform mapping output points dst -> input points src."""
    a, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    return _solve(a, b)


def phone_shot(page, rng):
    """Make a rendered page look like a hand-held phone photo of paper on a desk."""
    page = ImageChops.multiply(page, Image.new("RGB", page.size, (246, 242, 233)))  # off-white paper
    w, h = page.size
    cw, ch = int(w * 1.24), int(h * 1.16)
    # desk: warm grey-brown with blotchy texture
    desk = Image.new("RGB", (cw, ch), (104, 86, 70))
    blotch = Image.effect_noise((cw // 16, ch // 16), 40).resize((cw, ch), Image.BICUBIC)
    desk = Image.composite(desk, Image.new("RGB", (cw, ch), (126, 106, 86)), blotch)

    # page corners after a tilted, slightly rotated hand-held shot (top edge further away = narrower)
    x0, y0 = (cw - w) / 2, (ch - h) / 2
    inset = rng.uniform(0.035, 0.06) * w
    skew = rng.uniform(-0.02, 0.02) * w
    quad = [(x0 + inset + skew, y0 + 0.02 * h), (x0 + w - inset * 0.7 + skew, y0 + 0.01 * h),
            (x0 + w + 0.012 * w, y0 + h - 0.005 * h), (x0 - 0.01 * w, y0 + h)]
    ang = math.radians(rng.uniform(-3.2, 3.2))
    cx, cy = cw / 2, ch / 2
    quad = [(cx + (x - cx) * math.cos(ang) - (y - cy) * math.sin(ang) + rng.uniform(-6, 6),
             cy + (x - cx) * math.sin(ang) + (y - cy) * math.cos(ang) + rng.uniform(-6, 6)) for x, y in quad]
    coeffs = _perspective_coeffs(quad, [(0, 0), (w, 0), (w, h), (0, h)])
    warped = page.transform((cw, ch), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    mask = Image.new("L", (w, h), 255).transform((cw, ch), Image.PERSPECTIVE, coeffs, Image.BICUBIC)

    # soft drop shadow of the sheet on the desk
    shadow = ImageChops.offset(mask, 10, 14).filter(ImageFilter.GaussianBlur(14))
    desk = Image.composite(Image.new("RGB", (cw, ch), (52, 42, 34)), desk, shadow.point(lambda v: int(v * 0.7)))
    img = Image.composite(warped, desk, mask)

    # uneven light: bright near one corner, falling off across the sheet
    lx, ly = rng.choice([(0.1, 0.05), (0.9, 0.05), (0.15, 0.95), (0.85, 0.9)])  # where the lamp is
    small = Image.new("L", (64, 64))
    small.putdata([int(255 - 70 * min(1.0, math.hypot(i % 64 / 63 - lx, i // 64 / 63 - ly) / 1.2))
                   for i in range(64 * 64)])
    grad = small.resize((cw, ch), Image.BICUBIC)
    # a soft shadow band (the phone or a hand between lamp and paper)
    band = Image.new("L", (cw, ch), 255)
    d = ImageDraw.Draw(band)
    bx = rng.uniform(0.25, 0.6) * cw
    bw = rng.uniform(0.10, 0.16) * cw
    d.polygon([(bx, 0), (bx + bw, 0), (bx + bw - 0.35 * cw, ch), (bx - 0.35 * cw, ch)], fill=150)
    band = band.filter(ImageFilter.GaussianBlur(45))
    light = ImageChops.multiply(grad, band)
    tint = Image.merge("RGB", (light, light.point(lambda v: int(v * 0.97)), light.point(lambda v: int(v * 0.90))))
    img = ImageChops.multiply(img, tint)

    # optics and sensor: slight defocus, noise
    img = img.filter(ImageFilter.GaussianBlur(0.75))
    noise = Image.merge("RGB", [Image.effect_noise((cw, ch), 14) for _ in range(3)])
    img = Image.blend(img, noise, 0.05)
    return img


def make_photo(pdf, out, seed, dpi=110):
    if not shutil.which("pdftoppm"):
        raise SystemExit("pdftoppm (poppler-utils) is needed to build the phone photos.")
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), f"{tmp}/p"], check=True)
        c = canvas.Canvas(str(out))
        c.setTitle("Phone photo of a fictional sample invoice")
        for i, png in enumerate(sorted(Path(tmp).glob("p*.png"))):
            shot = phone_shot(Image.open(png).convert("RGB"), rng)
            jpg = Path(tmp) / f"shot{i}.jpg"
            shot.save(jpg, "JPEG", quality=55)
            pw, ph = shot.width * 72 / dpi, shot.height * 72 / dpi
            c.setPageSize((pw, ph))
            c.drawImage(str(jpg), 0, 0, pw, ph)  # JPEG embedded as-is; no text is drawn
            c.showPage()
        c.save()


# --------------------------------------------------------------------------- main

def main():
    for sub in ("invoices", "expected", "photos"):
        (HERE / sub).mkdir(parents=True, exist_ok=True)
    assert set(RENDER) == {e["name"] for e in INVOICES}
    for entry in INVOICES:
        check(entry)
        pdf = HERE / "invoices" / f"{entry['name']}.pdf"
        RENDER[entry["name"]](entry["invoice"], entry["print"], pdf)
        (HERE / "expected" / f"{entry['name']}.json").write_text(
            json.dumps(entry["invoice"], indent=2, ensure_ascii=False), encoding="utf-8")
        if entry["photo"]:
            make_photo(pdf, HERE / "photos" / f"{entry['name']}-photo.pdf", seed=entry["name"])
    n_photos = sum(e["photo"] for e in INVOICES)
    print(f"Wrote {len(INVOICES)} invoices, {len(INVOICES)} expected JSON files and {n_photos} photos to {HERE}")


if __name__ == "__main__":
    main()
