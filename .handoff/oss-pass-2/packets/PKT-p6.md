# PKT-P6 — Trusted-directory/executable resolution

Tier: **opus**   Milestone: **M3**   Effort: **S**
Collision lane: **C**   Merge order: **4/4 in C**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**P6** — Trusted-directory/executable resolution.

## 2. User problem

Halbert resolves every security-sensitive helper binary by bare name through PATH, and PATH on a macOS host is attacker- and package-manager-malleable (dual Homebrew: /usr/local is Intel brew and wins PATH over /opt/homebrew — recorded project memory). The two worst exposures: `crypto/storage.py:227` gates the macOS Keychain keystore on `shutil.which("security")` and then runs bare `["security", "find-generic-password", ...]` at `crypto/storage.py:229-231` — a PATH-hijacked `security` sits in front of the custody key that protects Halbert's Tier-2 secret store; and `streaming/sandbox.py:98-100` probes `shutil.which("bwrap")` / `shutil.which("sandbox-exec")` by bare name, so the decision about whether a command runs sandboxed at all is itself PATH-dependent — a hijacked `sandbox-exec` turns the sandbox boundary into the attack surface. The same bare-name pattern runs through `crypto/storage.py:271` (`secret-tool`), `vision/ocr.py:69` (tesseract), `skills/readiness.py:150`, `system/display_power.py:154` (injectable `which`), `ingestion/service.py:35` (journalctl), `rag/trending_discovery.py:196`, `tools/schedule_cron.py:85,94` (bare `crontab` argv), and `utils/ollama.py:158` (bare `pkill -f 'ollama serve'`). Meanwhile the command classifier in the target file — `tools/safety.py:_command_segments` (lines 137-163) — strips any directory component and reduces every executable to its basename for rule matching, so classification and execution today share one weakness: neither side ever checks WHERE the binary that will actually run comes from. Backlog verdict (FINAL-CRITICAL-DISCOVERY-BACKLOG-2026-09-11.md, Permissions table): P6 ACCEPT — "Trusted-directory/executable resolution — real, no overlap." Deep-eval P5 RESHAPE split item (2) carries this build: "the helper-binary resolution + git env + ffmpeg bounds — ACCEPT (real security hardening, the `security` binary PATH hijack is high)." For a steward that speaks as the computer itself and stages commands on the owner's host, "I ran the real /usr/bin/security" is a measured-truth requirement, not a nicety.

## 3. What to build

Build one resolver and convert the security-critical call sites to it. 1) New module `halbert_core/halbert_core/utils/system_bin.py` exporting `resolve_system_bin(name: str, trust: str = "strict") -> Optional[str]` plus a module-level directory table as DATA: STRICT dirs are the OS-fixed set — macOS `/usr/bin`, `/bin`, `/usr/sbin`, `/sbin` (these are on the sealed system volume, root-only writable); STANDARD appends the Homebrew prefixes `/opt/homebrew/bin` and `/usr/local/bin` (recorded project memory: Intel brew owns /usr/local — check both, in that order). Resolution walks the fixed dir list in order, never consults `$PATH`, verifies the candidate with `os.path.isfile` + `os.access(X_OK)` + `not os.path.islink` pointing outside the trusted set (resolve symlinks with `os.path.realpath` and re-test containment — `/usr/bin/security` must not resolve into `/usr/local`), and returns the absolute path or None. No new hard dependency — stdlib only (Haloysius subtractive contract). 2) Convert strict-tier sites first: `crypto/storage.py` (`security` at :227/:229 and `secret-tool` at :271 — the `available()` probes AND the `_run` argv heads, so the probed binary is the executed binary), `streaming/sandbox.py:98-100` (`bwrap`, `sandbox-exec` — probe and `_wrap_bwrap`/`_wrap_seatbelt` argv heads must use the resolved absolute path). 3) Convert standard-tier sites: `tools/schedule_cron.py:85,94` (`crontab`), `vision/ocr.py:69` (tesseract), `utils/ollama.py:158` (`pkill`), `skills/readiness.py:150`, `ingestion/service.py:35`, `system/display_power.py:154`, `rag/trending_discovery.py:196`. 4) In the target file `tools/safety.py`, add the classification-side counterpart to `_command_segments` (lines 137-163): after the basename reduction at line 161, when a segment head names a binary in the strict table, record whether the spelled path (if any) resolves inside the trusted set — a command line that spells an executable path OUTSIDE the trusted dirs for a security-critical binary (e.g. `/tmp/security find-generic-password`) classifies one risk level higher, minimum HIGH, via a new SafetyRule wired into `_classify_command`. This keeps Lane C's file touched by P6 while the resolver itself lives in utils/. 5) Tests: `halbert_core/tests/test_system_bin.py` — every name in the table resolves to an absolute path inside the fixed dir list (the discovery's own acceptance: "no resolved path lies outside the fixed list"); a tmpdir fake `security` earlier in PATH is never returned; a symlinked candidate escaping the trusted set is refused; unknown names return None (fail closed). Run with `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_system_bin.py`.

## 4. What NOT to build

Do not build the rest of the deep-eval's original P6 mega-packet — the door hardening (`?token=` WS auth, CSP, body cap, auth limiter), the TCC/OS-grant preflights (`lsof`/`scutil`/`codesign` callers of this resolver), the policy doctor/lint CLI, SECURITY.md/threat model, pairing hardening, view-only terminal, shutdown budget, config watcher, machine-name-from-scutil. Do not build a general PATH-sanitization or environment-scrubbing layer (that is the env-policy module, another unit's scope). Do not convert the ~40 remaining bare-name subprocess sites (git invocations, `dashboard/routes/*`, scrapers, hardware_detector) — the security-critical set above is the S-effort slice; the rest is tail. Do not add a signing/notarization check on resolved binaries (codesign verification belongs to the TCC preflight unit that consumes this resolver). Do not touch `_SECRET_BASENAMES`, `_classify_write`, SENSITIVE_PATHS, or the P1 command-gate rebuild shapes (argv normalisation, network-egress classification) — P1 is a separate unit earlier in Lane C. Do not cache resolutions in a way that survives PATH/binary changes across turns without revalidation; a per-process memo is fine, an on-disk cache is not.

## 5. Target files
- `halbert_core/halbert_core/tools/safety.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S, as indexed. The mechanism is one stdlib-only module (~80-120 lines: a dir table, an ordered walk, isfile/X_OK/realpath-containment checks) plus mechanical call-site conversion at ~10 sites, most of which are one-line swaps of `shutil.which(name)` → `resolve_system_bin(name, trust=...)` and an argv-head substitution. The reference design exists in the OSS origin (`src/infra/resolve-system-bin.ts:5-28, 106-217` — strict = OS dirs only, standard appends Homebrew), so this is a port-and-wire, not a design. The safety.py side is one rule + one segment-head check inside the existing `_command_segments`/`_classify_command` structure. No schema changes, no async, no model involvement, no UI. It merges last in Lane C (TT-03 → TT-04a → P1 → P6) specifically because its safety.py hunk is small and rebase-tolerant against the P1 classifier rebuild.

## 8. UX rationale

No new surface — that is correct for this unit. The user-facing effect is on the trust axis of the one seamless conversation: when the steward says it unlocked the Keychain or ran a command sandboxed, those statements are grounded in measured fact (the resolved absolute path of the binary that ran), not in whatever PATH happened to contain. Failure must read in Halbert's first-person computer voice and stay honest about measurement: if `security` cannot be resolved from the trusted set, the Keychain store reports unavailable ("I cannot reach the macOS Keychain from a system path I trust") rather than silently running a PATH-resolved binary — fail closed, never fall back to `shutil.which`. No model is named, no emoji, no new colours (nothing rendered). The one visible seam is `streaming/sandbox.py`: when the sandbox binary is absent from trusted dirs, the existing is_available() False path already carries the UX — do not add a second signal.

## 9. Acceptance criteria

1) `utils/system_bin.py` exists, exports `resolve_system_bin(name, trust="strict")`, stdlib-only, and resolves every table entry to an absolute path inside the fixed directory list with symlink-containment re-verified after realpath. 2) `crypto/storage.py` and `streaming/sandbox.py` no longer contain `shutil.which` — probe and execution use the same resolved absolute path (a grep for `shutil.which` in those two files returns zero hits). 3) `tools/schedule_cron.py`, `vision/ocr.py`, `utils/ollama.py`, `skills/readiness.py`, `ingestion/service.py`, `system/display_power.py`, `rag/trending_discovery.py` route through the resolver at standard trust. 4) `tools/safety.py` classifies a command whose spelled executable path for a strict-table binary lies outside the trusted dirs at minimum HIGH. 5) Unresolvable names fail closed (None → store/sandbox reports unavailable; no PATH fallback anywhere in the converted sites). 6) The new test module passes and no converted site regresses its existing tests.

## 10. Verification (measured state, not model judgment)

Runnable, measured: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_system_bin.py halbert_core/tests/test_safety_chained_commands.py -x -q` — exit code 0. The new test module asserts measured filesystem state: (a) for each name in the strict table present on this host, the returned path starts with one of `/usr/bin/`, `/bin/`, `/usr/sbin/`, `/sbin/` (assert on the string prefix of the realpath); (b) with a tmpdir containing an executable fake `security` prepended to `os.environ["PATH"]`, `resolve_system_bin("security")` still returns `/usr/bin/security` (proves PATH is never consulted); (c) a symlink in a trusted dir whose realpath escapes the set returns None; (d) `resolve_system_bin("definitely-not-a-real-binary-halbert") is None`. Plus grep checks with exit-code semantics: `grep -c "shutil.which" halbert_core/halbert_core/crypto/storage.py halbert_core/halbert_core/halbert_core/streaming/sandbox.py` — wait, correct path: `grep -rn "shutil.which" halbert_core/halbert_core/crypto/storage.py halbert_core/halbert_core/streaming/sandbox.py` exits 1 (no matches). Regression: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_applescript_safety.py halbert_core/tests/test_skills_safety_binding.py -q` exit 0 (baseline compare against main — a failure is yours iff absent from the known-red baseline: test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py).

## 11. Exclusions

From the deep-eval P6 RESHAPE split, everything outside this unit goes elsewhere: (1) door hardening — WebSocket `?token=` removal, CSP middleware, audio body cap, auth-failure limiter — to its own M3/M4 packet (GW-A/auth lane units per DISPATCH-INDEX); (2) TCC/OS-grant axis (signing identity, preflights) — split, gated on DIST-02 founder signing decision in M5b; (3) policy doctor + lint CLI — DIAG-01/DIAG-02 units; (4) SECURITY.md + threat model — a docs unit (T-lane); (5) runtime hygiene (shutdown budget, config watcher coalesce, cancellation marker) — SCHED/DAEMON lanes; (6) machine-name-from-scutil — its own small unit, which will CONSUME this resolver for the absolute-path `scutil` call; (7) pairing hardening — DEFERRED per deep-eval (no consumer until ROADMAP LD-1's two-machine run); (8) view-only terminal observation — DEFERRED per deep-eval (no observer surface exists). Within this unit's own scope, excluded to tail: conversion of the remaining ~40 bare-name subprocess sites (`dashboard/routes/discovery.py`, `services.py`, `editor.py`, `model/hardware_detector.py`, git invocations in `routes/development.py:548,551`, ffmpeg bounding) — M5b tail or a follow-on sonnet sweep, since they are not custody-key or sandbox-boundary paths; the git-env hardening half of the deep-eval P5 split item (2) pairs with the env-policy unit, not this resolver. The `lsof`/`scutil`/`codesign` consumers named in the deep-eval are users of this module, not part of it.

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
