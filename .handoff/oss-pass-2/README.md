# oss-pass-2 — companion data for `.handoff/OSS-REVERSE-ENGINEERING-PASS-2-2026-09-09.md`

Produced 2026-09-09 by the second OSS reverse-engineering pass over OpenClaw, Hermes and open-claude-code. Read the top-level handoff first; it indexes these files in its section 9.

| File | What it is |
|---|---|
| `remediation_plan.md` | The solidity-audit remediation plan: verdict, cross-cutting themes, the ranked fix-first table with seams and pinning tests, packets R-01…R-15, refuted gaps with reasons, rejected bugs, founder decisions FD-1…FD-24. |
| `section_<workstream>.md` | Twelve discovery syntheses, one per Halbert workstream: themes, every verified item with origin `path:lines` and a task, related audit gaps, do-not-lift, proposed packets, founder decisions. |
| `coverage_report.md` | What this pass read and did not read; thin units; unassigned directories; twenty ranked follow-up units; the HM09 anomaly. |
| `audit_overview.md` | All seventeen solidity audits in one file: each gap with confirmed/refuted status and effective severity, each suspected bug with its verdict. |
| `lost_units_digest.md`, `lost_units_verdicts.md` | The six audits (A06, A08, A10, A11, A13, A15) whose full JSON was lost to a scratch-directory wipe: the orchestrator's digest (truncated fields) and the refuter's full per-item reasons. |
| `discovery_digest.md` | One line per kept and verifier-added discovery item (881), grouped by workstream: `[priority/halbert_state/effort/novelty/status] id: title | origin | task`. |
| `merged_audits.json` | Full audit records for eleven units (invariants, gaps with verdicts, bugs with verdicts, origin tests not mirrored) and verdict-only records for the six lost units. |
| `merged_discoveries.json` | Every discovery candidate for all 46 units, including dropped ones, with the verifier's per-candidate verdict and notes, `missed_by_reader`, `unread_areas` and `verify_summary`. |

Ids: `A<nn>-<unit>-G<n>` are audit gaps; `<UNIT>-C<n>` are reader candidates; `<UNIT>-M<n>` are verifier-added mechanisms (effort unestimated). Unit HM09's `-C` candidates are unverified (the reader wrote a placeholder file); its `-M` items are the trustworthy ones.

Line numbers in audit records drift (A08's Hermes citations by about 150 lines); the remediation plan quotes refuter-corrected lines. Do not paste an audit's lines into a packet without re-opening the file.
