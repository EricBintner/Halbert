# Pause State — Rust Roadmap Doc Augmentation (2026-08-31)

> **RESUMED AND COMPLETED 2026-09-01.** The workflow was resumed from cache
> (17/17 agents, cached prefix replayed), all drafts spliced into the plan doc
> (now 72 tasks / 8 phases, ~2,640 lines), the scoping doc corrected, and
> MASTER-TODO re-synced. The review request is marked APPLIED. The sections
> below are kept as the historical record of the pause.

## Landed (committed to working tree, not yet committed to git)

- `.handoff/REVIEW-REQUEST-RUST-NATIVE-CORE-2026-08-31.md` — full sanity review
  of the Rust-native-core plan + Docker integration path. 13 findings (F1–F13),
  5 recommendations (RA–RE), 6 reviewer questions, 11-item proposed-edit list (§7).
  Two HIGH findings: **F1** (R1 not verifiable until R4 — fix: incremental FFI
  waves R4a/b/c) and **F2** (no Docker image build task exists — add R0.9/R0.10).
- `.handoff/MASTER-TODO.md` — one index entry added under the Rust Native Core
  subsection pointing at the review request.

## In flight (paused)

- Workflow **wf_4fe60499-a7b** ("augment-rust-roadmap-docs") — stopped cleanly.
  7 drafters + 7 adversarial verifiers + 1 completeness critic producing the
  verbose augmented sections for the plan doc. Resume path: session scratch,
  gone — the script is fully described by the findings in the review request;
  re-author from §7's edit list if it ever needs re-running.

## Remaining after resume (session task list #2–#4)

1. Splice verified drafts into `RUST-NATIVE-CORE-TODO-AND-IMPLEMENTATION-PLAN-2026-08-31.md`:
   counts 56→72 (R0 gains R0.9 Dockerfile + R0.10 CI image publish), R4 →
   incremental waves, R3 deps on R0 only (F4), one-external-MCP-surface daemon
   design (F9/RC), revised compose template (F6), reference Linux/Btrfs test
   env (RD), new §16 long-term L0–L3 stage gates.
2. Scoping doc (`HA-STRATEGY-SCOPING-AND-DEPLOYMENT-PATHS-2026-08-31.md`):
   §7 compose template revision, Path 3 "already runs in Docker" strike (F13),
   §9 roadmap gains containerization rows.
3. MASTER-TODO Rust subsection: resync to 72 tasks / new execution order
   (waits on resume output PART B), then mark the review request APPLIED
   (PART C).

## Grounding facts already verified (reuse, don't re-derive)

- `halbert_core/pyproject.toml`: extras pattern `light`/`rag-legacy`/`full`
  exists → add `rust` extra the same way; `requires-python = ">=3.10"` →
  abi3-py310 wheels viable; console script `halbert-mcp-serve =
  halbert_core.mcp.server:main` exists.
- `.github/workflows/ci.yml`: suite-census meta-gate fails CI on any ungated
  test file — R0.7 must register `crates/` in GATES or the first Rust test
  breaks CI.
- No Dockerfile/docker-compose anywhere in the repo; `deploy/` is systemd
  units only.
- `halbert_core/halbert_core/mcp/server.py`: 18 tools, stdio-only transport,
  `mcp_response()` egress boundary — must remain the single external MCP
  surface (halbertd socket is internal IPC).
- Frigate MQTT subscriber uses aiomqtt (lazy optional dep) — coexistence with
  the Rust bus is the R1-era stance; migration optional later.
