"""Per approach x set: score, validator flags, false flags, silent errors, cost. Run from repo root."""
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
from score import score_one
from claude_invoice_parser.schema import Invoice
from claude_invoice_parser.validate import validate_invoice

R2 = Path("bakeoff/round2")
EXP = Path("samples/holdout/expected")
H11_ISSUE = "21.0% of 1840.0 is 386.4, but tax amount is 386.9"
PRICE = {"vision": (4.0, 20.0), "text-haiku": (0.10, 0.50)}

for approach in ["rules", "vision", "text-haiku"]:
    for s in ["text", "photo"]:
        d = R2 / approach / s
        exp_dir = EXP if s == "text" else R2 / "expected-photo"
        ok = n = 0; crashes = []; rows = []
        for e in sorted(exp_dir.glob("*.json")):
            f = d / e.name
            if not f.exists():
                crashes.append(e.stem); n += 16; continue
            got = json.loads(f.read_text())
            a, b, misses = score_one(got, json.loads(e.read_text()))
            ok += a; n += b
            issues = validate_invoice(Invoice.model_validate_json(f.read_text()))
            rows.append((e.stem, a, issues))
        print(f"\n## {approach}/{s}: {ok}/{n} ({100*ok/n:.1f}%)  missing outputs: {crashes or 'none'}")
        for stem, a, issues in rows:
            tag = []
            if stem.startswith("h11"):
                tag.append("H11-REAL-ERROR-FLAGGED" if H11_ISSUE in issues else "h11-real-error-NOT-flagged")
                other = [i for i in issues if i != H11_ISSUE]
            else:
                other = issues
            if other and a == 16: tag.append("FALSE-FLAG(correct output flagged)")
            elif other: tag.append("flag-caused-by-extraction-error")
            if not other and a < 16: tag.append(f"SILENT-ERROR({16-a} wrong, passed)")
            print(f"  {stem:28} {a:2}/16  {tag}  {issues if issues else 'OK'}")

for approach, (pin, pout) in PRICE.items():
    for s in ["text", "photo"]:
        mf = R2 / approach / s / "metrics.json" if approach == "vision" else R2 / approach / f"metrics-{s}.json"
        if not mf.exists(): print(approach, s, "no metrics"); continue
        m = json.loads(mf.read_text())
        print(f"\n## cost {approach}/{s}")
        ti = to = 0; secs = 0.0
        for r in m:
            if "error" in r: print(f"  {r['file']}: ERROR {r['error']}"); continue
            c = (r["input_tokens"] * pin + r["output_tokens"] * pout) / 1e6
            t = r.get("seconds", r.get("total_seconds"))
            ti += r["input_tokens"]; to += r["output_tokens"]; secs += t
            print(f"  {r['file']:32} {r['input_tokens']:6} in {r['output_tokens']:6} out  ${c:.6f}  {t}s  {r.get('served_by','')}")
        ok = [r for r in m if "error" not in r]
        print(f"  TOTAL {ti} in / {to} out  ${(ti*pin+to*pout)/1e6:.4f}  mean ${(ti*pin+to*pout)/1e6/max(len(ok),1):.5f}/doc  {secs:.1f}s sum, {secs/max(len(ok),1):.1f}s mean")
