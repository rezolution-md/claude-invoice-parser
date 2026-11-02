"""Compare extracted JSON (output/json) with the expected answers (samples/expected).

Run after the parser: uv run python scripts/score.py [output/json]
Prints field-level accuracy per invoice and overall, so a prompt or model change can be measured.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCALARS = ["vendor_name", "vendor_tax_id", "customer_name", "invoice_number", "issue_date", "due_date",
           "currency", "subtotal", "tax_rate_percent", "tax_amount", "total"]
PAYMENT = ["iban", "bic_swift", "account_number", "routing_or_sort_code"]


def norm(value):
    if isinstance(value, str):
        return " ".join(value.lower().replace(" ", "").split())
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    return value


def score_one(got: dict, want: dict) -> tuple[int, int, list[str]]:
    checks, misses = 0, []
    for key in SCALARS:
        checks += 1
        if norm(got.get(key)) != norm(want.get(key)):
            misses.append(f"{key}: got {got.get(key)!r}, expected {want.get(key)!r}")
    for key in PAYMENT:
        checks += 1
        if norm(got["payment"].get(key)) != norm(want["payment"].get(key)):
            misses.append(f"payment.{key}: got {got['payment'].get(key)!r}, expected {want['payment'].get(key)!r}")
    checks += 1
    got_totals = [norm(i["line_total"]) for i in got["line_items"]]
    want_totals = [norm(i["line_total"]) for i in want["line_items"]]
    if got_totals != want_totals:
        misses.append(f"line totals: got {got_totals}, expected {want_totals}")
    return checks - len(misses), checks, misses


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output" / "json"
    total_ok = total = 0
    for expected in sorted((ROOT / "samples" / "expected").glob("*.json")):
        got_path = out / expected.name
        if not got_path.exists():
            print(f"{expected.stem}: no output found")
            continue
        ok, n, misses = score_one(json.loads(got_path.read_text()), json.loads(expected.read_text()))
        total_ok += ok
        total += n
        print(f"{expected.stem}: {ok}/{n} fields correct")
        for m in misses:
            print(f"    {m}")
    if total:
        print(f"\nOverall: {total_ok}/{total} fields correct ({100 * total_ok / total:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
