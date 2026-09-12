# PKT-durable_write — Atomic durable-write helper

Tier: **fable**   Milestone: **M0**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**durable_write** — Atomic durable-write helper.

## 2. User problem

Halbert has no single atomic durable-write primitive, so the "temp file in target dir + flush + fsync + os.replace + directory fsync + mode 0600" recipe is re-implemented per call site — and several live sites skip steps. Evidence: `halbert_core/halbert_core/scheduler/run_receipts.py:103-133` `_flush()` is the one correct in-tree implementation (mkstemp in target dir, fsync file, `os.replace`, fsync directory) but it is private to the receipt store. `halbert_core/halbert_core/model/llm_config.py:765-778` `save()` → `_write_raw()` rewrites `models.yml` (the API-key store) with no atomic recipe at all, while the founder runs concurrent sessions — a lost-update on secrets. Audit gap A12-G8 confirms `guest_homes.yml` is renamed without fsync, and the A06 own-bug is a restart-ledger write missing the directory fsync. Deep-eval cross-cutting opportunity #6 names this exactly: "Halbert already uses `os.replace` for local state (`scheduler/run_receipts.py:121`, `consent/store.py:599`) but not for identity or network-fetched files. The recipe should be a shared `utils/durable_write.py` helper, not reimplemented per-packet" — and final backlog §3.4 lists it as a cross-cutting primitive to build first, consumed by OTHER-P5 (install identity, bounded download), BIND-01a (config writes), scheduler receipts, guest_homes, plus packet-registry consumers MEM-P3-backup, P2, and TT-01. Standing rules engaged: "one place each thing is decided" (no duplicate primitives — the standing rules in the final backlog §3 explicitly forbid building this per-packet) and the two-dependency contract (this helper is stdlib-only: os, tempfile, errno — no new hard dependency).

## 3. What to build

Create exactly one new module `halbert_core/halbert_core/utils/durable_write.py` (stdlib-only: `os`, `tempfile`, `errno`, `contextlib`, `typing`; no yaml/requests needed — call sites serialize before calling). Public surface, mirroring the proven recipe at `scheduler/run_receipts.py:103-133`:

1. `durable_write_bytes(path: Path | str, data: bytes, *, mode: int = 0o600, dir_fsync: bool = True) -> None` — the core primitive. Steps, in order: resolve `path` to its parent `directory` (default "." when bare); `os.makedirs(directory, exist_ok=True)`; `tempfile.mkstemp(dir=directory, prefix=<basename> + ".", suffix=".tmp")` so the temp file is on the same filesystem as the target (required for atomic `os.replace`); wrap the fd in `os.fdopen(fd, "wb")`; `f.write(data)`; `f.flush()`; `os.fsync(f.fileno())`; `os.fchmod(f.fileno(), mode)` (default 0600 — several consumers write secret-bearing state: `models.yml` API keys, guest homes, install identity); close; then `os.replace(tmp_path, path)`; then, when `dir_fsync`, `os.open(directory, os.O_RDONLY)` → `os.fsync(dir_fd)` → `os.close(dir_fd)` so the rename itself is durable. On any `BaseException` after mkstemp: best-effort `os.unlink(tmp_path)` (swallow `OSError`) and re-raise — the crash-mid-write contract is "either the old or the new full state, never a torn file," matching the docstring at `run_receipts.py:104-105`.

2. `durable_write_text(path, text: str, *, encoding: str = "utf-8", mode: int = 0o600, dir_fsync: bool = True) -> None` — thin wrapper: `durable_write_bytes(path, text.encode(encoding), mode=mode, dir_fsync=dir_fsync)`. Text is the common case (YAML/JSON state files); bytes is the general case (bounded-download `.partial` files in OTHER-P5).

3. `fsync_directory(directory: Path | str) -> None` — exported standalone because OTHER-P5's install-identity flow (mkstemp + fsync + os.replace, minted once) and the A12-G8 `guest_homes.yml` fix each need a directory fsync after their own rename without re-walking the whole write path. Keep it tiny: open O_RDONLY, fsync, close, in try/finally.

Design constraints the implementer must hold: (a) no flocking inside this helper — `being.yml`'s flock-guarded read-modify-write (see deep-eval F06 reasoning: `models.yml`'s RMW is unlocked while `being.yml`'s is flock-guarded) is a separate concern owned by BIND-01a's CAS work; this helper is the write half only and must compose under a caller-held lock; (b) mode is applied by `fchmod` before the rename, never by a post-rename chmod (a post-rename chmod re-opens a TOCTOU window on a secret-bearing file); (c) no logging of file contents — at most a `logging.getLogger(__name__).debug` of the target path on failure; (d) no new third-party imports, per the Haloysius two-dependency contract; (e) module docstring states the crash contract and names the canonical consumers so the next session does not invent a fourth implementation. Unit tests land in `halbert_core/tests/test_durable_write.py` (new file): tmp_path fixtures, assert file contents after write, assert mode bits are 0600, assert no `*.tmp` residue on success, assert temp-file cleanup on injected failure (monkeypatch `os.replace` to raise), and a directory-fsync spy test (monkeypatch `os.fsync` and count calls: exactly 2 per write — file + directory). No existing file is modified in this unit; adoption is the consumers' packets.

## 4. What NOT to build

Do NOT migrate any existing call site in this unit — `scheduler/run_receipts.py:_flush()` keeps its private copy until SCHED-P1/OTHER-P5 adopts the helper (the final backlog keeps R-03's receipt work unmerged on the sonnet branch; touching it here invites a cross-branch conflict). Do NOT add advisory locking (flock/fcntl) — that is BIND-01a's CAS-precondition scope for `models.yml` and `being.yml`; this helper must compose under a caller-held lock, not grow one. Do NOT build OTHER-P5's `install_id.py` minting flow, `bounded_download.py`, or the `.partial` single-flight logic — those are consumers with their own verdicts (OTHER-P5 RESHAPE: install identity ships early, bounded download next). Do NOT touch `model/llm_config.py:save()`/`_write_raw()` — rerouting the API-key store's write path is BIND-01a's job and rides with its base-hash guard, not here. Do NOT add YAML/JSON serialization conveniences (`durable_write_yaml(obj)`) — that would pull `yaml` into a stdlib-only leaf module and invite format-specific forks; call sites serialize, then call. Do NOT fsync on every platform defensively with platform branching beyond what `os` provides — no `fcntl.F_FULLFSYNC` special-casing in this unit; if a macOS-specific durability gap is later proven, it lands as a documented revision, not a speculative branch. Do NOT add async variants (`aiofiles`-style) — no consumer is async-bound on file I/O, and a third hard dependency is forbidden. No logging of payloads, no redaction logic (callers scrub before write per the Tier-2 rule), no retry loop, no backup/rotation of the previous file (last-known-good retention is F06 config-state durability, a READ-NOW follow-up, not this S-sized primitive).

## 5. Target files
- `halbert_core/halbert_core/utils/durable_write.py` [new file]

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S (small). One new leaf module, ~70-100 lines including docstrings, plus one test file of similar size. The recipe is not being designed from scratch — it is extracted from the proven `scheduler/run_receipts.py:103-133` implementation whose steps are already enumerated in two authoritative docs (deep-eval opportunity #6 and final backlog §3.4: "temp file in target dir, write + flush, fsync, os.replace, directory fsync, optional mode/chmod"). There are no dependencies (registry says "Dependencies: none"), no hot-file risk (the module is new; zero existing imports), no founder-decision gates on the helper itself (FD gates in OTHER-P5/BIND-01a attach to the consumers, not the primitive), and no behavior change to any live path until consumers adopt it. The S sizing is what makes it the correct first build in M0: final backlog §3 says cross-cutting primitives "should be built once, before fanning out the dependent packets," and §3.4 names five consumers (OTHER-P5 install identity, OTHER-P5 bounded download, A06 ledger fsync, A12-G8 guest_homes rename, BIND-01 config writes) plus the packet registry adds MEM-P3-backup, P2, and TT-01 — eight adopters amortizing one small build, versus the standing-rule-forbidden alternative of eight divergent copies.

## 8. UX rationale

No user-facing surface. This is a stdlib leaf helper consumed only by backend code; nothing renders, nothing speaks. Consistency obligations it must not break downstream: (1) secret-bearing state files (`models.yml` API keys, `guest_homes.yml`, install identity) get mode 0600 by default — that is the mechanism keeping secrets off other local accounts, aligned with the Tier-2 determinism rule (secrets are handled by deterministic mechanism, never model judgment); (2) the crash contract (old or new, never torn) is what lets the machine keep speaking as itself in first person grounded in measured data after a power cut — a half-written `models.yml` or receipt ledger would surface later as the machine misreporting its own configuration, the exact failure mode OTHER-P3's "measured, not assumed" verdict attacks; (3) the module emits no UI copy, no emoji, no color, no model names — its only observable artifact is a debug-level log line naming a path on failure, which LOG-01/OTHER-P2's redacting filter will process like any other record.

## 9. Acceptance criteria

1. `halbert_core/halbert_core/utils/durable_write.py` exists and exports `durable_write_bytes`, `durable_write_text`, and `fsync_directory` with the signatures in field 3; importing it pulls no third-party module (verifiable by import in a bare interpreter with only the stdlib path).
2. Write semantics: after `durable_write_text(p, "x")`, `p` contains exactly "x"; the file's permission bits are 0600 by default and honor an explicit `mode=` override; no `*.tmp` sibling remains in the directory on success.
3. Crash contract: when `os.replace` is monkeypatched to raise, the pre-existing target file is byte-identical before and after the call, the exception propagates, and the temp file is unlinked.
4. Durability ordering: with `os.fsync` spied, a single `durable_write_bytes` call produces exactly two fsync calls — first on the temp file's fd, second on the parent directory's fd (when `dir_fsync=True`; exactly one when `dir_fsync=False`).
5. Same-filesystem guarantee: the temp file is created inside the target's own directory (mkstemp `dir=` argument), never in the system temp dir — asserted by tmp_path inspection during the success test.
6. No existing file in the tree is modified by this unit's diff (adoption is deferred to consumer packets); `git diff --stat` for the unit shows exactly two new files: the module and its test.
7. Composability: the helper contains no flock/fcntl code and no retry loop — greppable absence — so it composes under a caller-held lock as BIND-01a requires.

## 10. Verification (measured state, not model judgment)

Run the new unit's tests plus a collection sanity pass, from the repo root (this checkout runs on the main tree; the `arch -arm64` prefix is mandatory per the venv universal2 rule): `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_durable_write.py -v` — every test passes (exit code 0), covering: content round-trip, 0600 default mode and mode override, no tmp residue, temp-cleanup-and-old-file-intact on injected `os.replace` failure, and exactly-two-fsyncs ordering via monkeypatched spy. Then confirm no collateral damage to the suite's collection and the untouched receipt store: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests -k "run_receipts or durable_write" -q` — durable_write tests pass and the run_receipts selection matches its pre-unit baseline (main is not green overall; compare against a baseline run on the merge-base, per the repo rule, not against zero). If dispatching from a worktree instead of the main checkout, substitute `arch -arm64 ./wt_pytest.py halbert_core/tests/test_durable_write.py -v` so the editable-install metapath finder cannot resolve `halbert_core` to the wrong tree. Finally, a measured import check proving the two-dependency contract holds: `arch -arm64 .venv/bin/python -c "import halbert_core.halbert_core.utils.durable_write as m, sys; print(sorted(mod for mod in sys.modules if mod in ('yaml','requests')))"` — output must be `[]` (neither hard dependency is imported by the new module).

## 11. Exclusions

The following are deliberately excluded from this unit, each with its destination: (1) Migrating `scheduler/run_receipts.py:_flush()` to the helper → SCHED-P1 residual / OTHER-P5 coordination (final backlog §3.4: "coordinate with OTHER-P4 on `executor.py` since both touch the restart-ledger fsync"; also blocked on R-03's unmerged sonnet branch touching the same file). (2) The A06 restart-ledger directory-fsync fix → rides in OTHER-P5's fsync-fix bundle per deep-eval OTHER-P5 "The fsync fixes (A06 ledger, A12-G8) ride along." (3) The A12-G8 `guest_homes.yml` rename-without-fsync fix → same OTHER-P5 bundle. (4) OTHER-P5's `identity/install_id.py` minting flow and `utils/bounded_download.py` → OTHER-P5 proper (RESHAPE verdict: install identity ships early because mDNS broadcasts the raw hostname; bounded download ships next; FD-4 gates the node_id switch). (5) Rerouting `model/llm_config.py:save()`/`_write_raw()` and `routes/settings.py:1094-1111` `preferences.yml` writes through the helper plus flock/CAS preconditions → BIND-01a (ACCEPT split of BIND-01: "config CAS preconditions — S, ship now"); the helper is built so BIND-01a can adopt it immediately. (6) MEM-P3's backup snapshot writes, P2's approval-artifact binding writes, and TT-01's atomic write verification → their own packets adopt the helper (named consumers in the unit registry). (7) Last-known-good retention, backup-before-rewrite policy, and polluted-placeholder gating → F06 config-state-durability (READ-NOW follow-up unit), not this primitive. (8) Advisory locking and any `fcntl` usage → BIND-01a's CAS scope. (9) macOS `F_FULLFSYNC` hardening → dropped as speculative; revisit only with measured evidence of a durability gap (no consumer has demonstrated one; `os.fsync` is the in-tree standard at `run_receipts.py:120`).

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
