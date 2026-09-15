# Architectural audit — god-file identification pass + tier assignment

Written 2026-09-14. Source: an identification-only audit pass over the whole tree (line counts via `wc -l`, shape via AST: top-level classes/functions/method-count/longest-function). **No code was changed.** This doc is the deliverable: a ranked list of blatantly oversized files that should be broken up, each with a model tier (fable / opus / sonnet) and effort level (ultracode / max / xhigh / high / med).

Zero `.go` files exist in the repo — "go files" in the request was read as "god files."

## Method note

Raw line count alone is a bad signal here — three different things produce a big file:

1. **True god file** — one file holding many responsibilities (route tables spanning unrelated domains, a state machine owning every handler, an 866-line `create_app`). These are the targets.
2. **Data disguised as code** — giant literals or content-generating methods (`macos_command_data.py`, the `*_docs.py` scraper family). Different fix: move content to data, not "refactor."
3. **Legitimately long** — big test files (1,200–1,500 lines each), uniform per-domain scrapers. Left alone.

Every candidate below was AST-checked, not just line-counted.

## Tiering axes used

- **Model**: `opus` for high-blast-radius files, anything touching a security boundary or a repo invariant, and splits where extraction order/semantics can silently change behavior (mount order, transaction boundaries, turn/interrupt lifecycle). `sonnet` for mechanical, contract-preserving splits where the diff is verifiable by "same public surface, same route table, same CLI." `fable` for pure data moves.
- **Effort**: `ultracode` only where a packet is file-disjoint and can run in a parallel worktree; `max`/`xhigh`/`high`/`med` by size, method count, and verification burden.
- **Constraint check before dispatch**: every packet must preserve the repo invariants in AGENTS.md — most importantly the single-choke-point rules (model locality in `is_local_model()`, feature gating in `has_capability()`, redaction through `redaction_registry.py` + `display_transport.py`). A split that copies an invariant's logic into a second file is a regression, not a cleanup.

## Tier table — production god files

| Packet | Target | Lines | Shape | Model | Effort | Why | File-disjoint? |
|---|---|---|---|---|---|---|---|
| G-01 | `dashboard/routes/settings.py` | 3,593 | 88 route handlers across ~10 unrelated domains (model install, computer name, AI rules, onboarding, system scan, ingestion, indexing, knowledge graph, relations) | **sonnet** | xhigh | Mechanical split by domain prefix into `routes/settings/` modules — but 88 endpoints means the verification is "diff the final OpenAPI route table before/after," which is real work. Ultracode-eligible if run alone in a worktree. | yes |
| G-02 | `Halbert/main.py` | 2,671 | 65 functions, `main()` is 777 lines — every CLI subcommand inline | **sonnet** | high | Extract subcommand groups into `halbert_core/cli/` modules (package already exists, nearly empty). Contract: `halbert <cmd>` surface and argparse behavior byte-identical. | yes |
| G-03 | `dashboard/app.py` | 2,078 | `create_app()` alone is 866 lines | **opus** | high | Mostly mechanical mount/middleware grouping — BUT mount order is security-relevant (`SELF_AUTHENTICATING` mounts self-authenticate; everything else defaults to `require_owner`). Reordering mounts or moving a router's mount-site changes auth posture silently. Needs someone who reads the auth-mount contract, not just the line count. | yes |
| G-04 | `agents/state_machine.py` | **6,010** | 1 class (`AgentStateMachine`), ~104 methods, `_handle_responding` is 542 lines | **opus** | max | The worst file in the repo. Owns every state handler, TTS egress, arbiter notification, turn lifecycle, interrupt handling — i.e., R-01's talk-door/interrupt-algebra territory. Split per state-handler or per concern into `agents/state_machine/` package keeping the class as facade. Sequential, not parallel — this file is the center of the turn loop. | no (center of everything) |
| G-05 | `agents/conversation_sqlite.py` | 3,937 | 82 methods, `_ensure_schema` is 292 lines | **opus** | xhigh | Storage god file. SQLite corruption-predicate internals were hardened in R-04; transaction discipline (`BEGIN IMMEDIATE` vs deferred) was a real bug class here. Split: schema/migrations module + query modules per domain + store facade. | no (feeds continuity, threads) |
| G-06 | `dashboard/routes/agent.py` | 2,600 | `send_message` is 315 lines; also hosts `_endpoint_is_local` (thin delegate — keep it that way) | **opus** | high | Talk-door / message-submission auth surface. Splitting routes is mechanical, but this file sits on the peer-vs-owner boundary that the iOS-companion work is actively probing. | no (active seam) |
| G-07 | `mcp/server.py` | 2,035 | 35 funcs + 5 classes | **opus** | high | MCP protocol + dispatch + lifecycle in one file; MCP is a trust boundary (R-09 hardened the client side). Split protocol framing from tool dispatch from lifecycle. | yes |
| G-08 | `discovery/scanners/system_profile.py` | 1,935 | 1 class, 36 methods | **sonnet** | high | God-scanner: every probe category in one class. Splits cleanly per probe category; deterministic. Ultracode-eligible alongside G-01/G-02. | yes |

## Tier table — second tier (1,000–1,600 lines)

| Packet | Target | Lines | Shape | Model | Effort | Notes | File-disjoint? |
|---|---|---|---|---|---|---|---|
| G-09 | `mcp/client.py` | 1,584 | 12 classes, 43 methods | **opus** | med | MCP trust boundary; class-per-concern split | yes |
| G-10 | `mcp/package_preflight.py` | 1,538 | 40 funcs + 6 classes | **sonnet** | med | Self-contained FD-10 work; splits by check family | yes |
| G-11 | `model/client.py` | 1,498 | 38 top-level funcs + 1 class | **sonnet** | med | Helpers/scoring vs. client class split; stay inside `model/` | yes |
| G-12 | `agents/threads.py` | 1,483 | 38 methods, `begin_turn` 117 | **opus** | high | Session-tree/`move_leaf` transaction semantics live here (R-12 territory); turn-boundary bugs were a real defect class | no (pairs with G-04/G-05) |
| G-13 | `tools/executor.py` | 1,426 | `execute()` is 279 lines; detached-spawn path just landed | **opus** | high | Command-execution boundary — safety policy + spawn mechanics; recently touched (Phase-4 detached spawn) | no |
| G-14 | `prompts/agent_prompts.py` | 1,405 | 26 methods, `build_response_prompt` 176 | **sonnet** | med | Prompt builders, mechanical per-tier/per-prompt split | yes |
| G-15 | `context/assembler.py` | 1,374 | `assemble()` is 227 lines | **sonnet** | high | One big assembly function; extract per-section builders | yes |
| G-16 | `model/llm_config.py` | 1,086 | 52 funcs; **hosts the `is_local_model()` invariant** | **opus** | med | ⚠️ Splitting this file risks creating a second locality judgment — forbidden by the invariants list. If split, `is_local_model()` stays the single public choke point and other modules import it; do not re-derive locality anywhere. Consider whether this file should be split at all. | yes but invariant-bearing |
| G-17 | `mcp/config.py` | 1,117 | 28 funcs | **sonnet** | med | Parser vs. model vs. validation split | yes |
| G-18 | `dashboard/routes/discovery.py` | 1,085 | 12 route funcs | **sonnet** | med | Route-domain split, same pattern as G-01 | yes |

## Tier table — frontend god files

| Packet | Target | Lines | Shape | Model | Effort | Notes | File-disjoint? |
|---|---|---|---|---|---|---|---|
| G-19 | `pages/Storage.tsx` | 1,760 | 12 components in one page file | **sonnet** | high | Mechanical component extraction to `pages/storage/`; verify no shared-state coupling between extracted components | yes |
| G-20 | `components/agent/AgentChat.tsx` | 1,524 | the chat surface — highest-churn UI file | **sonnet** | high | Extraction is mechanical but the file is actively worked on (chat-UI modernization phases); coordinate timing | no (active seam) |
| G-21 | `hooks/useAgentStream.ts` | 1,521 | one hook = event switchboard | **opus** | med | The right shape is a handler registry (event-type → handler), not "split file in half" — that's a design call, hence opus | yes |
| G-22 | `pages/Sharing.tsx` | 1,163 | | **sonnet** | med | Component extraction | yes |
| G-23 | `pages/Network.tsx` | 1,011 | | **sonnet** | med | Component extraction | yes |
| G-24 | `components/ComponentLibraryViewer.tsx` | 1,061 | reference viewer, not a shipping surface | **sonnet** | med | Lowest priority of the set | yes |

## Tier table — data disguised as code

| Packet | Target | Lines | Shape | Model | Effort | Notes |
|---|---|---|---|---|---|---|
| G-25 | `scripts/macos_command_data.py` | 3,626 | 0 functions, 1 assignment — a pure literal | **fable** | med | Move to JSON/JSONL; update the one reader. Narrow, deterministic, zero judgment. |
| G-26 | `rag/scrapers/*_docs.py` family (15 files: shell, containers, systemd, security, networking, filesystem, git, ubuntu, performance, logging, scheduling, flatpak, snap, appimage + `macos_support.py`) | **19,101 total** | uniform: 1 class + ~11 `_X_guide()` methods returning synthetic document text | **sonnet** | xhigh | One generic data-driven scraper + content moved to markdown/JSONL. Per-file mechanical but the loader design + 19k-line migration is the effort. Founder may also reasonably rule "leave it — it's uniform and it works." |
| G-27 | `ingestion/redaction.py` | 1,698 | 45 funcs + 61 module-level assignments (pattern tables) | **opus** | med | ⚠️ Needs a ruling FIRST: AGENTS.md names `redaction_registry.py` the enforced choke point. Determine whether `redaction.py` is (a) the pattern source the registry reads, (b) a parallel second implementation (invariant violation), or (c) dead code. Only then decide split/move/delete. |

## Left alone deliberately

- **Test files** at 1,200–1,500 lines (`test_mcp_health`, `test_mcp_client`, `test_thread_store`, `test_threads`, `test_redaction_secrets`, `test_mcp_package_preflight`) — big test files are normal.
- `frontend/src-tauri/src/audio_capture.rs` (849) — largest Rust file, fine as-is.
- Everything under 1,000 lines — diminishing returns for this pass.

## Structural findings that constrain dispatch

From `prep_audit` + atlas:

- **`obs/logging.py` is a critical hub: 418 incoming deps.** No packet should touch it; it's listed here only as a blast-radius warning for anything that renames logging calls during extraction.
- **Import cycle**: `agents/conversation_status.py` ↔ `agents/states.py` — same package as G-04. Breaking it should be folded into G-04's split (extract shared types), not attempted separately.
- `agents/state_machine.py`, `conversation_sqlite.py`, `threads.py` (G-04/G-05/G-12) form one cluster — dispatch sequentially, same owner ideally, since they share turn-lifecycle semantics.

## Recommended dispatch order

**Wave 1 — sonnet, file-disjoint, ultracode-eligible (parallel worktrees):**
G-01 (settings routes), G-02 (CLI main), G-08 (system_profile scanner), G-19 (Storage.tsx)

**Wave 2 — sonnet mechanical, sequential-ish:**
G-10, G-11, G-14, G-15, G-17, G-18, G-22, G-23, G-24, G-25 (fable), G-26

**Wave 3 — opus, one at a time:**
G-03 (app.py mount order) → G-07 (mcp/server) → G-09 (mcp/client) → G-06 (routes/agent) → G-13 (executor) → G-21 (useAgentStream) → G-27 (redaction ruling)

**Wave 4 — the cluster, sequential, opus:**
G-05 (conversation_sqlite) → G-12 (threads) → G-04 (state_machine, includes the cycle break) → G-20 (AgentChat, after chat-UI work settles)

**Hold / rule first:** G-16 (`llm_config.py` — invariant-bearing; may legitimately stay whole), G-27 (ruling before any split), G-26 (founder may rule "leave it").

## Verification contract per packet

Every packet, regardless of tier:

1. **Route files**: dump the OpenAPI/route table before and after — must be identical (paths, methods, auth mounts).
2. **CLI**: `halbert --help` and each subcommand's argparse surface unchanged.
3. **Class splits**: public API re-exported from the original import path — no caller edits outside the packet.
4. **Full suite**: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests` (or `./wt_pytest.py` from a worktree). Compare against the merge-base failure baseline — `main` is not green.
5. **Frontend**: `npm run typecheck` + `npm test` at root.
