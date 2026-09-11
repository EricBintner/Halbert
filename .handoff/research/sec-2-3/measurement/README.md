# The classifier measurement — scripts, corpus, and the full report

These are the artefacts behind the numbers in Review Packet 12 §5.1. They were cited there before
they were committed, which meant the packet's single most important review directive — *check the
measured numbers yourself* — could be followed by nobody but its author, on one machine, until the
tmp directory was reaped. That was the bug; this directory is the fix.

**They carry hard-coded absolute paths** to the tmp directory they were written in
(`/private/tmp/claude-501/.../scratchpad`). Repoint those at this directory before running. They are
committed as evidence of how the numbers were produced, not as a maintained tool.

| File | What it is |
|---|---|
| `mine.py` | Builds the corpus: AST-extracts every argv Halbert's own code executes, plus shell lines from `data/**/*.jsonl` and fenced bash blocks in repo markdown. |
| `corpus.json` | The result: 262 argv lines, 11,133 doc lines, 250 markdown lines. |
| `proto.py` | The prototype allowlist classifier — the `(basename, first-operand)` table under evaluation. |
| `converge.py` | Prints the comparison table in §5.1. |
| `measure.py` | Classifies the corpus with the *current* framework, for the "today" column. |
| `report.json` | Per-command verdicts for every corpus line. This is the file to grep when a number looks wrong. |
| `verify.py` | 47 hand-written assertions — the bypasses that must gate and the ordinary commands that must not. |
| `safety.patched.py` / `safety.patch` | The proposed rewrite as measured. **Cut before `79dca611`, so it reverts the credential-read gate** — see the packet's note on 2-vs-24 test failures. |
| `sb/` | Seatbelt profiles used for the macOS sandbox measurements. |

## What reproduces, and what does not

Re-run on 2026-09-08 from this directory:

```
$ python converge.py
=== argv  n=262 ===
  today                     prompts/blocks:      8    3.1%
  plan (unknown->HIGH)      prompts/blocks:    217   82.8%
  proposal (allowlist+HIGH) prompts/blocks:     62   23.7%
```

Those three reproduce exactly, and they are the three the packet now quotes.

**Withdrawn:** an earlier draft of the packet carried a fourth column — 11.1% argv and 78.6% docs
"after one maintenance pass". `converge.py` emits no second-pass figure at all, and neither number
reproduces. The convergence claim is therefore **unproven**: 23.7% is what the allowlist measurably
achieves. Whether a maintenance pass halves it again is a question for whoever picks this up, not a
result.
