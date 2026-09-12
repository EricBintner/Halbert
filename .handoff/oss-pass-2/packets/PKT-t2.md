# PKT-T2 — Fix Darwin memory information defect

Tier: **sonnet**   Milestone: **M4**   Effort: **S**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**T2** — Fix Darwin memory information defect.

## 2. User problem

On macOS — the host Halbert actually runs on — the agent-facing `get_memory_info` tool cannot report memory at all. `halbert_core/halbert_core/tools/system_info.py:75-107` opens `/proc/meminfo` unconditionally; that path does not exist on Darwin, the `FileNotFoundError` is swallowed by the broad `except Exception` at line 106-107, and the string "Error getting memory info: [Errno 2] No such file or directory: '/proc/meminfo'" is returned straight to the model as the tool result. So when the machine is asked about its own memory, it quotes an error string instead of measured data — a direct violation of the standing "first person as the computer itself, grounded in measured data" directive, on the primary deployment platform. The correct Darwin logic already exists elsewhere in the tree: `halbert_core/halbert_core/discovery/scanners/system_profile.py:443-460` (`SystemProfiler._scan_hardware_macos`) runs `vm_stat`, parses the page size, and computes available ≈ free + inactive + speculative pages ("matches Activity Monitor"), with total from `sysctl -n hw.memsize` at lines 434-441. Two facts the dispatcher must honor: (1) the reference origin (OpenClaw `extensions/llama-cpp/src/hardware.ts:60-83`, finding OC22-C7) computes available as free + inactive only, while `system_profile.py` uses free + inactive + speculative — the implementations disagree, and the packet must pick one and say which (keep free + inactive + speculative: it is the already-shipped Halbert semantic, matches Activity Monitor, and changing the scanner's meaning is out of scope); (2) this defect was originally filed as one line of deep-eval packet T2 ("Suite integrity and the async ratchet"), but the dispatch-index RESHAPE narrowed unit T2 to exactly this one-file Darwin fix — the async ratchet, isolated runner, and AST guard are NOT part of this unit.

## 3. What to build

One focused change in `halbert_core/halbert_core/utils/platform.py` plus the tool wiring in `halbert_core/halbert_core/tools/system_info.py`, pinned by tests. Concretely:

1. Add a shared Darwin memory helper in `halbert_core/halbert_core/utils/platform.py` (the registry target file and the natural home — it already hosts platform predicates). New pure function `get_darwin_memory_info() -> dict` (name it exactly that; `platform.py` is a utils module, keep it sync and subprocess-based): run `sysctl -n hw.memsize` for total bytes and `vm_stat` for page accounting; parse page size via the same regex already proven in `system_profile.py` (`page size of (\d+)`, default 16384), extract `Pages free`, `Pages inactive`, `Pages speculative`, and compute `available_bytes = (free + inactive + speculative) * page_size`. Return a dict `{total_bytes, available_bytes}` (plus `free_bytes`/`inactive_bytes`/`speculative_bytes` if convenient for the renderer). Raise (or return None) on parse failure — do NOT fabricate zeros.

2. Refactor `SystemProfiler._scan_hardware_macos` in `halbert_core/halbert_core/discovery/scanners/system_profile.py:434-460` to call the new shared helper instead of its inline `vm_stat`/`sysctl` block, preserving its existing output shape (`result["memory"]["total_gb"]`, `result["memory"]["available_gb"]`, rounded to 1 decimal). This is the "factor the vm_stat parse out of system_profile.py into a shared helper" step from the section file — one implementation, two callers.

3. Branch `get_memory_info` in `halbert_core/halbert_core/tools/system_info.py:75-107` on `platform.system() == "Darwin"` (import `platform` stdlib, or reuse the module's existing style): on Darwin call the shared helper and render the SAME output shape the tool already produces (`Memory Usage:\n  Total: ... Used: ... Available: ...`) so downstream consumers see no format change; on Linux keep the existing `/proc/meminfo` path byte-for-byte. `used = total - available`, `percent` guarded on total > 0, GB formatting via the existing `format_size` closure pattern. The Darwin branch must never touch `/proc/meminfo`. Keep the broad `except` as the last-resort guard, but the Darwin path must be genuinely functional, not a dressed-up error.

4. No changes to `SYSTEM_TOOL_SCHEMAS["get_memory_info"]`, `SYSTEM_TOOL_HANDLERS`, the executor registration (`tools/executor.py:1391`), or the guest deny-list (`persona/guest_tools.py:227`) — the tool name, schema, and handler signature are unchanged.

Pin it with tests in `halbert_core/tests/` (new file, e.g. `test_system_info_darwin_memory.py`): (a) feed the helper a canned real `vm_stat` sample (captured from an Apple Silicon host, page size 16384) and a canned `sysctl` total; assert the computed `available_bytes`/`total_bytes` exactly; (b) assert the rendered `get_memory_info` output on the Darwin branch contains the expected GB figures; (c) assert the Darwin branch NEVER opens `/proc/meminfo` (monkeypatch `builtins.open` to fail on that path, or patch `platform.system` to return 'Darwin' and assert no `open` call touches `/proc/meminfo`); (d) assert the Linux branch still parses a canned `/proc/meminfo` fixture (regression guard). Run with `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_system_info_darwin_memory.py` plus the existing `test_system_info_no_shell.py`.

## 4. What NOT to build

The rest of deep-eval packet T2 stays out of this unit, per the RESHAPE: no `scripts/run_tests_isolated.py` per-file isolation runner (that is T1-dependent and tracked separately); no ruff ASYNC210/220/221/251/PLW1514 gate and no `asyncio.to_thread` conversion of the blocking `subprocess.run` sites in `dashboard/routes/services.py:246/276/285/448`, `dashboard/routes/discovery.py:501`, `dashboard/routes/rag.py:408` (the async ratchet — separate unit); no AST shadowed-definition collection guard (separate unit); no FD-1 CI decision about replacing vs. beside `pytest tests/` (founder decision, not code). Also not in scope: fixing `get_cpu_info`'s `/proc/cpuinfo` and `/proc/uptime` reads or `get_network_info`'s `/sys/class/net` walk on Darwin (same defect class, different tools — file as a follow-up if the founder wants it; this unit is memory only, matching the dispatch row "Fix Darwin memory information defect"); no Darwin process-list or disk changes (`ps aux`/`shutil.disk_usage` already work on macOS); no change to the available-memory SEMANTIC in the scanner (do not switch speculative in or out — keep free+inactive+speculative everywhere); no new dependencies (stdlib `platform`, `subprocess`, `re` only — the two-hard-dependency Haloysius contract is untouched); no migration or back-compat shim for old error strings (nobody depends on "Error getting memory info: ..." as an API); no model-named surfaces, no colour/emoji concerns — this tool's output is consumed by the model, not rendered on a user-facing surface.

## 5. Target files
- `halbert_core/halbert_core/utils/platform.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S** — S, matching the registry and section-file estimate, and it is genuinely S: the defect is one unguarded file read, the correct Darwin implementation already exists and is battle-tested 50 lines away in `system_profile.py:443-460`, and the fix is (a) lift that logic into a pure helper in `utils/platform.py`, (b) point both the scanner and the tool at it, (c) add four small tests around canned fixtures. No new dependencies, no async work (the helper is sync subprocess; `get_memory_info` is already async and can call it directly or via the module's existing patterns), no schema or registration churn, no cross-unit coordination — dependencies: none. The only real decision is the free+inactive vs free+inactive+speculative discrepancy, and it is resolved by keeping the already-shipped Halbert semantic. It should ship immediately regardless of what happens to the rest of the original T2 packet, per the deep-eval's own note: "The Darwin memory fix is a one-file fix that should ship immediately regardless of the rest of T2."

## 8. UX rationale

No pixels change — the fix lands on the model-facing tool result, which is where Halbert's first-person voice is sourced. Before: a user asks "how's your memory?" on the Mac and the machine, which speaks as itself grounded in measured data, has nothing but "Error getting memory info: [Errno 2] No such file or directory: '/proc/meminfo'" in context — it either apologizes vaguely or, worse, guesses. After: the tool returns real measured figures ("Total: 96.0 GB / Used: 61.3 GB (63.9%) / Available: 34.7 GB ...") matching what Activity Monitor reports, so the machine's first-person answer about its own body is true. That is the whole UX: the computer stops lying about itself on the host it ships on. Consistency guardrails: keep the rendered output shape identical to the existing Linux format so any prompt-side expectations hold; no emoji, no model names, no new user-facing strings — the output template is unchanged, only its numbers become real. Failure mode also improves honestly: if `vm_stat` or `sysctl` genuinely fail on a Mac, the existing broad `except` still yields the error string — an honest "I couldn't measure" instead of a deterministic wrong-path error.

## 9. Acceptance criteria

1. On a Darwin host, awaiting `get_memory_info({})` from `halbert_core/halbert_core/tools/system_info.py` returns a string beginning "Memory Usage:" with Total/Used/Available lines whose GB figures match `sysctl -n hw.memsize` and Activity Monitor within rounding — never the string "Error getting memory info". 2. The Darwin code path never opens `/proc/meminfo` (proven by test, not by reading). 3. The Linux path is byte-identical in behavior to today (canned-`/proc/meminfo` regression test passes). 4. `SystemProfiler._scan_hardware_macos` produces the same `memory.total_gb` / `memory.available_gb` values as before the refactor (one implementation, two callers — the scanner and the tool agree). 5. Available-memory semantic is free + inactive + speculative pages everywhere, and the choice is recorded in a comment at the helper. 6. No new third-party dependency; `utils/platform.py`, `tools/system_info.py`, `discovery/scanners/system_profile.py` are the only product files touched, plus one new test file. 7. `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_system_info_darwin_memory.py halbert_core/tests/test_system_info_no_shell.py` exits 0 on an arm64 Mac.

## 10. Verification (measured state, not model judgment)

Runnable, measured-state checks only. (1) New unit tests: `cd /Volumes/4TB-BAD/Halbert && arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_system_info_darwin_memory.py -q` — must exit 0; includes the canned-`vm_stat` parse assertion, the "Darwin never opens /proc/meminfo" assertion (monkeypatched `open` records its paths), and the canned-`/proc/meminfo` Linux regression. (2) Existing guard: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_system_info_no_shell.py -q` — exit 0 (SEC-2 no-shell invariant unbroken by the edit). (3) Live measured check on the actual Mac: `arch -arm64 .venv/bin/python -c "import asyncio; from halbert_core.tools.system_info import get_memory_info; r = asyncio.run(get_memory_info({})); print(r); assert r.startswith('Memory Usage:'), r; assert 'Error getting memory info' not in r"` — exit 0 and printed figures; cross-check the printed Total against `sysctl -n hw.memsize` divided by 2^30 (must match to 0.1 GB) and Available within a few GB of Activity Monitor (memory is live, so exact equality is not asserted — the assertion is on shape, absence of the error string, and the sysctl cross-check). (4) Scanner parity: `arch -arm64 .venv/bin/python -c "from halbert_core.discovery.scanners.system_profile import SystemProfiler; p = SystemProfiler(); h = p._scan_hardware_macos(); print(h['memory']); assert 'total_gb' in h['memory'] and 'available_gb' in h['memory']"` — exit 0 with both keys present and nonzero. Baseline note: `main` carries a known nonzero failure baseline — run the two named test files plus a merge-base baseline before attributing any unrelated failure to this change.

## 11. Exclusions

Everything else from the original deep-eval T2 packet is excluded from this unit and routed as follows: (a) the per-file isolated test runner `scripts/run_tests_isolated.py` (~60 lines, `arch -arm64` prefix, PYTHONPATH pin) — to the T1 lane, since the deep-eval makes T1's hermetic environment its prerequisite and lists the runner as follow-on to T1; (b) the ruff ASYNC gate (ASYNC210/220/221/251 + PLW1514 with per-file-ignores ratchet) and the six blocking-call fixes in `dashboard/routes/services.py:246/276/285/448`, `dashboard/routes/discovery.py:501`, `dashboard/routes/rag.py:408` — to a separate async-ratchet unit (the deep-eval says the ratchet can ship first and independently; it is not this one); (c) the AST shadowed-definition collection guard (~30 lines, preventive) — to the same separate suite-integrity unit as (b); (d) the FD-1 founder decision (isolated runner replaces vs sits beside `pytest tests/` in CI) — founder decision, not code, no unit until ruled; (e) Darwin defects in the sibling tools (`get_cpu_info` reading `/proc/cpuinfo`//`/proc/uptime`, `get_network_info` walking `/sys/class/net`) — same defect class but outside the registry row's scope ("Fix Darwin memory information defect"); recommend filing a follow-up S unit rather than silently expanding this one; (f) changing the available-memory semantic (origin's free+inactive vs Halbert's free+inactive+speculative) — dropped per RESHAPE-style scoping: keep Halbert's shipped semantic, record the choice in a code comment; (g) the T5-adjacent "shared with T2" mention in the deep-eval's T5 row — that row only notes this same Darwin fix ships once; no T5 work here.

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
