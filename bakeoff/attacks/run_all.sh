#!/usr/bin/env bash
# Attack-set runner: points the three frozen approaches at samples/attacks/invoices, with the
# same commands, models and settings bakeoff/round2/run_all.sh uses for the holdout text set.
# Text set only (there are no photos). No approach code is changed.
#
# Extra steps, not in round 2:
#   pipeline  runs the full CLI once (uv run invoice-parser ... --out bakeoff/attacks/pipeline),
#             so each invoice gets the real ok / needs_review / failed status.
#   retry     after each API approach, any invoice that has no JSON output (the call errored) is
#             re-run ONCE, alone, with the same frozen command, into <approach>/retry/, logged as
#             logs/<approach>-retry-<invoice>.log. The first attempt's log is kept untouched.
#
#   eval "$(discobox-access env)"; bash bakeoff/attacks/run_all.sh [rules|vision|text-haiku|pipeline ...]
set -euo pipefail
cd "$(dirname "$0")/../.."
A=bakeoff/attacks
TEXT=samples/attacks/invoices
mkdir -p "$A/logs"

timed() {  # timed <log> <cmd...> : run, tee output, append total wall-clock seconds
  local log=$1; shift
  local t0=$(date +%s.%N)
  "$@" 2>&1 | tee "$log" || true
  echo "WALL_CLOCK_SECONDS $(python3 -c "import sys,time; print(round(time.time()-float(sys.argv[1]),1))" "$t0")" | tee -a "$log"
}

retry_missing() {  # retry_missing <approach> <outdir> <cmd...> : re-run once each invoice with no JSON
  local approach=$1 out=$2; shift 2
  for f in "$TEXT"/*.pdf; do
    local b=$(basename "$f" .pdf)
    [ -f "$out/$b.json" ] && continue
    local one=$(mktemp -d)
    ln -s "$PWD/$f" "$one/$b.pdf"
    echo "RETRY $b (no output from the first attempt)" | tee -a "$A/logs/retries.log"
    timed "$A/logs/$approach-retry-$b.log" "$@" "$one" "$out/retry/$b"
    rm -rf "$one"
    if [ -f "$out/retry/$b/$b.json" ]; then
      cp "$out/retry/$b/$b.json" "$out/$b.json"
      echo "RETRY $b: succeeded, output copied to $out/$b.json" | tee -a "$A/logs/retries.log"
    else
      echo "RETRY $b: no output again" | tee -a "$A/logs/retries.log"
    fi
  done
}

for a in "${@:-rules vision text-haiku pipeline}"; do for approach in $a; do
  case $approach in
    rules)
      Rr() { uv run --with pdfplumber --with pytesseract python bakeoff/rules/extract_rules.py "$@"; }
      timed $A/logs/rules-text.log Rr "$TEXT" $A/rules/text ;;
    vision)
      export ANTHROPIC_API_KEY="$INVOICE_ANTHROPIC_KEY"
      V() { uv run python bakeoff/vision/run.py "$@"; }
      timed $A/logs/vision-text.log V "$TEXT" $A/vision/text
      retry_missing vision $A/vision/text V
      unset ANTHROPIC_API_KEY ;;
    text-haiku)
      export ANTHROPIC_API_KEY="$INVOICE_ANTHROPIC_KEY"
      T() { uv run --group bakeoff python -m claude_invoice_parser.text_haiku "$@"; }
      timed $A/logs/text-haiku-text.log T "$TEXT" $A/text-haiku/text
      retry_missing text-haiku $A/text-haiku/text T
      unset ANTHROPIC_API_KEY ;;
    pipeline)
      export ANTHROPIC_API_KEY="$INVOICE_ANTHROPIC_KEY"
      timed $A/logs/pipeline.log uv run invoice-parser "$TEXT" --out $A/pipeline
      unset ANTHROPIC_API_KEY ;;
  esac
done; done
