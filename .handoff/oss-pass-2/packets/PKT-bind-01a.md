# PKT-BIND-01a — Config CAS precondition (base-hash guard)

Tier: **opus**   Milestone: **M2**   Effort: **S**
Collision lane: **N,O**   Merge order: **2/2 in N; 1/2 in O**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**BIND-01a** — Config CAS precondition (base-hash guard).

## 2. User problem

models.yml — the store that holds every cloud API key, every saved endpoint, and the chat/specialist/vision slot assignments — is read-modify-written with no concurrency guard at all, while the founder runs concurrent Claude sessions against the same checkout. OC05's verifier confirmed this as a live lost-update defect: `halbert_core/halbert_core/model/llm_config.py` `save()` (`llm_config.py:765-778`), `update()` (`:821-838`), `set_top_level()` (`:846-862`), and `ensure_endpoint()` all funnel through `_read_for_write()` → mutate → `_write_raw()` with no check that the file didn't change between the read and the write. Two dashboard sessions (or a session plus a peers-route write from `routes/peers.py:581`, or a compression write from `routes/compression.py:109`) that each load the config, mutate their own copy, and save will silently drop whichever write landed first — an API key added in session A vanishes when session B's stale payload is written over it. The contrast case already in the tree proves the expected bar: `config/being_config.py:506-598` takes an advisory `fcntl.flock` around its read-modify-write cycle specifically because concurrent writers exist. The same defect shape repeats for preferences.yml: `dashboard/routes/settings.py:476-493` (`/computer-name`) and `settings.py:1093-1111` (onboarding complete) both do `yaml.safe_load` → mutate → `open(path,'w')` with no lock and no atomic rename — a crash mid-write truncates the file, and a concurrent write loses updates. `_write_raw` is already atomic (temp file + `os.replace` + 0600), so the missing piece for models.yml is purely the compare-and-set precondition; preferences.yml needs the guard and the atomic write. The dashboard's own settings drawer is a read-modify-write over HTTP (`routes/llm.py:283-312` serves `_editor_payload()` on GET and accepts a deep-merge PUT), which means the natural fix — a base-hash precondition echoed by the GET and returned by the PUT — fits the existing round trip without a new endpoint.

## 3. What to build

Add a compare-and-set precondition to the models.yml write path and extend it to preferences.yml, in four pieces:

1. Content hash helpers in `halbert_core/halbert_core/model/llm_config.py`. Add `current_base_hash() -> str` — sha256 of the canonical YAML dump of the parsed dict that `_read_for_write()` returns (hash the parsed structure re-serialised with `sort_keys=True`, not the raw bytes, so a semantically identical reformat doesn't trip the guard). Change `save(llm_config, *, base_hash: Optional[str] = None)`, `update(partial, *, base_hash=None)`, and `set_top_level(key, value, *, base_hash=None)` so that when `base_hash` is provided, the writer recomputes `current_base_hash()` immediately after its own `_read_for_write()` and raises a new `ConfigConflictError(path, expected=base_hash, actual=current)` on mismatch — before any mutation or backup. `ConfigConflictError` subclasses `ConfigUnreadableError`'s sibling pattern: carries `path` plus the two hashes, message states the file changed since the caller read it. `ensure_endpoint`/`ensure_*` stay unconditional (idempotent creates; a conflict there is a no-op anyway). Because the dep `durable_write` (shared `utils/durable_write.py`, listed in the backlog's shared-recipes table for OTHER-P5/BIND-01/scheduler) does not exist in the tree yet, keep `_write_raw` as-is — it already does temp-file + `os.replace` + 0600 — and route preferences.yml through a new `halbert_core/halbert_core/utils/durable_write.py` ONLY if the dependency unit has landed first; otherwise write preferences through the same tempfile/`os.replace` recipe inline in a small helper inside `settings.py` (do not create a second copy of the recipe if `utils/durable_write.py` exists — import it).

2. Wire the HTTP round trip in `halbert_core/halbert_core/dashboard/routes/llm.py`. `_editor_payload()` gains a top-level `"base_hash": llm_store.current_base_hash()` (hash of the global layer's owning file, computed once per GET alongside the payload). `LLMConfigUpdate` gains `base_hash: Optional[str] = None`; the PUT passes it to `llm_store.update(body.llm_config, base_hash=body.base_hash)` and catches `ConfigConflictError` with a 409 `{"error": {"code": "CONFIG_CONFLICT", "path", "message"}}` mirroring the existing `CONFIG_UNREADABLE` shape at `routes/llm.py:295-303`. A client that omits `base_hash` writes unconditionally (legacy path preserved — the CLI and tests call `update()` directly with no hash).

3. preferences.yml in `halbert_core/halbert_core/dashboard/routes/settings.py`. The two raw writers — `/computer-name` (`settings.py:476-493`) and onboarding-complete (`settings.py:1093-1111`) — get the same treatment behind a module-level `asyncio.Lock` (the `_being_config_lock` pattern at `settings.py:31`): load → mutate → write under the lock, write via temp-file + `os.replace`, chmod 0600. In-process lock suffices here: preferences.yml writers are these two dashboard routes only, both in one process; models.yml has cross-process writers (CLI, peers, compression) which is why it gets the content-hash CAS instead of a lock.

4. Tests in `halbert_core/tests/test_llm_config_store.py` (extends the existing `models_config_dir` fixture file) and `halbert_core/tests/test_settings_model_routes.py`: stale-hash save raises `ConfigConflictError`; matching-hash save succeeds; omitted hash writes unconditionally; PUT with a stale hash returns 409 `CONFIG_CONFLICT`; GET payload contains `base_hash` and a PUT echoing it back succeeds; a concurrent `set_top_level` between hash capture and `update()` is detected.

## 4. What NOT to build

- No flock/fcntl locking on models.yml. The being_config.py flock is the in-tree precedent, but an advisory lock only serialises writers that cooperate, and the CLI/tools writers would each need the lock too — a missed call site re-opens the hole. The base-hash CAS catches the conflict at the single choke point (`save`/`update`/`set_top_level`) regardless of which caller forgot what. If the founder later wants blocking semantics, that is a follow-up decision, not this unit.
- No file-binding/TOCTOU work (`bind_path()` activation in `lease.py`, `utils/path_boundary.py`, symlink checks) — that is BIND-01b, sequenced after R-08/R-07 per the RESHAPE verdict.
- No `allowed_hosts` per-credential egress binding (gated on founder decision FD-4) and no file-delivery convention (FD-3) — both DEFERRED per the deep-eval.
- No reload-plan / projected-view diff work (OTHER-P6b owns the settings.py reload table; do not touch the hot-reload path in this lane-E file beyond the two named write sites — rebase risk is flagged in the registry).
- No schema changes to models.yml, no migration of existing files, no changes to `_carry_forward_api_keys` or the slot-validation logic in `update()`.
- No frontend changes beyond what the PUT already returns: the UI may ignore `base_hash` initially and keep writing unconditionally; surfacing a conflict notice in the drawer is a SURFACE-01 follow-on, not this packet.
- No change to `ensure_*` call sites' behaviour, and no guard on read paths.

## 5. Target files
- `halbert_core/halbert_core/model/llm_config.py`
- `halbert_core/halbert_core/dashboard/routes/settings.py`

## 6. Dependencies

durable_write

## 7. Effort

**S** — S. The whole change is: one sha256 helper (~15 lines), one exception class (~10 lines), an optional keyword threaded through three functions in one file (`llm_config.py` `save`/`update`/`set_top_level` — the mutation logic itself is untouched), one field on a pydantic model plus one 409 branch in `routes/llm.py` (the `CONFIG_UNREADABLE` handler at :295-303 is the exact template), and two write sites in `settings.py` swapped to a locked atomic write following the `_being_config_lock`/`os.replace` patterns already in that file and in `_write_raw`. No new dependencies (hashlib, tempfile, os.replace are stdlib and `_write_raw` already proves the atomic recipe in-module). The risky part is not the code but lane E: `settings.py` is 3,491 lines and shared with OTHER-P6b, so the diff there must stay confined to the two named functions — no drive-by refactors, and rebase on main immediately before merging. Test cost is low: `test_llm_config_store.py` already has the `models_config_dir` fixture and atomic-write test (`test_atomic_write_leaves_original_intact_on_failure` at :244) to copy.

## 8. UX rationale

No new surface. The dashboard settings drawer keeps working unchanged: GET `/llm/config` silently carries an extra `base_hash` field, and a PUT that omits it behaves exactly as today. The only user-visible change is a failure mode that replaces silent data loss: when two sessions race a config save, the loser's PUT now returns 409 `CONFIG_CONFLICT` instead of overwriting the winner's API key — the drawer's existing error handling displays the message, and a re-GET (which the drawer already does after a failed save path) refreshes to the current state so the user re-applies their change on top of the winner's, never blindly. Nothing is named on any surface beyond the error string; the message names the file path and says the configuration changed since it was loaded — first-person computer voice is not triggered here because this is a machine-level 409 payload, and no model, colour, or emoji is involved. Onboarding and `/computer-name` writes become crash-safe (no half-written preferences.yml after a power cut) with zero visible change.

## 9. Acceptance criteria

1. `llm_config.save()`/`update()`/`set_top_level()` accept `base_hash=` and raise `ConfigConflictError` when the file's current content hash differs, before mutating or backing up; omitted hash preserves today's unconditional write.
2. GET `/llm/config` response contains `base_hash`; PUT `/llm/config` echoing a fresh `base_hash` succeeds (200), echoing a stale one returns 409 with `error.code == "CONFIG_CONFLICT"`; PUT with no `base_hash` succeeds (back-compat for the CLI and existing tests).
3. Two interleaved writers against models.yml — A reads, B reads, B writes, A writes with A's stale hash — A's write is refused and B's API key survives in the file on disk (the exact OC05 lost-update scenario, now failing closed).
4. `/computer-name` and onboarding-complete writes to preferences.yml go through an in-process lock and temp-file + `os.replace` (no `open(path,'w')` remaining on that file), mode 0600.
5. `ensure_ollama_endpoint`/`ensure_endpoint` call sites (`settings.py:273-274`, `peers.py:576-581`) are untouched in behaviour.
6. No changes outside `model/llm_config.py`, `dashboard/routes/llm.py`, `dashboard/routes/settings.py`, and the two test files; the settings.py diff touches only the two write functions (OTHER-P6b rebase guard).

## 10. Verification (measured state, not model judgment)

From the worktree root: `arch -arm64 ./wt_pytest.py halbert_core/tests/test_llm_config_store.py halbert_core/tests/test_settings_model_routes.py -x -q` — must exit 0, including the new tests: `test_update_with_stale_base_hash_raises_conflict`, `test_update_with_matching_base_hash_succeeds`, `test_put_llm_config_conflict_returns_409`, `test_editor_payload_includes_base_hash`. (If running from the main checkout instead of a worktree: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_llm_config_store.py halbert_core/tests/test_settings_model_routes.py -x -q`.) Plus a measured end-to-end check of the race itself, run as a script against a temp config dir: session A calls `current_base_hash()`, an interleaving `set_top_level("compression", {...})` lands, then A's `update(partial, base_hash=...)` must raise `ConfigConflictError` and `grep` of the on-disk models.yml must still show the interleaved key — assert on file contents and the raised exception type, exit code 0. Finally `arch -arm64 ./wt_pytest.py halbert_core/tests -k "llm_config or settings_model or compression" -q` to confirm no regression in the neighbouring writer routes (compression.py:109, peers.py:581 paths); compare against the known nonzero main baseline before attributing any failure to this change.

## 11. Exclusions

BIND-01b (file-binding security: `bind_path()`/`is_governed_path()` activation, `utils/path_boundary.py`, exec allowlist resolution, shell env stripping, scratch relocation, deny-always-wins, scope-escalation lattice) → goes to unit BIND-01b, sequenced after R-08 and R-07 settle per the RESHAPE verdict. `allowed_hosts` per-credential egress binding → dropped per RESHAPE, deferred to founder decision FD-4. File-delivery convention → dropped per RESHAPE, deferred to founder decision FD-3 (the section file's own recommendation was "no for now"). The wider durability story (shared `utils/durable_write.py` helper, last-known-good recovery, polluted-placeholder gating for install identity) → M5b tail / OTHER-P5, which owns the durable-write recipe; this unit imports it if present but does not build it. The settings reload plan and projected-view diff → OTHER-P6b (lane-E co-owner). The approval-expiry enforcement and stale-tone overrides → SURFACE-01 sub-items. Frontend conflict-notice UX in the settings drawer → SURFACE-01 follow-on; this packet ships the 409 contract only. Sensitivity tiers on the AI-proposed diff path and write-only secret response models → BIND-01b's config-write trio remnant (OC12-M5/OC23-M2), not the CAS precondition.

---

## OSS reference

Greenfield — no direct OSS reference; see the deep-eval.

## Repo traps

- Every Python test run needs the `arch -arm64` prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests`.
- From a git worktree use `arch -arm64 ./wt_pytest.py halbert_core/tests`, NEVER bare pytest (the editable install pins halbert_core to the MAIN tree).
- `main` is NOT green. Known-red baseline (2026-09-11): test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py (~23 failures). A failure is yours iff absent from this baseline.
- Work in a git worktree; narrow commits; concurrent sessions edit this repo.
- NEVER add Co-Authored-By or 'Generated with …' trailers. Subject + body only.
- No emoji anywhere. Colours only from shared-tokens/tokens.css (run scripts/check_contrast.py).
- Never name/recommend an AI model on any user-facing surface; connection slots, not model menus.
- Model locality: is_local_model() (model/llm_config.py:181) is the ONLY judge; :cloud tag is primary.
- Feature gating: has_capability() (capabilities.py:499); never _is_home_variant.
- Redaction: ingestion/redaction_registry.py enforced at security/display_transport.py; scrub BEFORE the model.
- Commands staged from the UI are staged, never executed.
- No users yet: no migrations/back-compat shims unasked; leave superseded data on disk, unread, never delete.
- Line references drift: re-anchor by grep before editing; a failed anchor is a rebase signal, not a spec change.
- Modify only this packet's Target files. .handoff/ is correspondence, not authority (ROADMAP.md + DECISIONS.md are the spine).
