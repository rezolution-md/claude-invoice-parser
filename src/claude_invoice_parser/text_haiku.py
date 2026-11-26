"""Bake-off approach "text-haiku": extract text locally, send only text to Claude Haiku 5.5.

The PDF never leaves the machine. pdfplumber reads the text layer; if a page has none
(an image-only scan), the page is rendered and OCR'd with tesseract. The resulting plain
text goes to claude-haiku-5-5 with the repo's Invoice schema as structured output.

Run: uv run --group bakeoff python -m claude_invoice_parser.text_haiku <pdf folder> <out folder>
"""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import anthropic
import pdfplumber
import pytesseract
from pdf2image import convert_from_path
from pydantic import ValidationError

from .extract import SYSTEM_PROMPT as BASE_SYSTEM_PROMPT
from .extract import ExtractionError
from .schema import Invoice
from .validate import validate_invoice

MODEL = "claude-haiku-5-5"
# Claude Haiku 5.5 list price, prompts up to 100K tokens (Anthropic pricing as of 2026-11-03).
PRICE_IN_PER_MTOK = 0.10
PRICE_OUT_PER_MTOK = 0.50

OCR_DPI = 300
OCR_CONFIG = "--psm 6"  # treat the page as one uniform block of text; keeps table rows on one line

SYSTEM_PROMPT = BASE_SYSTEM_PROMPT + """

You receive the invoice as plain text extracted from the PDF, not the PDF itself.
- Table columns may be separated by spaces or stray "|" characters; line breaks may not match the layout.
- When the text came from OCR, characters can be misread: O/Q/D for 0, l/I/| for 1, S/B for 5/8, B for ß.
  Correct these only where the field format makes the intended character certain (IBAN check digits
  and account numbers are digits, a German USt-IdNr. is DE + 9 digits). Never invent missing characters."""


@dataclass
class TextResult:
    invoice: Invoice
    source: str  # "text-layer" or "ocr"
    text_chars: int
    input_tokens: int
    output_tokens: int
    extract_seconds: float
    api_seconds: float

    @property
    def cost_usd(self) -> float:
        return (self.input_tokens * PRICE_IN_PER_MTOK + self.output_tokens * PRICE_OUT_PER_MTOK) / 1_000_000


def pdf_to_text(pdf_path: Path) -> tuple[str, str]:
    """Return (text, source). Uses the text layer per page, falling back to OCR for image-only pages."""
    pages: list[str] = []
    used_ocr = False
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                image = convert_from_path(pdf_path, dpi=OCR_DPI, grayscale=True, first_page=i, last_page=i)[0]
                text = pytesseract.image_to_string(image, config=OCR_CONFIG).strip()
                used_ocr = True
            pages.append(text)
    return "\n\n--- page break ---\n\n".join(pages), ("ocr" if used_ocr else "text-layer")


def extract_from_text(pdf_path: Path, client: anthropic.Anthropic, effort: str = "medium") -> TextResult:
    t0 = time.perf_counter()
    text, source = pdf_to_text(pdf_path)
    t1 = time.perf_counter()
    if not text.strip():
        raise ExtractionError(f"{pdf_path.name}: no text found, even after OCR")

    label = "OCR output" if source == "ocr" else "text layer"
    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_format=Invoice,
            output_config={"effort": effort},
            messages=[{
                "role": "user",
                "content": f"Extract this invoice. Source: {label}.\n\n<invoice_text>\n{text}\n</invoice_text>",
            }],
        )
    except ValidationError as e:
        raise ExtractionError(f"{pdf_path.name}: output did not match the invoice schema ({e.error_count()} errors)") from e
    t2 = time.perf_counter()

    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else None
        raise ExtractionError(f"{pdf_path.name}: request declined (category: {category})")
    if response.stop_reason == "max_tokens":
        raise ExtractionError(f"{pdf_path.name}: response hit max_tokens before the JSON was complete")
    if response.parsed_output is None:
        raise ExtractionError(f"{pdf_path.name}: no structured output (stop_reason: {response.stop_reason})")

    return TextResult(
        invoice=response.parsed_output,
        source=source,
        text_chars=len(text),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        extract_seconds=t1 - t0,
        api_seconds=t2 - t1,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()
    metrics = []
    for pdf in sorted(args.folder.glob("*.pdf")):
        name = pdf.stem.removesuffix("-scan")  # scorer matches on the original name
        try:
            r = extract_from_text(pdf, client, effort=args.effort)
        except ExtractionError as e:
            print(f"FAILED {pdf.name}: {e}")
            metrics.append({"file": pdf.name, "error": str(e)})
            continue
        (args.out / f"{name}.json").write_text(r.invoice.model_dump_json(indent=2))
        issues = validate_invoice(r.invoice)
        row = {
            "file": pdf.name, "source": r.source, "text_chars": r.text_chars,
            "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "cost_usd": round(r.cost_usd, 6),
            "extract_seconds": round(r.extract_seconds, 2), "api_seconds": round(r.api_seconds, 2),
            "total_seconds": round(r.extract_seconds + r.api_seconds, 2), "issues": issues,
        }
        metrics.append(row)
        print(f"{'REVIEW' if issues else 'OK':7}{pdf.name}: {r.source}, {r.input_tokens} in / {r.output_tokens} out, "
              f"${r.cost_usd:.6f}, {row['total_seconds']}s" + (f"\n        {issues}" if issues else ""))
    (args.out.parent / f"metrics-{args.out.name}.json").write_text(json.dumps(metrics, indent=2))
    ok = [m for m in metrics if "error" not in m]
    print(f"Total: {sum(m['input_tokens'] for m in ok)} in / {sum(m['output_tokens'] for m in ok)} out, "
          f"${sum(m['cost_usd'] for m in ok):.6f}")
    return 0 if len(ok) == len(metrics) else 1


if __name__ == "__main__":
    sys.exit(main())
