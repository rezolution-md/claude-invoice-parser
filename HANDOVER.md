Box handover (handover-rules skill v1)

# Bake-off round 2: held-out run

Branch `bakeoff/round2`. The full write-up is in [`bakeoff/round2/RESULTS.md`](bakeoff/round2/RESULTS.md).

**Result:** I ran all three frozen approaches on `samples/holdout`: 12 text-layer PDFs and 4 phone photos.

| Approach | Text | Photo | h11 VAT error flagged | Cost, 16 docs |
|---|---|---|---|---|
| rules | 108/192 (56.2%) | 27/64 (42.2%) | no | $0 |
| vision (Opus 5.5) | 188/192 (97.9%) | 63/64 (98.4%) | yes | $0.55 |
| text-haiku | 188/192 (97.9%) | 52/64 (81.2%) | yes | $0.018 |

- No approach crashed or failed to produce output.
- The validator never flagged a correct output. But it let through 5 wrong vision outputs and 5 wrong text-haiku outputs, mostly with a wrong IBAN or tax ID.
- **Verdict:** use vision if you can only run one approach; text-haiku for digital PDFs, with photos and flagged files sent to vision; rules only for fixed-vendor templates.

**What was done:**
- No approach code was changed.
- `bakeoff/round2/run_all.sh` symlinks the photos under their original names, because the frozen scripts strip only `-scan`. It then runs each approach's own entry point.
- I installed tesseract 5.5.4 with apt, as in round 1. Rules and text-haiku need it for the photos.
- The outputs, metrics and logs are all in `bakeoff/round2/`. Nothing is left only in a scratchpad.

**Open:**
- Each approach ran once, with no repeat runs, so expect some run-to-run variation in the LLM scores.
- The validator does not check IBAN length or mod-97. That is the obvious next fix, but it is outside this frozen round.
