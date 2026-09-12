# PKT-MCP-B — content/structuredContent alternation + bridge base64 predecode (post R-09)

Tier: **opus**   Milestone: **M5a**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

> **Verification-first** — verify R-09 is merged, keep only the genuine residual.

---

## 1. Packet

**MCP-B** — content/structuredContent alternation + bridge base64 predecode (post R-09).

## 2. User problem

R-09 is merged (commits 865e016c, 7edf3908, ab0750a1, afc2f1b9, d569883d, 58216f33 on main, plus the opus-batch merge 55ecef87), and with it the MCP-B deep-eval's core: `mcp/metadata.py:sanitize_metadata_text` defangs override phrases, strips U+E0000-E007F tag chars and C0 controls, caps at 1200 chars; `mcp/bridge.py:format_tool_result` fences every result with `[mcp_result server=...]` provenance and projects non-text blocks as size facts; annotations and the sampling/elicitation refusal are done. Two residuals remain, both in one function. (a) HM09-C9: a spec-following MCP server renders its payload into BOTH `content` and `structuredContent`; `format_tool_result` (bridge.py:243-271) never looks at `structuredContent` — grep for the symbol across halbert_core returns zero hits — so when a server sends structuredContent alongside thin content, the model either sees the thin copy or, worse, once we forward both, pays double tokens. Protocol-reserved `_meta`-prefixed keys likewise have no strip rule. (b) HM09-M3 residual: the success path into the next PLANNING pass is already trimmed at `agents/state_machine.py:53` (`_TOOL_RESULT_CHARS = 2000`, applied at :186-187), so context flood is handled — but the bridge itself buffers whole base64 blobs in-process (client.py tool_call.result) and never pre-checks decoded size before projection; an image/audio block becomes only a `[image: mime, N encoded bytes]` fact (bridge.py:223-227) with no spill-to-file path, so binary resources a server returns are silently unusable even where a file on disk would serve. The residual packet is exactly these two, in `format_tool_result` and its helpers.

## 3. What to build

Two narrow changes, both in `halbert_core/halbert_core/mcp/bridge.py`, plus tests. (1) Content/structuredContent alternation in `format_tool_result` (bridge.py:243): when the result is a dict, project `result["content"]` via the existing `_project_content`; only if that projection renders EMPTY (empty string) and `result.get("structuredContent")` is present, render the structuredContent value via the existing `_json_dump` + `sanitize_metadata_text` path at MAX_RESULT_CHARS — never forward both. Strip protocol-reserved keys: before the empty-fallback JSON dump, drop any top-level keys starting with `_meta` (and a `_meta` key itself) so plumbing never reaches the model payload. Add a visible marker when the structuredContent fallback was taken, e.g. prefix `[structured content]`, so the model can tell which arm served. (2) Base64 pre-decode check + binary spill in `_project_content` (bridge.py:203-240): for `image`/`audio` blocks, compute `decoded_size = len(data) * 3 // 4` BEFORE any decode attempt and compare against a new module constant (suggest `MAX_BINARY_SPILL_BYTES = 50 * 1024 * 1024`, mirroring the origin's 50 MB resource cap); if under the cap, decode and write to a spill file under the host cache dir (use the existing platform cache location used by camera_gate — do NOT invent a second location), replacing the block with `[image: mime, N bytes, saved to <path>]`; if over the cap, keep the current size-fact behaviour and append `, not saved (over spill cap)`. The spill write must route through the same gate path camera_gate uses for captured media (redaction/scrub seam), not around it. Keep `MAX_RESULT_CHARS = 8000` unchanged — it must stay above the 2000-char observation trim at state_machine.py:53 so the budget layer, not the bridge, decides what the model loses. No model anywhere in the decision; everything is deterministic size arithmetic and a closed key-prefix rule.

## 4. What NOT to build

Do NOT rebuild anything R-09 already merged — that is most of the original MCP-B packet. Specifically excluded: description scan/tag-stripping/override-phrase defanging (done — `mcp/metadata.py:sanitize_metadata_text`, tested by `tests/test_mcp_metadata_hygiene.py`); the 1200-char metadata cap (MAX_METADATA_CHARS, done); result fencing and `provenance='mcp'` (done — `_fence`, MCP_RESULT_OPEN/CLOSE, test_a_result_is_fenced_and_names_its_server); non-text block projection to size facts (done — `_project_content`, test_an_image_block_becomes_a_size_fact_not_a_base64_wall); annotation handling (destructiveHint→HIGH, done, R-09 Phase C); sampling/elicitation refusal pin (done, M13); the stdio 64 KiB frame fix (done — `MAX_STDIO_FRAME_BYTES` at client.py:441); MCPToolError text capping for the failed path (done — client.py:288-290 sanitize+redact). Also excluded: the media-cache/rendering half of the origin design (C8) — the dashboard has no image rendering surface today, so a cache-and-reference-tag port is explicitly deferred by the section file; the spill-to-file in this packet is the bounded stand-in, not the full media cache. The death supervisor, whitespace warning, and dead-child race belong to MCP-A's residual packet, not this one. The schema cache and idle recycling belong to MCP-C. No changes to `agents/state_machine.py` (the 2000-char trim stays as-is), no changes to `tools/executor.py` (provenance field already landed), no new dependencies, no model calls, no emoji, no AI-model names on any surface.

## 5. Target files
- `halbert_core/halbert_core/mcp/`

## 6. Dependencies

Verify R-09

## 7. Effort

**S** — S, honestly. Both residuals live in one function cluster (`format_tool_result` + `_project_content`, ~70 lines) in one file. Item (1) is a fallback branch plus a key-prefix filter — perhaps 30 lines with the marker and the `_meta` strip. Item (2) is integer arithmetic on a base64 length, a bounded `base64.b64decode`, a file write under an existing cache directory, and a string-format change to the projected fact — perhaps 50 lines including the over-cap path. Tests are the larger half: the existing `tests/test_mcp_bridge.py` and `tests/test_mcp_metadata_hygiene.py` give the harness pattern, and the new cases are deterministic (a dict carrying both fields; a fake image block of known size; an over-cap blob). No async machinery beyond what the current handler tests already use, no new fixtures, no cross-module seams except reusing the camera-gate cache location. Effort stays S only if the spill write genuinely reuses the existing cache-dir helper; if the executor finds camera_gate's path helper is not importable from mcp/, the fallback is the platform cache util in `utils/platform.py`, still S.

## 8. UX rationale

Nothing user-facing changes visually; this is hygiene inside the machine's own hearing. What the owner notices is absence-of-weirdness: a spec-following MCP server (the kind that fills both `content` and `structuredContent`) no longer costs double tokens or feeds the model two disagreeing copies of the same fact, so answers grounded in MCP data stay consistent and the seamless conversation does not mysteriously truncate early from context pressure. When a server returns an image or audio blob, the model can now say, in the computer's first person and grounded in the measured fact, "the server returned a 2.1 MB PNG, saved here" with a real path — instead of the blob vanishing into a size-only footnote. The `[structured content]` marker and the `, not saved (over spill cap)` suffix keep the machine honest about which arm served and what was dropped: nothing silently discarded, what is dropped is said — the same posture as the existing projection. No settings, no toggles, no new surfaces, no model names anywhere; the machine speaks of "the server," never of a provider.

## 9. Acceptance criteria

1) A `tools/call` result dict carrying BOTH `content` (non-empty) and `structuredContent` yields output built from `content` only; the string `structuredContent` and the structured payload's unique sentinel value do not appear in the formatted result. 2) A result dict whose `content` projects to empty (e.g. `content: []` or absent) with `structuredContent` present yields output containing the structured payload's sentinel value and the `[structured content]` marker. 3) A result dict containing top-level `_meta` keys (or `_meta`-prefixed keys) yields output with those keys absent — grep the formatted string for the sentinel key name, zero hits. 4) An `image` block whose base64 decodes under `MAX_BINARY_SPILL_BYTES` produces a file on disk under the cache dir, whose byte length equals the pre-computed `len(data)*3//4` (adjusted for padding), and the formatted output names the path. 5) An `image` block over the cap writes NO file (cache dir file count unchanged) and the output carries the size fact plus `not saved`. 6) All pre-existing MCP tests still pass unchanged — in particular test_mcp_metadata_hygiene.py's fencing, provenance, image-fact, and embedded-resource tests, proving the R-09 invariants were not regressed. 7) `MAX_RESULT_CHARS` remains 8000 and `_TOOL_RESULT_CHARS` remains 2000 (bridge cap stays above the observation trim).

## 10. Verification (measured state, not model judgment)

Run the measured checks with the repo's required invocation: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_mcp_bridge.py halbert_core/tests/test_mcp_metadata_hygiene.py -x -q` from /Volumes/4TB-BAD/Halbert (main checkout; from a worktree use `arch -arm64 ./wt_pytest.py` instead). New tests to add and pass by ID: `test_structured_content_is_ignored_when_content_renders` (acceptance 1), `test_structured_content_is_the_fallback_when_content_is_empty` (acceptance 2), `test_reserved_meta_keys_never_reach_the_model` (acceptance 3), `test_an_image_block_under_the_spill_cap_is_saved_to_a_file` (acceptance 4), `test_an_image_block_over_the_spill_cap_is_a_fact_not_a_file` (acceptance 5). Acceptance 6 is the two pre-existing files passing green. Acceptance 7 is a grep assertion: `grep -n "MAX_RESULT_CHARS = 8000" halbert_core/halbert_core/mcp/bridge.py && grep -n "_TOOL_RESULT_CHARS = 2000" halbert_core/halbert_core/agents/state_machine.py`. Every check reads measured state — file contents, formatted strings, bytes on disk, pytest exit codes — never a model judgment. Note main carries a known nonzero failure baseline; run the two named files only, and if a failure appears that also fails on the merge-base without this change, it is baseline, not regression.

## 11. Exclusions

Death supervisor / pipe-EOF reaper, hidden-whitespace warning on config values, fail-fast dead-child race → MCP-A residual packet ("MCP child-process liveness completion"), same deep-eval doc. Schema cache with lazy first-call connect, idle/max-lifetime recycling of stdio children → MCP-C residual packet ("MCP server lifecycle optimization"), same doc. OSV package preflight at fetch time → already deferred by founder decision FD-10 (default: not now; record); `mcp/package_preflight.py` holds what was ratified. Media cache with reference tags and dashboard image rendering → deferred wholesale until a rendering surface exists (section file's C8 gate); the spill-file here is the bounded interim, not that port. The 55 bare `{'error': str(e)}` returns in `mcp/server.py` typed-error envelope → GW-A packet (accepted), not this one; this packet touches only the client-side bridge result path. The shared-sanitizer opportunity (SP-2's `prompts/untrusted.py` importing `strip_unicode_tags`/the fold table from `mcp/metadata.py`) → SP-2 packet in the skills workstream; this packet leaves `mcp/metadata.py` untouched so SP-2 has a stable import target. The terminal-tools orphan-process escalation ladder (HM04-M3) → terminal workstream, reusing R-09's process-group pattern, none of this packet's files.

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
