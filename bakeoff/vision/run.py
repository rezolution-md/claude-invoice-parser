"""Bake-off runner for the "vision" baseline.

Calls the repo's unchanged pipeline (extract_invoice: PDF sent as a document block, strict
schema, claude-opus-5-5, effort medium) on one folder and records, per document, the
usage tokens from the API response, the model that served it, wall-clock time and the
validator's issues.

    uv run python bakeoff/vision/run.py samples/invoices bakeoff/vision/clean
    uv run python bakeoff/vision/run.py samples/scanned  bakeoff/vision/scan
"""

import json
import sys
import time
from pathlib import Path

import anthropic

from claude_invoice_parser.extract import ExtractionError, extract_invoice
from claude_invoice_parser.validate import validate_invoice


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()
    metrics = []
    for pdf in sorted(src.glob("*.pdf")):
        name = pdf.stem.removesuffix("-scan")
        start = time.perf_counter()
        try:
            result = extract_invoice(pdf, client)  # default effort, as the CLI uses
        except ExtractionError as e:
            secs = time.perf_counter() - start
            metrics.append({"file": pdf.name, "error": str(e), "seconds": round(secs, 2)})
            print(f"FAILED {pdf.name}: {e}")
            continue
        secs = time.perf_counter() - start
        issues = validate_invoice(result.invoice)
        (out / f"{name}.json").write_text(
            json.dumps(result.invoice.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        metrics.append({
            "file": pdf.name,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "served_by": result.served_by,
            "seconds": round(secs, 2),
            "status": "needs_review" if issues else "ok",
            "issues": issues,
        })
        print(f"{pdf.name}: {result.input_tokens} in / {result.output_tokens} out, {secs:.1f}s, "
              f"{result.served_by}, {'needs_review' if issues else 'ok'}")
        for i in issues:
            print(f"    - {i}")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
