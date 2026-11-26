"""Rules-only invoice extraction: no language model, no network.

Text comes from the PDF text layer (pdfplumber) or, when there is none, from
tesseract OCR of a 300 dpi render (pdftoppm). Fields are filled by regular
expressions keyed on printed labels and by a simple layout rule for line items
(a line in the item block that ends in one to two money amounts, optionally
preceded by a quantity).

Usage:
    uv run --with pdfplumber --with pytesseract python bakeoff/rules/extract_rules.py \
        <pdf-dir> <out-dir> [--strip-suffix -scan]
"""

import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import pdfplumber
import pytesseract
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from claude_invoice_parser.schema import Invoice, LineItem, PaymentDetails  # noqa: E402

# ---------------------------------------------------------------- text sources


def text_layer(pdf: Path) -> str:
    with pdfplumber.open(pdf) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def ocr(pdf: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", str(pdf), f"{tmp}/p"], check=True)
        pages = sorted(Path(tmp).glob("p*.png"))
        # psm 6 = treat the page as one uniform block of text; keeps table rows on one line.
        return "\n".join(pytesseract.image_to_string(Image.open(p), lang="eng+deu", config="--psm 6") for p in pages)


def get_text(pdf: Path) -> tuple[str, str]:
    txt = text_layer(pdf)
    if len(txt.strip()) > 20:
        return txt, "text-layer"
    return ocr(pdf), "ocr"


def normalise(raw: str) -> list[str]:
    lines = []
    for line in raw.splitlines():
        line = line.replace("|", " ")            # OCR'd table borders
        line = re.sub(r"\s+[·•]\s+", " · ", line)
        line = re.sub(r"\s+-\s+", " · ", line)   # OCR reads the middle dot as a hyphen
        line = re.sub(r"\s{2,}", " ", line).strip()
        if line:
            lines.append(line)
    return lines


# ---------------------------------------------------------------- primitives

CUR_SYM = {"$": "USD", "€": "EUR", "£": "GBP"}
CUR_CODES = ("USD", "EUR", "GBP", "CHF", "CAD", "AUD")
# A money amount: optional sign, optional symbol/code, digits with , or . thousands, exactly 2 decimals.
MONEY = re.compile(
    r"(?P<sign>-)?(?:(?P<pre>[$€£])|(?P<code>USD|EUR|GBP|CHF)\s?)?(?P<sign2>-)?"
    r"(?P<num>\d{1,3}(?:[.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2})(?!\d)\s?(?P<post>€|EUR|USD|GBP)?"
)


def to_number(s: str) -> float:
    s = s.strip()
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
    elif "," in s:
        dec = "," if re.search(r",\d{1,2}$", s) else None
    elif "." in s:
        dec = "." if re.search(r"\.\d{1,2}$", s) else None
    else:
        dec = None
    thousands = {",", "."} - {dec}
    for t in thousands:
        s = s.replace(t, "")
    if dec:
        s = s.replace(dec, ".")
    return float(s)


def money_in(line: str) -> list[tuple[float, re.Match]]:
    out = []
    for m in MONEY.finditer(line):
        v = to_number(m["num"])
        if m["sign"] or m["sign2"]:
            v = -v
        out.append((v, m))
    return out


MONTHS = {
    m: i + 1
    for i, names in enumerate([
        ("january", "januar", "jan"), ("february", "februar", "feb"), ("march", "märz", "mar"),
        ("april", "apr"), ("may", "mai"), ("june", "juni", "jun"), ("july", "juli", "jul"),
        ("august", "aug"), ("september", "sept", "sep"), ("october", "oktober", "oct", "okt"),
        ("november", "nov"), ("december", "dezember", "dec", "dez"),
    ])
    for m in names
}
MONTH_RX = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_PATTERNS = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})"), lambda m: date(int(m[3]), int(m[2]), int(m[1]))),  # DMY
    (re.compile(rf"({MONTH_RX})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})", re.I),
     lambda m: date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))),
    (re.compile(rf"(\d{{1,2}})\.?\s+({MONTH_RX})\.?,?\s+(\d{{4}})", re.I),
     lambda m: date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))),
    # Slashed dates are ambiguous (US M/D vs EU D/M); assume D/M unless the first part > 12 is impossible.
    (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), lambda m: date(int(m[3]), int(m[2]), int(m[1]))),
]


def first_date(s: str) -> date | None:
    best = None
    for rx, build in DATE_PATTERNS:
        m = rx.search(s)
        if m and (best is None or m.start() < best[0]):
            try:
                best = (m.start(), build(m))
            except ValueError:
                pass
    return best[1] if best else None


def after_label(text: str, labels: str) -> str | None:
    """Text following a label up to the next field separator (· or end of line)."""
    m = re.search(rf"(?:{labels})\s*[:#]?\s*(.+?)(?:\s·\s|$)", text, re.I | re.M)
    return m[1].strip() if m else None


# ---------------------------------------------------------------- field rules

SUBTOTAL_RX = re.compile(r"^(sub-?total|net(?:\s+amount)?|nettobetrag|netto|zwischensumme)\b", re.I)
TAX_RX = re.compile(r"^(sales tax|tax|vat|gst|zzgl\.?|mwst|ust|iva|tva)\b", re.I)
TOTAL_RX = re.compile(
    r"^(total(?: due| amount)?|grand total|amount due|balance due|rechnungsbetrag|gesamtbetrag|endbetrag|"
    r"zu zahlen)\b", re.I)
SUMMARY_RX = re.compile(f"{SUBTOTAL_RX.pattern}|{TAX_RX.pattern}|{TOTAL_RX.pattern}", re.I)
CUSTOMER_LABELS = r"bill to|billed to|kunde|client|customer|sold to|rechnungsempfänger"
WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10}
IBAN_LEN = {"DE": 22, "PT": 25, "GB": 22, "FR": 27, "ES": 24, "IT": 27, "NL": 18, "AT": 20, "BE": 16,
            "IE": 22, "CH": 21, "PL": 28, "LU": 20, "DK": 18, "SE": 24, "FI": 18}


def find_currency(text: str) -> str:
    counts: dict[str, int] = {}
    for code in CUR_CODES:
        counts[code] = counts.get(code, 0) + 3 * len(re.findall(rf"\b{code}\b", text))
    for sym, code in CUR_SYM.items():
        counts[code] = counts.get(code, 0) + text.count(sym)
    return max(counts, key=counts.get) if any(counts.values()) else "USD"


def find_invoice_number(text: str) -> str | None:
    m = re.search(
        r"\b(?:tax\s+)?(?:invoice|rechnung|facture|factura|fattura)\b\s*(?:no\.?|nr\.?|number|num\.?)?\s*[:#]?\s*"
        r"([A-Z0-9][A-Z0-9/\-]*\d[A-Z0-9/\-]*)", text, re.I)
    return m[1] if m else None


def find_tax_id(text: str) -> str | None:
    m = re.search(
        r"\b(?:EIN|USt-?IdNr\.?|VAT\s*(?:reg\.?|no\.?|number|id)?|NIF|TIN|Tax\s*ID|UID|Steuernr\.?|ABN|GSTIN)"
        r"\s*[:#]?\s*([A-Z]{0,2}[0-9][0-9\- ]{5,}[0-9])", text, re.I)
    return re.sub(r"\s", "", m[1]) if m else None


def find_dates(text: str) -> tuple[date | None, date | None]:
    issue = due = None
    m = re.search(r"(?:invoice date|rechnungsdatum|issue date|date of issue|issued|datum|date)\s*:?\s*(.+)",
                  text, re.I)
    if m:
        issue = first_date(m[1])
    m = re.search(r"(?:due date|due|zahlbar bis|fällig(?: am)?|payable by)\s*:?\s*(.+)", text, re.I)
    if m:
        due = first_date(m[1])
    if issue and not due:
        m = re.search(r"(?:net\s*(\d{1,3})\b|within\s+(\d{1,3})\s+days|terms:?\s*(\d{1,3})\s+days|"
                      r"innerhalb\s+(?:von\s+)?(\d{1,3})\s+tagen)", text, re.I)
        if m:
            due = issue + timedelta(days=int(next(g for g in m.groups() if g)))
    return issue, due


def repair_iban(raw: str) -> str:
    """Fix OCR letter/digit confusions using IBAN structure (country length, 4-char print groups)."""
    groups = raw.upper().split()
    want = IBAN_LEN.get(groups[0][:2]) if groups else None
    # Printed IBANs come in groups of 4. A 5-char first group with an 'O' in it ("DEO00") is OCR
    # seeing one zero twice; drop the 'O' if that brings the length to the country's IBAN length.
    if want and len(groups[0]) == 5 and "O" in groups[0][2:] and len("".join(groups)) == want + 1:
        g = groups[0]
        i = g.index("O", 2)
        groups[0] = g[:i] + g[i + 1:]
    s = "".join(groups)
    country, rest = s[:2], s[2:]
    # Check digits are always digits; an all-numeric BBAN (DE, PT, ...) can't contain the letter O.
    rest = rest[:2].replace("O", "0") + rest[2:]
    if re.fullmatch(r"[0-9O]+", rest):
        rest = rest.replace("O", "0")
    return country + rest


def find_payment(lines: list[str], text: str) -> PaymentDetails:
    iban = bic = acct = routing = bank = None
    m = re.search(r"IBAN\s*:?\s*([A-Z]{2}[0-9O]{2}(?:\s?[A-Z0-9]){8,32})", text, re.I)
    if m:
        iban = repair_iban(m[1])
    m = re.search(r"\b(?:BIC|SWIFT)(?:/SWIFT)?\s*:?\s*([A-Z]{6}[A-Z0-9]{2,5})\b", text)
    if m:
        bic = m[1]
    m = re.search(r"\b(?:account|acct\.?|konto)(?:\s*(?:no\.?|number|nr\.?))?\s*:?\s*(\d[\d\- ]{4,}\d)", text, re.I)
    if m:
        acct = re.sub(r"\s", "", m[1])
    m = re.search(r"\brouting(?:\s*(?:no\.?|number))?\s*:?\s*(\d{9})\b", text, re.I) or \
        re.search(r"\bsort\s*code\s*:?\s*(\d{2}-\d{2}-\d{2})", text, re.I)
    if m:
        routing = m[1]
    m = re.search(r"(?:pay by [A-Z]+|pay to|bankverbindung|bank|remit to)\s*:\s*([^,·\n]+?)(?:,|\s·\s|$)",
                  text, re.I | re.M)
    if m and not re.match(r"(IBAN|BIC|account|sort)", m[1], re.I):
        bank = m[1].strip()
    return PaymentDetails(bank_name=bank, iban=iban, bic_swift=bic, account_number=acct,
                          routing_or_sort_code=routing)


def parse_item(line: str) -> LineItem | None:
    amounts = money_in(line)
    if not amounts:
        return None
    total, last = amounts[-1]
    if line[last.end():].strip(" .€"):
        return None  # money must close the line
    head = line[:last.start()].rstrip(" .")
    unit = qty = None
    if len(amounts) >= 2 and amounts[-2][1].end() >= len(head) - 1:
        unit, m2 = amounts[-2]
        head = line[:m2.start()].rstrip()
    q = re.search(r"\s(\d+(?:[.,]\d+)?)$", head)
    if q:
        qty = to_number(q[1]) if "," in q[1] or "." in q[1] else float(q[1])
        head = head[:q.start()]
    desc = re.sub(r"\s*\.{3,}\s*$", "", head).strip()
    if qty is None and unit is None:
        w = re.search(rf"\b({'|'.join(WORD_NUM)}|\d+)\b.*?\bat\s+{MONEY.pattern}\s+each", desc, re.I)
        if w:
            qty = float(WORD_NUM.get(w[1].lower(), w[1]))
            unit = to_number(w["num"])
    if unit is not None and qty is None:
        qty = 1.0
    return LineItem(description=desc, quantity=qty, unit_price=unit, line_total=total)


def find_items(lines: list[str]) -> list[LineItem]:
    start = 0
    for i, line in enumerate(lines):
        if re.match(rf"(?:{CUSTOMER_LABELS})\b", line, re.I):
            start = i + 1
    end = next((i for i in range(start, len(lines)) if SUMMARY_RX.match(lines[i])), len(lines))
    rows = [lines[i] for i in range(start, end)]
    items = [(r, parse_item(r)) for r in rows]
    items = [(r, it) for r, it in items if it is not None]
    # Strip a leading position column ("1 Wartungsvertrag...") when every row has one.
    if len(items) >= 2 and all(re.match(r"\d{1,3}\s+\D", it.description) for _, it in items):
        for _, it in items:
            it.description = re.sub(r"^\d{1,3}\s+", "", it.description)
    return [it for _, it in items]


def summary_amount(lines: list[str], rx: re.Pattern, last: bool = False) -> tuple[float | None, str | None]:
    hits = [ln for ln in lines if rx.match(ln) and money_in(ln)]
    if not hits:
        return None, None
    ln = hits[-1] if last else hits[0]
    return money_in(ln)[-1][0], ln


def extract(pdf: Path) -> tuple[Invoice, str]:
    raw, source = get_text(pdf)
    lines = normalise(raw)
    text = "\n".join(lines)

    customer = after_label(text, CUSTOMER_LABELS)
    if customer:
        customer = customer.split(",")[0].strip()

    subtotal, _ = summary_amount(lines, SUBTOTAL_RX)
    total, _ = summary_amount(lines, TOTAL_RX, last=True)
    tax_amount, tax_line = summary_amount(lines, TAX_RX)
    rate = None
    if tax_line:
        r = re.search(r"(\d+(?:[.,]\d+)?)\s*%", tax_line)
        rate = to_number(r[1]) if r and ("," in r[1] or "." in r[1]) else (float(r[1]) if r else None)
    notes = None
    rc = re.search(r"[^\n]*reverse[ -]charge[^\n]*", text, re.I) or re.search(r"[^\n]*steuerschuldnerschaft[^\n]*",
                                                                             text, re.I)
    if rc:
        notes = re.sub(r"^(VAT|USt\.?)\s*:\s*", "VAT ", rc[0].strip())
        if tax_amount is None:
            tax_amount = 0.0

    issue, due = find_dates(text)
    items = find_items(lines)
    inv = Invoice(
        vendor_name=lines[0] if lines else "",
        vendor_tax_id=find_tax_id(text),
        customer_name=customer,
        invoice_number=find_invoice_number(text) or "",
        issue_date=issue.isoformat() if issue else None,
        due_date=due.isoformat() if due else None,
        currency=find_currency(text),
        line_items=items,
        subtotal=subtotal,
        tax_rate_percent=rate,
        tax_amount=tax_amount,
        total=total if total is not None else (subtotal or 0.0) + (tax_amount or 0.0),
        payment=find_payment(lines, text),
        notes=notes,
    )
    return inv, source


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    suffix = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "--strip-suffix" else ""
    out.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(src.glob("*.pdf")):
        t0 = time.perf_counter()
        inv, source = extract(pdf)
        dt = time.perf_counter() - t0
        name = pdf.stem.removesuffix(suffix) if suffix else pdf.stem
        (out / f"{name}.json").write_text(json.dumps(inv.model_dump(), indent=2, ensure_ascii=False) + "\n")
        print(f"{pdf.name}\t{source}\t{dt:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
