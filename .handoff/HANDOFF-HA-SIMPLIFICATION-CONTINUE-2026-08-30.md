# Handoff: Continue the HA Simplification Workstream (feat/ha-simplification)

**Date:** 2026-08-30
**From:** GLM-5.3 (ultracode build session)
**To:** Next AI (fable) continuing Batch U6
**Branch:** `feat/ha-simplification` — worktree at `~/.config/superpowers/worktrees/Halbert/ha-simplification`
**Canonical direction:** [`HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md`](HANDOFF-HOME-AUTOMATION-SIMPLIFICATION-2026-08-30.md) — its Section 12 (W1-W25, D1-D4) is the authoritative work list. **Read it first.**

---

## 1. What is done (all committed, verified CLEAN)

Nine commits on top of `main` (`1fd6dba1`):

| Commit | Work |
|---|---|
| `a161bb9a` | **D1** — variant resolution unified on `_get_variant()` (being.yml > env > sysadmin) for `/api/instance/info` and all gating. **Bug fixed en route:** the env leg of the chain was dead — `load_being_config()` returned a truthy `'sysadmin'` default when being.yml lacked a variant key, so `HALBERT_VARIANT` env was never honored by backend gating. New `being_config.explicit_variant()` makes the documented chain actually hold. |
| `226555ef` | **S1 backend** (W1-W3, W6) — secure_model auto-provisioning, wizard writes, and the secure turn path gated off `home`/`home-light`. `llm_config.py` untouched (ships empty by design). |
| `d733ec9a` | **S1 frontend** (W4-W5) — `variants: ["sysadmin"]` on the secure_model role; host-side filtering in `ModelSettings.tsx`/`AgentChat.tsx`. `RoleAssignmentRow` NOT touched (package stays role-agnostic). |
| `5e2ce6b4` | **S2** (W7-W13) — SourcePrep fully gated off HA variants across `agent.py`, assembler factories, `app_seam` (`skip_retrieval`), config-watcher reindex callback, HA-config bridge (default-disabled), `/home/config-search` endpoints removed, `ha_config_tools.py` deleted, deploy artifacts cleaned, `test_ha_phase3.py` retargeted. |
| `6f46f09a` | **S4** (W17-W19) — `recommend_budget()`/`get_installation_commands()` return offload-only for `SBC_LOW_POWER`; `ComputeRouter.route()` implemented (peer → template thoughts, no local attempt); wizard gets an SBC compute-peer prompt + `--peer` CLI flag. |
| `6a077653` | **S6** (W22-W24) — `apple_foundation` stripped from the mDNS `compute_backends` contract everywhere; `test_peer_discovery.py` updated to assert `ollama,vllm`; `PeerAuthMiddleware` ImportError export bug fixed. |
| `5f87520c` | **S3 frontend** (W15) — `ComputePeerCard` replaces the model picker on HA variants (Settings `ai` tab), Test Connection wired to the peer probe, `ChatModelPill` handled for HA. |
| `0514a5c3` | **S3 backend** (W14, W16) — `PeerProvider` registered in the model stack (`CHAT_CAPABLE_PROVIDERS`, tier router, providers `__init__`); peer:// slots now resolve instead of being disabled; compute-peer link persistence route (403s sysadmin, never touches secure_model). *This commit was made by the final verifier — the implementing agent hit a provider-side usage-limit 429 after finishing the code but before committing; the verifier reviewed the uncommitted diff adversarially, ran its 23+ tests, and committed it.* |
| `3ce98551` | **W25** — stale `<=4GB` profile comments corrected to the strict `<4GB` boundary the code enforces. |

**Verification (final pass):** backend suite 49 failed / 3901 passed / 41 skipped — the 49 failures are **byte-identical to the pre-existing main baseline** (they exist on `main` before any of this work; list in `/tmp/worktree-failures.txt`, though /tmp may be swept — regenerate with a main-repo run if needed). Frontend: vitest 437 passed, `tsc --noEmit` clean; model-picker 103 tests passed, `check:boundary` clean. Adversarial diff review found variant gating never touches sysadmin (pinned by dedicated sysadmin regression tests), no ungated SourcePrep construction, secure_model unreachable for HA variants, no hardcoded model names.

**W20/S5 resolution (implemented as a no-change, by design):** on a home node installed per the deploy docs, haloysius is absent (optional `[cognition]` extra, not on PyPI), so the operative memory path is SQLite+FTS5 receipts/threads (`agent.py` wires `memory_service=None`; recall is ThreadManager-owned). **No packaging change is required.** If identity memory is wanted on HA nodes, the additive option is: install haloysius from the sibling checkout + serve embeddings via Ollama (`nomic-embed-text`) or the ONNX native embedder. Never add `sentence-transformers` to any halbert extra (drags torch); never install `[rag-legacy]` (chromadb) on HA nodes.

**W21:** verified by inspection + live call (Memory page returns a sane `chromadb_available: false`); no automated test added — optional follow-up.

---

## 2. What remains — decisions, then code

### 2.1 D2 — the 4GB classification boundary (BLOCKS one test expectation)

Code classifies `SBC_LOW_POWER` as strictly **<4GB**: `hardware_detector.py:423-427` puts `>= 4` GB hosts in `ENTRY_8GB`, whose local-model support is `True` (`compute_router.py:254-266`, pinned by `halbert_core/tests/federation/test_hardware_profile_fallback.py:31-33`). The handoff's device table (§6.2) says 4GB hosts are offload-only. **Pick one:**
- (a) move the boundary (`>= 4` → `> 4`) so 4GB hosts classify `SBC_LOW_POWER`, update `compute_router` docstrings + the fallback test; or
- (b) keep the code and fix the handoff/READMEs to "<4GB" (the README currently says "4 GB RAM or less require a compute peer" — see `HANDOFF-README-HOME-AUTOMATION.md` §3.5/§3.7).

Note: `hardware_detector.py` is model-name-agnostic by design; there are no 1B/Q2_K strings in code anywhere.

### 2.2 D4 — should `home` merge into `home-light`?

The service-skip matrix in handoff §12.1 was **verified correct** against `dashboard/app.py`. Two nuances the matrix missed, both **strengthening the merge case**:
1. The home-variant scheduler already runs with `enable_llm=False` (`app.py:490`) — its proactive jobs (detector sweep, morning report, VisualWatcher) are sysadmin-telemetry jobs that never use the LLM.
2. `app.py:423-425`'s comment claims home-light skips "ChromaDB-heavy init" — **no such gating code exists**; ChromaDB is simply lazily imported by routes. (Trivial correction: the router block is `:274-306`, not `:272-306`.)

If merged: S2's config-watcher gating collapses into the merge, and one variant name disappears from all `HA_VARIANTS` checks.

### 2.3 Q3 — remove `vision_model` from HA variants? (evidence says: safe)

Investigation verdict: **effectively vestigial on the HA/Frigate path.** The Frigate MQTT subscriber/event mapper never performs vision-model inference (Frigate does detection; Halbert consumes labels/scores). Remaining consumers on a home variant: images attached in dashboard chat, explicit vision pins, intake recommendations, capture tools (off on headless nodes), and peer vision offload. All fall through gracefully to the guide model when the slot is empty (which is how it ships). Removing the slot breaks nothing structurally; the one UX cost is attached-photo chat silently routing to a possibly non-multimodal chat model. Recommended: remove from the HA config surface, keep the fallbacks, document that a multimodal chat_model covers the photo case.

**Latent issue worth fixing either way:** Frigate REST tools return snapshots as base64 data-URI *strings*, and the state machine only auto-routes dict results with an `"image"` key to the vision model (`state_machine.py:2464-2478`) — so today a Frigate snapshot lands as a giant text observation (context bloat), never reaching vision at all.

### 2.4 Q4 — disable `advance_turn` on HA variants? **Read this first — it contains a live bug**

Key facts (all verified in the current tree):
- `advance_turn` fires **only on explicit chat turns** (dashboard + Wyoming share one agent singleton). There is no autonomous loop wired — `HomeCognitiveLoop` (`halbert_core/halbert_core/home/cognitive_loop.py`) is dead code, referenced only by `home/__init__.py` and its test.
- Template-thoughts mode (default, `HALBERT_LLM_THOUGHTS` unset) does decay/trigger/reinforce/promotion with canned thoughts — zero LLM cost.
- **The tick is the ONLY thing that drains the HA and Frigate event queues** (`state_machine.py:2607-2609` `populate_cognition`; queues are plain lists with no maxlen — `ha_event_mapper.py:34`, `frigate_event_mapper.py:120`).
- **Live bug:** on any haloysius-less install (e.g. a `[light]` home-light node), `get_cognition_tick()` raises ImportError → tick is skipped → the HA WebSocket stream (`app.py:657-676`) and Frigate MQTT (`:700-732`) still start (ungated) → **the queues grow unbounded**. This leak exists on main today.

So the real choice: (a) keep `advance_turn` on HA variants (it costs no LLM and drains the queues), or (b) disable it **together with** skipping/bounding the event streams. The current middle state (streams on, tick off) is the one configuration that actively leaks. If you disable the monologue, bound or skip the streams in the same change, or add a timer flush without advance_turn.

### 2.5 Minor open findings from the verify pass (non-blocking)

1. `routes/compute.py` `peer_probe` returns HTTP 200 with an `{'error': ...}` envelope while sibling `POST /api/peers/compute-peer` raises HTTPException — cosmetic API-convention drift (frontend handles both).
2. `providers/peer.py` `is_loaded(PEER_GOVERNED_MODEL)` returns True unconditionally — deliberate while the workstation models route is a stub; revisit at federation-9.3.
3. `client.py` `_call_peer` with `stream=True` raises NotImplementedError (redaction across SSE boundaries unsolved, TODO federation-9.4) — fails loudly, which is the documented correct behavior.
4. `useInstanceVariant.ts` (+ its test) missing trailing newlines.
5. `app.py:432/:456` log strings still say "HALBERT_VARIANT=home" — cosmetic, harmless now that the chain actually works.

---

## 3. Environment & verification notes for continuing sessions

- **Test runner:** `cd <worktree>/halbert_core && arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest -q`. The `arch -arm64` prefix is mandatory (universal2 venv). Run pytest from `halbert_core/`, never the repo root (namespace-import gotcha).
- **Baseline:** 49 pre-existing failures exist on `main` — identical list before and after this work. The bar is "no new failures beyond those 49." Regenerate the baseline list from a main-repo run if `/tmp/worktree-failures.txt` is gone.
- **Frontend:** node_modules IS installed in this worktree; vitest + tsc + model-picker `check:boundary` all runnable.
- **Haloysius** is not on PyPI — `[cognition]` installs from a sibling checkout; without it the cognition tick ImportError-skips (non-fatal).
- Concurrency: the user runs multiple AI sessions on this repo. Commit with explicit pathspec `git add <files>` only; never `-A`. NEVER add Co-Authored-By/attribution trailers. Never name or recommend specific AI models in code or docs.

## 4. Suggested next steps (in order)

1. Resolve **Q4 first** — it contains the live unbounded-queue leak, which is a real bug regardless of the monologue decision. Minimal fix: bound both mapper queues (maxlen deque) + flush-or-drop policy; then decide keep-vs-disable with the streams in mind.
2. **D2** — one-line code change or a docs fix; unblocks the final `test_hardware_profile_fallback` 4GB expectation.
3. **Q3** — remove vision_model from the HA config surface (graceful fallbacks stay); consider routing Frigate snapshots as images instead of text observations.
4. **D4** — merge decision; if yes, collapse the variant checks and delete the home-only service blocks.
5. Minor findings §2.5 as cleanup.
6. When all of Batch U6 is done, the follow-ups in the canonical handoff §10 (federated Phase 9) become the next target — this work deliberately precedes Phase 9.