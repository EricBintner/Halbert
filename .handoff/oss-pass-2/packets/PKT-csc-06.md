# PKT-CSC-06 — Terminal reattach + UTF-8 decoder + port announcement

Tier: **opus**   Milestone: **M2**   Effort: **S-M**
Collision lane: **B,E**   Merge order: **1/4 in B; 2/3 in E**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**CSC-06** — Terminal reattach + UTF-8 decoder + port announcement.

## 2. User problem

Three live defects and one half-built loop in the terminal/desktop boot path, all verified in code:

1. UTF-8 corruption across read boundaries (live defect). Every PTY consumer decodes each 4 KiB master-fd chunk independently with `errors="replace"`: `dashboard/routes/websocket.py:110` (`chunk.decode("utf-8", errors="replace")`), `dashboard/routes/terminal.py:295`, `:308` (`output.bytes().decode('utf-8', errors='replace')` on the bounded one-shot path) and `:386` (the SSE `stream_session` path). A multi-byte code point split across an `os.read` boundary is permanently replaced with U+FFFD in the user's terminal and in every `CommandResponse.output` string. Any non-ASCII output large enough to split — a `cat` of a UTF-8 document, CJK compiler errors, box-drawing TUIs — corrupts. This is independent of reconnect; it fires on a single healthy stream.

2. PTY reattach drops the replay buffer (half-built loop). `streaming/pty.py:179` enqueues `("__replay__", self.get_buffer())` as the first item on every `attach()` queue, but the only in-tree consumers (`read_chunk()` at pty.py:348 and the SSE/WS routes built on it) skip the tuple: `if isinstance(item, tuple) and item[0] == "__replay__": continue`. So a reconnecting frontend receives nothing of the scrollback that exists precisely for reattach (pty.py docstring: "the frontend can render history on attach"). Meanwhile the frontend `useTerminalSessions.ts` `ws.onclose` (~line 310-318) marks a `running` session `done` with `exitCode ?? -1` on any socket close — a wifi flap presents as a finished terminal with a false exit code, and there is no `reconnecting` status, no backoff, no reconnect policy at all.

3. Port selection is a TOCTOU (defect that has already bitten once). `src-tauri/src/lib.rs:33-35` probes freeness with `std::net::TcpListener::bind((HOST, port)).is_ok()`, drops the listener, and later passes the port to the sidecar via `HALBERT_PORT` (lib.rs:131); the comment at lib.rs:56-58 records that a second Halbert or any dev server holding 8000 already left the webview pointed at the wrong backend. The Python side has its own duplicate scan (`dashboard/__main__.py:48-57 find_available_port`, range 8000-8100). Nothing confirms which port uvicorn actually bound; the shell guesses, the webview trusts the guess.

4. No panic hook in the Tauri shell. Every diagnostic in the spawn path is `eprintln!`/`println!` (lib.rs:144, :152, :154, :156, :170), discarded when the .app is launched from Finder. A panic in the shell leaves zero durable evidence — which also makes M3's planned "show the tail on timeout" worthless, since there is no sink to tail.

## 3. What to build

Four changes, in priority order (1 and 2 are defects; 3 closes the reattach loop; 4 is boot-path hardening):

1. Per-connection incremental UTF-8 decoder (pty.py lane, plus its two route consumers). Replace every per-chunk `bytes.decode("utf-8", errors="replace")` with a `codecs.getincrementaldecoder("utf-8")(errors="replace")` instance held per stream lifetime. Sites: `dashboard/routes/websocket.py` (~line 106-110, decoder per websocket connection, instantiated next to the `read_chunk()` loop), `dashboard/routes/terminal.py` `stream_session` event_gen (~line 384-386, decoder per SSE generator), and the one-shot `CommandResponse` path (terminal.py:295, :308 — `BoundedOutput` accumulates raw bytes so a single final decode is already boundary-safe; keep that but route it through the same helper for one behavior definition). Put the helper in `streaming/pty.py` (e.g. `make_utf8_decoder()`) so there is exactly one place the errors policy is decided. A split multi-byte code point must reassemble across chunks; a decoder flush at end-of-stream emits any partial tail as U+FFFD exactly once.

2. PTY reattach: deliver the replay buffer as a typed frame instead of dropping it. In `streaming/pty.py` `read_chunk()` (~line 348), stop silently skipping the `("__replay__", bytes)` tuple — yield it to consumers as a distinct item (or expose `attach()`-level typing directly). In `dashboard/routes/websocket.py` and `terminal.py` `stream_session`, serialize it as a typed frame `{"type": "replay", "data": <decoded scrollback>}` sent once at stream start, decoded through the same incremental decoder (replay bytes may end mid-code-point and the live tail continues the sequence). Frontend `useTerminalSessions.ts`: handle `msg.type === 'replay'` by replacing (not appending to) `s.output`; add `'reconnecting'` to the session status union; in `ws.onclose`, a session with status `running` transitions to `reconnecting` (never to `done` with `exitCode -1`), and only the real `exit` frame or an explicit reconnect-policy give-up sets `done`. Add a pure reconnect-policy module (new file, e.g. `frontend/src/lib/terminalReconnectPolicy.ts`): backoff schedule, attempt ceiling, close-code classification (abnormal vs. clean), no framework imports, unit-testable in isolation. On successful reattach the typed replay frame restores scrollback and status returns to `running`.

3. Port announcement: `HALBERT_BACKEND_READY port=<N>`. In `dashboard/__main__.py`, after uvicorn has actually bound (run uvicorn programmatically via `uvicorn.Config`/`uvicorn.Server` and emit after `server.started`, or bind the socket ourselves and pass the fd), print exactly one stdout line `HALBERT_BACKEND_READY port=<N>` (flush=True). In `src-tauri/src/lib.rs` `spawn_backend` (~line 125-156), parse that line from the sidecar's stdout in the existing `CommandEvent::Stdout` match arm; store the announced port as the authoritative `api_base()` port (replacing the probed `backend_port()` guess as source of truth once received — the `OnceLock` gets set from the announcement, with the probe kept only as the value passed to the sidecar's env). The webview/IPC path waits for the announcement under a floored deadline (e.g. 15 s floor, no upper-ceiling guess); on deadline expiry, surface the captured stderr tail rather than pointing the webview at an unverified port. `find_available_port` in `__main__.py` keeps its `--find-port` role; the announcement is what closes the TOCTOU regardless of which side picked the port.

4. Tauri panic hook. In `src-tauri/src/lib.rs` setup, install `std::panic::set_hook` writing the panic payload + backtrace to a durable file under the app state dir (resolve via Tauri's `app.path()` state directory — capability boundary, not a hardcoded path), opened with create+append, written and `sync_all()`-flushed synchronously inside the hook before the default hook runs. Cap the file (rotate at ~1 MiB) so a panic loop cannot fill the disk. This is the sink M3's timeout-tail display will read.

## 4. What NOT to build

No broad session/terminal registry, no session-tree persistence, no cross-process session resume store — the FINAL-CRITICAL-DISCOVERY-BACKLOG verdict for CSC-06 is RESHAPE ("keep the resume contract, drop the broad registry"); the registry flavor is out. No Windows PTY support (pty.py header: Unix-only for v1). No changes to the command classifier, pager neutering, or spawn path — the `_PAGER_NEUTERED` env and `os.execvpe` logic stay untouched. No frontend visual redesign: the `reconnecting` status reuses existing pill/indicator components with `shared-tokens/tokens.css` colours, no new palette entries, no emoji, no session list UI (standing directive: one seamless surface). No new hard Python dependency (Haloysius subtractive contract: `codecs` is stdlib). No model involvement anywhere — decoding, replay, backoff, and port parsing are deterministic. No changes to `auth` ticket flow, `guard_bind`, or the SEC-1 token handshake. No behavior change for clean exits — an `exit` frame with a real code still lands exactly once and still sets `done`.

## 5. Target files
- `halbert_core/halbert_core/streaming/pty.py`
- `halbert_core/halbert_core/dashboard/frontend/src-tauri/src/lib.rs`
- `halbert_core/halbert_core/dashboard/__main__.py`

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S-M** — S-M is the right size because three of the four changes are small, well-bounded edits to already-understood sites: the decoder is a stdlib `codecs.getincrementaldecoder` swapped in at three decode call sites plus one helper; the port announcement is one stdout line in `__main__.py` plus one match arm in an existing `CommandEvent::Stdout` loop in lib.rs (the async reader task already exists at lib.rs:148); the panic hook is ~30 lines of Rust. The medium half is the reattach loop: typing the replay frame end-to-end (pty.py → websocket.py/terminal.py → useTerminalSessions.ts) and the new pure reconnect-policy module with its unit tests. It stays under M because no protocol redesign is needed — the `("__replay__", ...)` tuple and the scrollback buffer already exist and are already bounded; this unit wires what is there rather than building storage. The four pieces share files (lib.rs, __main__.py both touched by 3 and 4; the two route files both touched by 1 and 2), so building them together in one packet avoids double-touching the same hunks, as the deep-eval's Opportunities note flags.

## 8. UX rationale

The user never sees any of the mechanisms; they see their terminals stop lying. Non-ASCII output — an accented filename, a CJK error, a `tree` drawing box characters — renders intact instead of sprouting U+FFFD replacement glyphs mid-stream. When the network or the backend blips, a running terminal shows a subtle `reconnecting` state (existing indicator component, shared-tokens colour, no emoji) and then returns with its scrollback intact, instead of silently flipping to a finished state with a bogus exit code of -1 that reads as "the command failed." A false exit on a wifi flap is a real trust injury for a steward that speaks in first person grounded in measured data: the machine claiming a command exited when it never did is exactly the class of statement Halbert must never make. On desktop boot, the app waits for the backend to say the port it actually bound, so the first paint is always our own backend — no more window pointed at a stranger's dev server. And when the shell panics, there is a durable crash record on disk, so a "the app just vanished" report has evidence behind it instead of nothing. No new surfaces, no new settings, no model names anywhere; every status string is a state of the computer, spoken as the computer.

## 9. Acceptance criteria

1. A PTY stream emitting a multi-byte UTF-8 sequence (e.g. 10,000 repetitions of a 4-byte code point) survives a forced split at every possible chunk alignment with zero U+FFFD in the reassembled output — verified by a test that feeds byte chunks split at offsets 1, 2, and 3 of a 4-byte sequence through the decoder path and asserts the joined string equals the input.

2. On websocket reconnect to a still-running session, the frontend receives exactly one `{"type": "replay", ...}` frame before any `stdout` frames; `useTerminalSessions` sets status `reconnecting` on abnormal close (never `done`/`-1`), restores `running` on reattach, and replaces output with the replay payload. A close after the real `exit` frame still yields `done` with the true code.

3. The reconnect-policy module is pure (no DOM/framework imports), covered by unit tests for its backoff schedule, attempt ceiling, and close-code classification.

4. Booting the backend prints exactly one line matching `^HALBERT_BACKEND_READY port=\d+$` to stdout after the port is bound, and the port named in that line is the port a TCP connect to `127.0.0.1:<N>` succeeds on (verified by an integration test that parses the line and dials the port).

5. The Tauri shell, when the backend announces a port different from the probed guess, uses the announced port for the webview — the probe and the announcement can never disagree silently.

6. Triggering a Rust panic in a debug build writes a file containing the panic message to the app state dir before process exit, and the file survives relaunch.

7. No new hard dependency in any Python package metadata; no hardcoded colour values in touched frontend files (tokens.css only); no emoji in any new string.

## 10. Verification (measured state, not model judgment)

All checks runnable from a worktree of this checkout:

1. `arch -arm64 ./wt_pytest.py halbert_core/tests/test_pty_fanout.py halbert_core/tests/test_terminal_route.py` — existing PTY/route suites stay green (regression floor; `main` has a known nonzero baseline, so diff against a merge-base baseline run first).

2. New test (add as `halbert_core/tests/test_pty_utf8_incremental.py`): construct the incremental decoder from `streaming/pty.py`, feed a 4-byte code point split across chunk boundaries at offsets 1/2/3 plus a large mixed ASCII/non-ASCII payload through the websocket route's decode path, assert `result.encode("utf-8") == input_bytes` and `"�" not in result`. Run: `arch -arm64 ./wt_pytest.py halbert_core/tests/test_pty_utf8_incremental.py` — exit code 0.

3. New test asserting the replay frame is delivered not dropped: attach two consumers to a session with scrollback, assert consumer 2's first yielded item is the typed replay carrying `get_buffer()` content. Included in the new test file above or as a case in `test_pty_fanout.py`.

4. Frontend unit tests: `cd halbert_core/halbert_core/dashboard/frontend && npx vitest run src/hooks/useTerminalSessions.test.ts src/lib/terminalReconnectPolicy.test.ts` — assert reconnecting transition on abnormal close, replay-frame output replacement, and the policy module's backoff/ceiling tables. Exit code 0. Plus `npm run typecheck` clean for the touched workspaces.

5. Port announcement integration check: `arch -arm64 .venv/bin/python -m halbert_core.dashboard --find-port` (or with a fixed `--port`), capture stdout, `grep -m1 -E '^HALBERT_BACKEND_READY port=[0-9]+$'`, then `nc -z 127.0.0.1 <parsed-port>` — the dial must succeed (exit 0). Scriptable as a single shell assertion; also encodable as a pytest spawning the module as a subprocess.

6. Tauri-side verification: `cd halbert_core/halbert_core/dashboard/frontend/src-tauri && cargo test` for the port-parse unit (feed a synthetic `CommandEvent::Stdout` line, assert the stored port updates); manual/integration: `cargo build`, run the .app with a panic-injection debug hook, confirm the state-dir panic file exists, is non-empty, and persists after relaunch. Report the file path and byte count as measured evidence.

## 11. Exclusions

- Broad session/terminal registry and cross-process resume store — dropped per the FINAL-CRITICAL-DISCOVERY-BACKLOG RESHAPE verdict on CSC-06 ("keep the resume contract, drop the broad registry"). The resume contract kept here is exactly: replay frame typed end-to-end + reconnecting status + reconnect policy. Anything session-tree-shaped belongs to CSC-04 (session-tree integrity, ACCEPT) if it lands at all.
- Conversation-store / crash-recovery of the chat itself — CSC-01 and CSC-03/CSC-05 territory (ACCEPT/RESHAPE respectively); this unit touches terminals and desktop boot only.
- Windows PTY support — out per pty.py's own v1 scoping; no unit owns it yet (post-v1 roadmap item).
- M3's "show the captured tail on boot timeout" UI — deferred to M3/DIST-1 as the deep-eval's minimum-viable-version note assigns (this unit builds only the sink it will read: the panic hook file and the stderr capture already in lib.rs's reader task).
- Idle-terminal reaping policy and agent-reuse-of-idle-terminals (the "watched terminals" direction) — separate terminal-direction work, not in this packet's target files.
- Any `--find-port` range/UX redesign of `find_available_port` — left as-is; the announcement makes the pick verifiable regardless of which side picks.

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
