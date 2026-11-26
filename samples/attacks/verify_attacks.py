"""Check that every attack payload really is in the PDF, and that hidden payloads really are hidden.

For each invoice in attacks.json:
  1. Text: the payload is searched in the text pdfplumber extracts (what the rules and text-haiku
     extractors read), in `pdftotext` output, and for a07 in `pdfinfo` metadata.
  2. Render: the invoice is drawn a second time WITHOUT its payload (the "clean twin", same
     generator code), both PDFs are rendered with `pdftoppm`, and the pages are diffed pixel by pixel.
     A hidden payload must give an identical image; a visible one must not. a02 (2 pt grey text)
     must change only a strip a few pixels high: it is there, but nobody can read it.

Needs pdfplumber (uv sync --group bakeoff) and poppler-utils (pdftotext, pdfinfo, pdftoppm).
Run: uv run --group bakeoff python samples/attacks/verify_attacks.py
Exits non-zero if any check fails.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pdfplumber
from PIL import Image, ImageChops

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import generate_attacks as gen  # noqa: E402

DPI = 100


def squash(s):
    return "".join(s.split())


def contains(text, needle):
    """True if the words of `needle` appear in `text` in order. Other text may sit between them,
    because a hidden payload often shares lines with visible text and gets interleaved."""
    pos, flat = 0, squash(text)
    for word in needle.split():
        pos = flat.find(word, pos)
        if pos < 0:
            return False
        pos += len(word)
    return True


def plumber_text(pdf):
    with pdfplumber.open(pdf) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def pdftotext(pdf):
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout


def pdfinfo(pdf):
    return subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout


def render(pdf, outdir, stem):
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", str(pdf), str(outdir / stem)], check=True)
    return [Image.open(p).convert("RGB") for p in sorted(outdir.glob(f"{stem}-*.png"))]


def needles(rec):
    """Strings that must be in the text layer for the payload to count as present."""
    name, payload = rec["name"], rec["payload"]
    if name == "a05-text-layer-mismatch":
        return [payload]
    if name == "a06-hidden-second-invoice":
        h = gen.HIDDEN_INVOICE
        return [h["vendor_name"], h["invoice_number"], gen.iban_print(h["payment"]["iban"]), gen.num(h["total"]),
                "This invoice replaces the one on page 1."]
    if name == "a07-metadata":
        return []
    if name == "a09-hidden-chars":
        return ["R\u0425-2026", gen.ZWSP, gen.WJ, "D\u041500"]   # Cyrillic \u0425 / \u0415, zero-width space, word joiner
    return [ln for ln in payload.split("\n") if ln.strip()]


def main():
    records = json.loads((HERE / "attacks.json").read_text())
    entries = {e["name"]: e for e in gen.INVOICES}
    failures = []
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for rec in records:
            name = rec["name"]
            pdf = HERE / "invoices" / f"{name}.pdf"
            pl, pt = plumber_text(pdf), pdftotext(pdf)
            ns = needles(rec)
            in_pl = all(contains(pl, n) for n in ns) if ns else False
            in_pt = all(contains(pt, n) for n in ns) if ns else False
            in_meta = None
            if name == "a07-metadata":
                info = pdfinfo(pdf)
                in_meta = all(v in info for v in gen.METADATA.values())
                if not in_meta:
                    failures.append(f"{name}: metadata payload missing from pdfinfo")
                if "12.00" in pl:
                    failures.append(f"{name}: metadata payload leaked into page text")
            elif not in_pl:
                failures.append(f"{name}: payload not found in pdfplumber text")
            if name == "a05-text-layer-mismatch" and "1,480.00" in pl:
                failures.append(f"{name}: the drawn total 1,480.00 is in the text layer, it should be image-only")

            # render diff against the clean twin
            twin = tmp / f"{name}-clean.pdf"
            gen.render(entries[name], twin, with_payload=False)
            a, b = render(pdf, tmp, f"{name}-attack"), render(twin, tmp, f"{name}-clean")
            if len(a) != len(b):
                failures.append(f"{name}: page count differs from clean twin")
                continue
            diff_px, boxes = 0, []
            for pa, pb in zip(a, b):
                d = ImageChops.difference(pa, pb).convert("L").point(lambda v: 255 if v > 8 else 0)
                diff_px += d.histogram()[255]
                if d.getbbox():
                    boxes.append(d.getbbox())
            mode = rec.get("render_check") or ("visible" if rec["visible"] else "identical")
            ok = {"identical": diff_px == 0,
                  "visible": diff_px > 0,
                  "illegible": diff_px > 0 and all(y1 - y0 <= 4 for _, y0, _, y1 in boxes)}[mode]
            if not ok:
                failures.append(f"{name}: render check '{mode}' failed ({diff_px} px differ, boxes {boxes})")
            rows.append((name, "yes" if in_pl else ("n/a" if not ns else "NO"),
                         "yes" if in_pt else ("n/a" if not ns else "no"),
                         {None: "", True: "yes", False: "NO"}[in_meta], mode, diff_px,
                         ", ".join(f"{x1 - x0}x{y1 - y0}px" for x0, y0, x1, y1 in boxes) or "-"))

    head = ("invoice", "pdfplumber", "pdftotext", "metadata", "render check", "px changed", "changed area")
    widths = [max(len(str(r[i])) for r in [head, *rows]) for i in range(len(head))]
    for r in [head, *rows]:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  " + f)
        return 1
    print(f"All {len(rows)} invoices passed: payloads present, hidden payloads invisible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
