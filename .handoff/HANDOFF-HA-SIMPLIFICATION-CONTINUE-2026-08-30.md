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

## 2. Decisions resolved

### 2.1 D2 — the 4GB classification boundary — RESOLVED (option b)

**Decision: keep the code, fix the docs.** The code classifies `SBC_LOW_POWER` as strictly **<4GB** (`hardware_detector.py:423-427` puts `>= 4` GB hosts in `ENTRY_8GB`). W25 (`3ce98551`) corrected the stale `<=4GB` comments to `<4GB`. No code change needed.

### 2.2 D4 — merge `home-light` into `home` — RESOLVED (yes, merged)

**Decision: merge.** There was never a real distinction between `home` and `home-light` — it has always been just `home`. The `home-light` variant was removed from `VALID_VARIANTS`, `HA_VARIANTS`, and all gating/checks across the backend, frontend, tests, and deploy docs. The single `home` variant now carries the thin-client behavior (skip scheduler, config watcher, terminal sessions, seed HA from being.yml). Committed in the D4 merge commit.

### 2.3 Q3 — remove `vision_model` from HA variants? — RESOLVED (no, keep it)

**Decision: keep `vision_model` on HA variants.** The handoff's "vestigial" reasoning was wrong for the actual use case. The vision_model slot exists for two reasons: (1) a text-only chat model needs a vision option, and (2) a user may want a specific vision model separate from the chat model. A sentient home AI with cloud chat + local vision is a legitimate configuration. The "graceful fallback to chat model" only works if the chat model is multimodal — if it isn't, removing vision_model silently breaks photo understanding. The slot stays.

**Latent issue still worth fixing:** Frigate REST tools return snapshots as base64 data-URI *strings*, and the state machine only auto-routes dict results with an `"image"` key to the vision model (`state_machine.py:2464-2478`) — so today a Frigate snapshot lands as a giant text observation (context bloat), never reaching vision at all. This is a bug independent of the vision_model decision.

### 2.4 Q4 — disable `advance_turn` on HA variants? — RESOLVED (no, premise was wrong)

**Decision: keep `advance_turn`; the "haloysius-less install" scenario is not real.** Haloysius is fundamental — every Halbert install includes it. The handoff's concern about `get_cognition_tick()` raising `ImportError` on a "haloysius-less" install describes a configuration that does not exist in practice. The `[cognition]` extra is not optional for HA variants; haloysius is part of the core stack.

**Defensive note:** the HA/Frigate event queues (`ha_event_mapper.py:34`, `frigate_event_mapper.py:120`) are plain lists with no `maxlen`. While the tick drains them in practice, bounding them with a `deque(maxlen=...)` would be a cheap defensive improvement. This is non-blocking.

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

1. **Frigate snapshot routing bug** (from Q3 investigation): Frigate REST tools return snapshots as base64 data-URI strings, but the state machine only auto-routes dict results with an `"image"` key to the vision model. Fix: route Frigate snapshots as images, not text observations.
2. **Defensive queue bounding** (from Q4 investigation): bound the HA/Frigate event queues with `deque(maxlen=...)` so a slow tick can never cause unbounded memory growth.
3. Minor findings §2.5 as cleanup.
4. When all of Batch U6 is done, the follow-ups in the canonical handoff §10 (federated Phase 9) become the next target — this work deliberately precedes Phase 9.