# PKT-SP-1 — Typed readiness evaluator + authoring sweep + builtin annotations (post R-11)

Tier: **opus**   Milestone: **M5a**   Effort: **S-M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Verification-first** — verify R-11 is merged, keep only the genuine residual.

---

## 1. Packet

**SP-1** — Typed readiness evaluator + authoring sweep + builtin annotations (post R-11).

## 2. User problem

R-11 built the typed `Readiness` enum and `evaluate_readiness()` in `halbert_core/halbert_core/skills/readiness.py`, and `matcher.py` consumes it for activation (matcher.py:175,183,229,237). But the model-facing catalog builder `_entries()` in `halbert_core/halbert_core/skills/catalog.py:159-193` never calls `evaluate_readiness` — it lists every trusted, model_invocable, source_path-bearing skill in priority_rank order regardless of whether the host can actually run it. A builtin whose SKILL.md declares `bins: [zpool]` on a Mac without ZFS still appears in the `<available_skills>` block, gets selected by the router, and tells the model to invoke a binary that does not exist. The `requires` schema R-11 parses has no consumer effect on the surface the model reads. Compounding this, none of the nine builtin SKILL.md files (`config-ops`, `discovery-ops`, `frigate-ops`, `home-ops`, `network-ops`, `security-ops`, `service-ops`, `storage-ops`, `understated`) carries a `requires:` declaration at all, so even the catalog filter has nothing real to evaluate. And `telemetry.py:219` writes `detail={"name": skill.name, "path": str(path)}` with the absolute source path into `skill_events`, leaking `/Users/<operator>/...` into telemetry rows. The typed evaluator exists, the input annotations are missing, the catalog consumer is missing, the regression sweep is missing, and telemetry leaks absolute paths.

## 3. What to build

Three concrete changes in `halbert_core/halbert_core/skills/`, plus content edits and one sweep test.

(1) Catalog consumes readiness. In `catalog.py:_entries()` (currently at lines 159-193), call `evaluate_readiness(skill, platform=current_platform())` after the existing `kind/state/model_invocable/source_path` gates. Only `Readiness.READY` skills are appended to `out`. `MISSING`, `UNSUPPORTED`, and `DISABLED` skills are excluded from the model-facing block. Keep the existing sort key `(-priority_rank, name)`. Do not expose setup_needed on the operator surface in this packet — that is a Settings/operator-surface change and out of scope here.

(2) Annotate the nine builtin SKILL.md files with `requires:` declarations. Content work, founder-approved per the verdict. Edit each file under `halbert_core/halbert_core/skills/builtin/<name>/SKILL.md` to declare what it actually needs: `storage-ops` gets `requires: {any_bins: [zpool, diskutil, lsblk], os: [darwin, linux]}`; `frigate-ops` gets `requires: {config: [frigate]}` (or whatever `has_capability` key names the Frigate integration); `network-ops` gets `requires: {any_bins: [ip, ifconfig, networksetup]}`; `service-ops` gets `requires: {any_bins: [systemctl, launchctl]}`; `discovery-ops`, `home-ops`, `security-ops`, `config-ops` get whatever their bodies actually invoke (read each body, list the binaries it tells the model to run, declare those). `understated` is a lens and already excluded by `kind == "lens"` — no annotation needed. Keep annotations minimal and honest: declare only what the body references.

(3) Authoring-standards pytest sweep. New test module `halbert_core/tests/test_skills_authoring_standards.py` that parametrizes over every builtin SKILL.md (discovered via `Path(__file__).parent / "../halbert_core/skills/builtin"`), parses each via the existing `parser.py`, and asserts: (a) `description` ≤ the parser's declared bound (R-11 already enforces this at parse; the sweep pins it against regression); (b) presence of `## When to Use`, `## Quick Reference`, and `## Verification` sections in the body — enforced via a `GRANDFATHER` dict mapping skill name → set of missing sections, and the dict may only shrink, never grow (assert `set(current_missing) <= GRANDFATHER.get(name, set())` and fail if a new skill starts with a missing section); (c) every `requires.bins` and `requires.any_bins` entry is a plausible binary name (no path separators, no shell metacharacters).

(4) Telemetry path stripping. In `telemetry.py:219`, replace `"path": str(path)` with `"path": skill.source_path.name if skill.source_path else ""` — record only the basename (the SKILL.md filename or the relative skill directory), never the operator's home directory. One-line change; rides along with the packet.

## 4. What NOT to build

Apple skills (HM20-C1 per-app AppleScript disambiguation) — deferred. No `CAP_APPLESCRIPT` consumer exists in the readiness evaluator yet; build when Apple skills are actually authored. AST-based diagnostic audit (HM10-C5) — deferred; advisory only, no gate. TOCTOU-safe bundle fetch (HM10-C1) — deferred; no installer exists, so there is nothing to harden. Provider-credential blocklist rule (HM06-C19) — deferred; `execute_code` already bans subprocess, record as a design constraint only in packet notes, not as code. Custodian skills (OC24-C6) — handed to SK-3 per the section file. Operator-surface rendering of setup_needed skills — not built; this packet only filters the model-facing catalog. Do NOT touch `matcher.py` — it already consumes readiness correctly for activation. Do NOT touch `readiness.py` — the evaluator itself is R-11's and is correct. Do NOT touch `parser.py` — the `requires` schema already parses. Do NOT add a second implementation of the readiness check inside `catalog.py` — call `evaluate_readiness`, do not reimplement the gates.

## 5. Target files
- `halbert_core/halbert_core/skills/`

## 6. Dependencies

Verify R-11

## 7. Effort

**S-M** — S-M. (1) is a five-line change in `_entries()` plus an import — S. (2) is content editing across nine files; each requires reading the skill body and listing the binaries it invokes; no logic, but it cannot be done blind — M for thoroughness, S if the bodies are short. (3) is a new ~120-line pytest module with a parametrized fixture and three assertions — S. (4) is a one-line change — trivial. The bulk of the work is (2), the content sweep, and (3)'s initial `GRANDFATHER` dict population (which requires running the sweep once against the current nine files and recording what is missing). No new module is created; only `catalog.py`, `telemetry.py`, nine SKILL.md files, and one new test file. No hub files are touched. `catalog.py` is not a hub (the SourcePrep atlas does not list it). Effort is bounded, sequenced, and reversible.

## 8. UX rationale

Invisible to the operator in normal use. The model-facing `<available_skills>` block silently shrinks to only the skills that can actually run on this host. A Mac without `zpool` stops seeing `storage-ops` ZFS runbooks in the catalog; a Linux box without `diskutil` stops seeing APFS guidance. The router can no longer select a specialist that can do nothing. No new settings, no new UI surface, no new persona vocabulary. The telemetry rows in `skill_events` stop carrying `/Users/<operator>/...` paths — visible only to someone querying the table. The catalog does not announce the filter; it simply does not list what is not usable, consistent with "commands staged never executed" and "never as an assistant."

## 9. Acceptance criteria

(1) `catalog.py:_entries()` calls `evaluate_readiness` and filters to `Readiness.READY`; a unit test in `test_skills_catalog.py` constructs a fake skill with `requires.bins = ["definitely_not_a_real_binary_xyz"]` and asserts it does not appear in the rendered catalog. (2) All nine builtin SKILL.md files carry a syntactically valid `requires:` block parseable by `parser.py`; `understated` is exempt (it is a lens). (3) `test_skills_authoring_standards.py` exists, parametrizes over all builtins, asserts description bounds and section presence with a shrink-only `GRANDFATHER` dict; running it on a clean checkout passes; manually adding a fake builtin with an over-limit description fails the sweep. (4) `telemetry.py` no longer writes absolute paths to `skill_events.detail["path"]`; a test asserts the field equals `Path(skill.source_path).name` or `""`, never a string containing `str(Path.home())`.

## 10. Verification (measured state, not model judgment)

From the repository root, on a worktree:

```
arch -arm64 ./wt_pytest.py halbert_core/tests/test_skills_catalog.py halbert_core/tests/test_skills_readiness.py halbert_core/tests/test_skills_authoring_standards.py
```

This runs the existing catalog and readiness tests (R-11's, must stay green) plus the new authoring-standards sweep. The sweep test ID `test_skills_authoring_standards.py::test_builtin_descriptions_bounded` and `test_skills_authoring_standards.py::test_builtin_required_sections` are the measured state checks. To verify the catalog filter end-to-end, run:

```
arch -arm64 ./wt_pytest.py halbert_core/tests/test_skills_catalog.py -k "readiness or ready"
```

The new test injected there constructs a skill with `requires.bins = ["definitely_not_a_real_binary_xyz"]` and asserts it does not appear in the rendered `<available_skills>` block — a measured check, not a model judgment. For the telemetry strip, `test_skills_readiness.py` (or a new `test_skills_telemetry.py` if the packet author splits it) asserts the `path` detail field never contains `str(Path.home())`. All tests run against the shared venv with `arch -arm64` per the repo's standing rule; `wt_pytest.py` strips the editable-install MetaPathFinder so the worktree's own code is what is tested.

## 11. Exclusions

Deferred items and their destinations:

- Apple skills per-app disambiguation (HM20-C1) — deferred to a future packet when `CAP_APPLESCRIPT` exists in `capabilities.py` and Apple skills are actually authored. No file is touched.
- AST-based diagnostic audit (HM10-C5) — deferred; advisory only, no gate. Would live in a future `skills/audit.py` if ever built.
- TOCTOU-safe bundle fetch (HM10-C1) — deferred; no installer exists. Constraint recorded in `.handoff/oss-pass-2/deep-eval-group3-skills-mcp-models.md` (already there, section SP-1 line 44).
- Provider-credential blocklist rule (HM06-C19) — deferred; `execute_code` already bans subprocess. Constraint recorded in the same deep-eval file. No code change.
- Custodian skills (OC24-C6) — handed to SK-3 per the section file; not this packet's scope.
- Operator-surface (Settings pane) rendering of setup_needed / disabled skills — not built here; that is a `halbert_core/halbert_core/dashboard/` frontend change and belongs to a different packet.
- `matcher.py`, `readiness.py`, `parser.py`, `registry.py`, `loader.py`, `composer.py`, `sidecar.py`, `suppression.py`, `reserved.py`, `reload.py`, `scanner.py` — all untouched. Only `catalog.py`, `telemetry.py`, nine `builtin/*/SKILL.md` files, and one new test file `halbert_core/tests/test_skills_authoring_standards.py` are modified or created.

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
