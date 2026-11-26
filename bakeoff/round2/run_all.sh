#!/usr/bin/env bash
# Round 2 runner: points the three frozen round-1 approaches at samples/holdout.
# No approach code is changed. The only adaptation: the frozen scripts strip "-scan" (not
# "-photo") from file names, so the photos are symlinked under their ORIGINAL names into a
# temporary folder, and each approach is run on that folder exactly as in round 1.
#
#   eval "$(discobox-access env)"; bash bakeoff/round2/run_all.sh [rules|vision|text-haiku ...]
set -euo pipefail
cd "$(dirname "$0")/../.."
R2=bakeoff/round2
TEXT=samples/holdout/invoices
PHOTO=$(mktemp -d)
trap 'rm -rf "$PHOTO"' EXIT
for f in samples/holdout/photos/*-photo.pdf; do
  b=$(basename "$f" -photo.pdf)
  ln -s "$PWD/$f" "$PHOTO/$b.pdf"
done
mkdir -p "$R2/expected-photo" "$R2/logs"
for f in "$PHOTO"/*.pdf; do cp "samples/holdout/expected/$(basename "$f" .pdf).json" "$R2/expected-photo/"; done

timed() {  # timed <log> <cmd...> : run, tee output, append total wall-clock seconds
  local log=$1; shift
  local t0=$(date +%s.%N)
  "$@" 2>&1 | tee "$log" || true
  echo "WALL_CLOCK_SECONDS $(python3 -c "import sys,time; print(round(time.time()-float(sys.argv[1]),1))" "$t0")" | tee -a "$log"
}

for a in "${@:-rules vision text-haiku}"; do for approach in $a; do
  case $approach in
    rules)
      Rr() { uv run --with pdfplumber --with pytesseract python bakeoff/rules/extract_rules.py "$@"; }
      timed $R2/logs/rules-text.log  Rr "$TEXT"  $R2/rules/text
      timed $R2/logs/rules-photo.log Rr "$PHOTO" $R2/rules/photo ;;
    vision)
      export ANTHROPIC_API_KEY="$INVOICE_ANTHROPIC_KEY"
      timed $R2/logs/vision-text.log  uv run python bakeoff/vision/run.py "$TEXT"  $R2/vision/text
      timed $R2/logs/vision-photo.log uv run python bakeoff/vision/run.py "$PHOTO" $R2/vision/photo
      unset ANTHROPIC_API_KEY ;;
    text-haiku)
      export ANTHROPIC_API_KEY="$INVOICE_ANTHROPIC_KEY"
      timed $R2/logs/text-haiku-text.log  uv run --group bakeoff python -m claude_invoice_parser.text_haiku "$TEXT"  $R2/text-haiku/text
      timed $R2/logs/text-haiku-photo.log uv run --group bakeoff python -m claude_invoice_parser.text_haiku "$PHOTO" $R2/text-haiku/photo
      unset ANTHROPIC_API_KEY ;;
  esac
done; done
