"""Run the repo validator on a folder of extracted JSON: uv run python bakeoff/rules/validate_outputs.py <dir>..."""
import json,sys
from pathlib import Path
from claude_invoice_parser.schema import Invoice
from claude_invoice_parser.validate import validate_invoice
for d in sys.argv[1:]:
    for f in sorted(Path(d).glob("*.json")):
        print(d, f.stem, validate_invoice(Invoice.model_validate_json(f.read_text())) or "OK")
