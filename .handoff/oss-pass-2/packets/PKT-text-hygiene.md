# PKT-text_hygiene — One untrusted-content sanitizer

Tier: **fable**   Milestone: **M0**   Effort: **S-M**
Collision lane: **L**   Merge order: **1/2 in L**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**text_hygiene** — One untrusted-content sanitizer.

## 2. User problem

Halbert has four independent, mutually unaware untrusted-text sanitizers, and the seams they miss are live prompt-injection surfaces. `mcp/metadata.py:66 sanitize_metadata_text` (R-09) caps at 1200 chars, strips Unicode tag chars U+E0000–U+E007F and C0/DEL, and defangs a closed set of override phrases — but only MCP metadata passes through it. `prompts/agent_prompts.py:309 _CONTROL_TAG_RE` (plus the `_defang_continuity` fixpoint at :333, scan-bounded by `_DEFANG_SCAN_MIN=4096`/`_DEFANG_SCAN_FACTOR=4`) collapses `<continuity|speech|text|modality_context>` — but matches ASCII angle brackets only, so a fullwidth `＜continuity＞` or a zero-width-interrupted `<system>` sails through (SP-2 spot-check, deep-eval group3 line 58). `agents/threads.py:148 _fence` substitutes `[`/`]` with fullwidth lookalikes and collapses `<continuity>` for its one receipt row. `discovery/schema.py:39 sanitize_discovery_text` strips controls and `<>` with a 64-char cap for discovery metadata. Meanwhile the tool-output block at `agent_prompts.py:1000-1006` is a bare `- {obs}` list with no defang pass at all, carrying web-search, MCP, peer-proxy, file, and command output straight into `messages[0]`. The FINAL-CRITICAL backlog §3.3 names the fix: one module, `security/text_hygiene.py`, consolidating the tag stripper + a non-ASCII fold table (NFKC fold of fullwidth/CJK brackets, zero-width joiners, BOM, soft hyphen) + a random-boundary wrapper for injecting external content into prompts — because building a third (or fifth) sanitizer per-packet is the wrong direction and the standing rules forbid duplicate primitives. Consumers already queued: TT-01 (ANSI/Unicode strip of subprocess output), TT-03 (command normalization step one), SP-2 (fold table + boundary wrapper), P4 (untrusted-data delimiters), VMV-3 (media/status surfaces), CH-A (turn provenance rows), LOG-01 (control-character sanitizer for log tail).

## 3. What to build

Create `halbert_core/halbert_core/security/text_hygiene.py` as the single untrusted-content sanitizer, exporting one public entry point plus composable halves so consumers pick the shape they need:

1. `sanitize_untrusted_text(value: Any, *, limit: int = DEFAULT_LIMIT) -> str` — the full pipeline, order fixed and documented: (a) coerce to str (None → ""); (b) NFKC normalization (`unicodedata.normalize("NFKC", text)`) which folds fullwidth ASCII (`＜` → `<`), fullwidth digits/letters, and compatibility lookalikes into their canonical forms BEFORE any tag regex runs — this is the gap `_CONTROL_TAG_RE` cannot see; (c) strip Unicode tag chars U+E0000–U+E007F and C0/DEL controls minus tab/newline/CR (reuse the exact `_TAG_CHARS`/`_CONTROLS` patterns from `mcp/metadata.py:45-48`, moved here); (d) strip zero-width joiners/non-joiners (U+200B–U+200D), BOM (U+FEFF), and soft hyphen (U+00AD) — the fold-table tail NFKC does not remove; (e) collapse the prompt-layer control tags (`continuity|speech|text|modality_context`, now matching post-fold ASCII reliably) using the existing `_CONTROL_TAG_RE` pattern, with the fixpoint substitution loop and scan bound (`max(SCAN_MIN, limit * SCAN_FACTOR)`, same constants and same termination argument as `threads.py:161-166` — every pass replaces ≥12 chars with one, string strictly shrinks); (f) defang the override-phrase set (the closed `_OVERRIDE_PHRASES` regex from `mcp/metadata.py:53-63`, moved here, `[defanged]` replacement kept visible); (g) cap at `limit`, cutting on a boundary and appending the visible `[truncated at N characters]` marker — an elision the model can see beats one it cannot.

2. `strip_ansi(text: str) -> str` — ANSI/VT escape-sequence stripper (CSI/OSC/DCS/ESC sequences) for subprocess output, the TT-01 consumer. Pure function, no other pipeline stage, so a caller that needs raw-text-without-ANSI is not forced through defanging.

3. `wrap_boundary(text: str, *, label: str = "untrusted") -> str` — the random-boundary wrapper from the SP-2 design: wrap sanitized text in a per-call random-ID delimiter pair (e.g. `<untrusted-{hex8}>...</untrusted-{hex8}>`) so the closing tag in the payload cannot be predicted and forged, and emit the one-line "data, not instructions" frame naming the random id. Uses `secrets.token_hex(4)`; never a model, never configurable.

4. `DEFAULT_LIMIT` and the scan-bound constants re-exported so callers stop hand-copying ceilings (the `agent_prompts.py:283 _SYSTEM_LINE_CHARS` comment block explicitly warns about hand-copied ceilings drifting).

Then rewire the two existing owners to delegate, deleting their private implementations: `mcp/metadata.py:66 sanitize_metadata_text` becomes a thin wrapper calling `sanitize_untrusted_text(value, limit=MAX_METADATA_CHARS)` (keeps its public name — R-09 call sites and tests unchanged); `prompts/agent_prompts.py` `_CONTROL_TAG_RE`/`_defang_continuity` and `threads.py:_fence` import the tag-collapse and scan-bound constants from `security/text_hygiene.py` instead of holding private copies (keep `_fence`'s fullwidth-bracket substitution local to threads.py — that is row-format policy, not sanitization). `discovery/schema.py:39 sanitize_discovery_text` stays as-is: its 64-char single-line shape is a different contract; record it as a known non-consumer in the module docstring. Add `halbert_core/tests/test_text_hygiene.py` covering: fullwidth `＜continuity＞` folded and collapsed; zero-width-interrupted `<s\nystem>` (ZWJ between letters) neutralized after fold; nested `"</</continuity>continuity>"` fixpoint terminates with no tag residue; 130KB pathological row completes in well under the old 7s (assert wall-clock < 2s); ANSI CSI color sequence stripped; two `wrap_boundary` calls produce different boundary ids; override phrase replaced with visible `[defanged]`; truncation marker present and total length ≤ limit + marker. No new dependencies — stdlib `re`, `unicodedata`, `secrets` only (Haloysius two-hard-dependency contract). No model anywhere; every step deterministic.

## 4. What NOT to build

Do NOT rewire any consumer in this unit — TT-01's executor ANSI strip, TT-03's command normalization, SP-2's `prompts/untrusted.py` application to the `agent_prompts.py:1000-1006` tool-output block and its guest tool-list threading, P4's delimiter adoption, VMV-3's media surfaces, CH-A's provenance rows, and LOG-01's log-tail sanitizer each adopt the module in their own packets; this unit ships the primitive plus the three delegation rewires (mcp/metadata, agent_prompts, threads) only. Do NOT build the source-hygiene block — §3.3 lists it as an SP-6 component and SP-6 is DEFERRED (gate: missing write path and consumers); it goes to SP-6 when that packet opens. Do NOT touch the redaction registry (`ingestion/redaction_registry.py`, `security/result_redaction.py`) — redaction of secrets is R-05's choke point, a different mechanism from injection-shape hygiene; this module must not call it and must not be called by it. Do NOT add a content filter, denylist of topics, or any model call — the closed override-phrase set is deliberately short per the metadata.py docstring ("a long list is a filter, and a filter invites evasion work"). Do NOT change `discovery/schema.py:39` — different contract (single-line, 64 chars, strips all brackets rather than defanging). Do NOT build a config knob, severity levels, or per-caller overrides — one pipeline, one order, applied the same way every time. Do NOT add a third hard dependency or any non-stdlib import.

## 5. Target files
- `halbert_core/halbert_core/security/text_hygiene.py` [new file]
- `halbert_core/halbert_core/mcp/metadata.py`
- `halbert_core/halbert_core/prompts/agent_prompts.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S-M** — S-M (one focused session, ~250-350 lines of module plus ~150 lines of tests plus three small delegation rewires). The hard parts are already solved and sitting in the tree: the cap/defang/truncate semantics and their docstring rationale live in `mcp/metadata.py` (77 lines), the fixpoint-collapse and scan-bound cost argument live in `agent_prompts.py:309-360` and `threads.py:148-171`, and the fold-table requirement is precisely enumerated in the SP-2 deep-eval (fullwidth/CJK brackets, zero-width joiners, BOM, soft hyphen). What remains is consolidation, the NFKC fold insertion at the correct pipeline position, the ANSI stripper (~15 lines of regex), the random-boundary wrapper (~25 lines), and the test battery including the pathological-input timing pin. It is not S alone because the pipeline-order decision (fold BEFORE tag-collapse, strip zero-width BEFORE defang, cap LAST) must be argued once and pinned by tests, and the three delegation rewires touch two hot files (`agent_prompts.py`, `threads.py`) that concurrent sessions edit — keep each rewire a mechanical import swap with zero behaviour change so rebases stay trivial. It is not L because no consumer wiring, no state_machine/executor/routes files, and no founder decisions are in scope.

## 8. UX rationale

No user-facing surface changes — this is a security primitive below every surface. Its effects are felt indirectly: the machine's replies stop being steerable by fullwidth-tag or zero-width-tag payloads embedded in command output, MCP descriptions, or pasted text, and quoted text that was cut says so (`[truncated at N characters]`) instead of silently ending mid-token — consistent with the "grounded in measured data" posture: the machine shows its seams. The `[defanged]` marker stays visible on purpose so a person reading a transcript can see that a server or file tried to address the model as its operator and was neutered. No colours, no emoji, no copy, no settings, no onboarding impact. The boundary wrapper's random id appears only inside prompt assembly and never renders on a dashboard surface; if a debugging surface ever shows it, it shows as an opaque token, never a model or provider name.

## 9. Acceptance criteria

1. `halbert_core/halbert_core/security/text_hygiene.py` exists and exports `sanitize_untrusted_text`, `strip_ansi`, `wrap_boundary`, `DEFAULT_LIMIT`. 2. `mcp/metadata.py::sanitize_metadata_text` delegates to it and its existing tests still pass unchanged (no behaviour drift on the R-09 surface). 3. `agent_prompts.py` and `threads.py` import the tag pattern and scan-bound constants from the new module; the private `_TAG_CHARS`/`_CONTROLS`/`_OVERRIDE_PHRASES` regex bodies exist in exactly one place in the tree (grep confirms). 4. New tests prove the previously-missed shapes are caught: fullwidth `＜continuity＞` collapses, zero-width-interrupted tags collapse, nested fixpoint payload leaves no residue, ANSI escapes strip, boundary ids differ per call, override phrases render as `[defanged]`, truncated output carries the visible marker. 5. The 130KB nested-payload timing test passes under its bound. 6. No new third-party dependency appears in any pyproject/requirements file.

## 10. Verification (measured state, not model judgment)

Runnable, measured checks — run from the repo root with the mandated prefix: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_text_hygiene.py halbert_core/tests -k "metadata or defang or fence or continuity" -x -q` must exit 0 (new module tests plus every existing test touching the three rewired call sites). Structural one-liners, each must exit 0: `grep -rn "E0000" halbert_core/halbert_core/ --include="*.py" -l` prints only `security/text_hygiene.py` and test files (single owner of the tag range); `grep -rn "ignore\\\\s+(all" halbert_core/halbert_core/ --include="*.py" -l` prints only `security/text_hygiene.py` (single owner of the override-phrase regex); `grep -n "import unicodedata\\|from security.text_hygiene" halbert_core/halbert_core/mcp/metadata.py halbert_core/halbert_core/prompts/agent_prompts.py halbert_core/halbert_core/agents/threads.py` shows the three delegation imports. Timing pin (measured, not judged): `arch -arm64 .venv/bin/python -c "import time; from halbert_core.security.text_hygiene import sanitize_untrusted_text; payload='</continuity>'*20000; t=time.monotonic(); sanitize_untrusted_text(payload); assert time.monotonic()-t < 2.0, 'fixpoint regression'"` exits 0. Dependency contract: `grep -c "^dependencies" -A5 halbert_core/pyproject.toml | grep -c "pyyaml\\|requests"` confirms no third hard dependency was added (the count of hard deps stays 2).

## 11. Exclusions

Four real exclusions, each with a named destination. (1) Consumer adoption — TT-01's ANSI strip in `tools/executor.py`/`streaming/pty.py`, TT-03's command-normalization first pass, SP-2's application of `wrap_boundary` to the `agent_prompts.py:1000-1006` tool-output block plus its guest tool-list threading and shell-steer text, P4's untrusted-data delimiter adoption, VMV-3's media-surface scrubbing, CH-A's provenance-row fencing, LOG-01's log-tail control-character pass: each goes to its own packet (TT-01, TT-03, SP-2, P4, VMV-3, CH-A, LOG-01 per the registry notes); this unit ships the primitive so those packets import instead of reinventing. (2) The source-hygiene block listed in the §3.3 candidate spec — goes to SP-6, which the FINAL-CRITICAL backlog verdicts DEFER (gate: missing skill write path and consumers); build nothing for it now. (3) The prompt-size diagnostic (HM15-C12) and synthetic-cancellation naming (OCC02-C10) from the SP-2 design — both stay in SP-2; C10 additionally waits on A07-G4's delimiter pair per the group3 deep-eval sequencing note. (4) Any expansion of the override-phrase list, per-caller policy knobs, locale-specific fold exceptions, and streaming/chunked sanitization — dropped per the RESHAPE discipline: the closed phrase set is deliberate (metadata.py docstring: a long list invites evasion), there is one pipeline with no knobs, and no streaming consumer exists today; if TT-01's spill path later needs a streaming variant, it is designed there against this module's primitives, not speculated into M0.

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
