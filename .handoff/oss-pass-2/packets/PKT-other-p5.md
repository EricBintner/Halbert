# PKT-OTHER-P5 — Install identity (mDNS) + bounded downloads

Tier: **opus**   Milestone: **M3**   Effort: **S-M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**OTHER-P5** — Install identity (mDNS) + bounded downloads.

## 2. User problem

Two real defects, both closed by the same atomic-write recipe. (1) Install identity (HM14-C20): `federation/peer_discovery.py:295` builds the mDNS `node_id` as `HALBERT_PERSONA_ID + '-' + socket.gethostname()` and broadcasts it in the Zeroconf TXT record — the raw hostname goes out on the LAN, violating the standing directive "the engaged surface carries the onboarding name, never the raw hostname." There is no stable, opaque install identity anywhere; identity is re-derived from the hostname on every announce, so a hostname change silently re-identifies the node to already-paired peers. (2) Bounded downloads (OC21-C6): 66 outbound `requests.get`/`urlopen` sites have no byte cap and no staged rename. Concretely, `tools/web_search.py:99-110` (DuckDuckGo) and `:186-197` (SearXNG) call `await resp.text()` / `await resp.json()` with only an aiohttp total-timeout — a malicious or buggy endpoint can allocate unbounded memory; and `rag/scrapers/homebrew.py:76` `requests.get(url, timeout=...)` reads third-party formula endpoints with no size bound. Neither defect has a migration concern: FD-4's recommended default is accepted — the mDNS node_id MAY switch, already-paired peers re-pair, old ids are left on disk unread per the no-users/no-migrations rule.

## 3. What to build

Two deliverables sharing one recipe, install identity shipping FIRST (it removes a live standing-directive violation; bounded download follows in the same packet).

A) Install identity — new file `halbert_core/halbert_core/identity/install_id.py` exporting `read_or_create_install_id(state_dir: str) -> Optional[str]`. On first call: mint a 32-hex `uuid4().hex`, write it via the durable_write helper (mkstemp in `state_dir`, write+flush, fsync, `os.replace` to `<state_dir>/install_id`, then `_fsync_directory(state_dir)`), with an fcntl advisory lock on `<state_dir>/install_id.lock` held across read-modify-create plus a module-level thread lock, mode 0600. On subsequent calls: read and return the existing id; return None only on unrecoverable I/O error (never raise into the announce path). Returns None is acceptable per signature but the happy path always returns the persisted id.

Wire it in `federation/peer_discovery.py` `get_node_identity()` (~line 295): replace `node_id = os.environ.get("HALBERT_PERSONA_ID", "halbert") + "-" + socket.gethostname()` with `node_id = f"{os.environ.get('HALBERT_PERSONA_ID', 'halbert')}-{read_or_create_install_id(state_dir()) or socket.gethostname()}"` — persona prefix preserved for multi-instance, hostname replaced by the opaque install id, hostname kept only as last-resort fallback if the state dir is truly unwritable. `node_name` continues to come from `resolve_entity_name()` (already correct — never raw hostname). Import `state_dir` from `utils/paths.py:63`.

B) Bounded download — new file `halbert_core/halbert_core/utils/bounded_download.py` exporting `download(url, dest, max_bytes, max_decompressed=None) -> Path`: streams via `requests.get(url, stream=True)` + `iter_content`, counts bytes, aborts and deletes the partial file the moment the cap is exceeded; writes to `<dest>.partial` then fsync + `os.replace` (via durable_write recipe); a per-dest single-flight lock prevents two coroutines/threads racing the same dest; on refresh failure with an existing complete dest, serves the stale copy rather than surfacing the error. Also `async read_bounded(resp, max_bytes) -> bytes` for aiohttp: wraps `resp.content.read` in chunks, raising a typed `DownloadTooLarge` past the cap.

Adopt B in this packet at exactly two sites: `rag/scrapers/homebrew.py:72-78` `_make_request` (route through `download()` with a scraper-appropriate cap, e.g. 64 MiB) and `tools/web_search.py` both fetches (`:99-110` and `:186-197`) — replace `await resp.text()` and `await resp.json()` with `await read_bounded(resp, cap)` then decode/parse the bounded bytes (e.g. 8 MiB for HTML, 4 MiB for JSON). Both items use the shared `utils/durable_write.py` helper (dependency — do NOT reimplement the tmp+fsync+os.replace+dir-fsync recipe in this packet).

## 4. What NOT to build

- Do NOT reimplement the atomic-write recipe inline. `utils/durable_write.py` is a declared dependency (PKT-durable-write, M0); consume it. If it is not yet merged when this packet starts, land a minimal local copy and mark it for dedupe at merge — do not fork the recipe per-call-site.
- Do NOT fix the A06 ledger fsync or A12-G8 guest_homes.yml rename here — those ride the SAME durable_write recipe but belong to their own packets (scheduler durability / guest persona). Note them as consumers, don't touch the files.
- Do NOT migrate or invalidate old node_ids, do not delete any superseded identity file, and do not build a re-pairing flow — FD-4 accepts the id switch; old data stays on disk unread (no-users rule).
- Do NOT sweep the other ~63 outbound fetch sites. Only `homebrew.py` and the two `web_search.py` fetches adopt bounded_download in this packet; a repo-wide adoption audit is out of scope.
- Do NOT touch `PeerListener` Zeroconf/TODO(federation-9.7) code, the compute broker/router, or any peer-pairing crypto — `node_id` is consumed as an opaque string by `compute_router.py`, `compute_endpoint.py`, `fleet_proxy.py`; no changes needed there.
- Do NOT add a settings UI, doctor check, or config knob for either mechanism — deterministic behaviour, no surface changes.
- No model involvement anywhere: identity minting and byte-capping are both deterministic (never a model where a template suffices).

## 5. Target files
- `halbert_core/halbert_core/federation/peer_discovery.py`

## 6. Dependencies

durable_write, OTHER-P4

## 7. Effort

**S-M** — S-M total, matching the registry line. The install identity is S: one new ~80-line module (`identity/install_id.py`), a one-line wire-in at `peer_discovery.py:295`, and a focused unit test; the recipe (mkstemp/fsync/os.replace/dir-fsync/fcntl) comes from durable_write, not invented here. The bounded download is M: `utils/bounded_download.py` is ~150 lines with two concurrency edges (per-dest single-flight, stale-serve-on-refresh-failure) plus the aiohttp variant, and the two adoption sites each need their decode path adjusted (bounded bytes -> text/json parse). Effort is kept down because durable_write is a dependency, not built here; it would be M-M otherwise. The two items share only the recipe, not logic — packeted together per the deep-eval to avoid a third copy of the atomic-write pattern, which the standing one-choke-point rule forbids.

## 8. UX rationale

No user-facing surface changes — and that is the point for identity. Today the node announces itself to the LAN as `halbert-Erics-MacBook-Pro` (raw hostname in the mDNS TXT record); after this packet it announces as `halbert-<32-hex>` while the human-facing `node_name` remains the onboarding ai_name via `resolve_entity_name()`. This is exactly the standing rule: the engaged surface carries the onboarding name, never the raw hostname. First-person, grounded-in-measured-data framing is untouched (no copy changes). For bounded downloads the UX is reliability the user never sees: a runaway third-party search or formula endpoint can no longer balloon the process's memory and take the steward down mid-conversation — the one seamless conversation survives upstream misbehaviour. Nothing is staged, nothing is executed from a UI, no model is named, no colour or emoji is introduced.

## 9. Acceptance criteria

1. `get_node_identity()` returns a `node_id` that does NOT contain the raw hostname: with `HALBERT_PERSONA_ID` unset, `node_id` matches `^halbert-[0-9a-f]{32}$`, and calling it twice returns the SAME id (persistence across calls).
2. The id survives a simulated restart: delete nothing, call `read_or_create_install_id` in a fresh process against the same state dir, get the identical value; the file at `<state_dir>/install_id` is mode 0600 and contains exactly 32 hex chars.
3. Corruption safety: write garbage to `<state_dir>/install_id.partial`, call the reader — it returns the last-good id or mints a new one, never the partial garbage (atomicity via os.replace).
4. `download()` writes a complete file for a payload under the cap; for a payload over the cap it raises/returns failure AND leaves no `<dest>` and no `<dest>.partial` behind (or leaves the prior good dest intact on refresh).
5. `read_bounded(resp, cap)` raises `DownloadTooLarge` when the body exceeds cap and never materialises more than cap bytes in memory.
6. Both `web_search.py` fetch paths route through `read_bounded`; `homebrew.py` routes through `download()`. No raw-hostname string appears in any mDNS-related return value.
7. No new test failures beyond the known-red baseline (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py).

## 10. Verification (measured state, not model judgment)

Run from a worktree with the arch prefix (never bare pytest):

  arch -arm64 ./wt_pytest.py halbert_core/tests/test_install_id.py halbert_core/tests/test_bounded_download.py -x -q

plus the existing federation suite to confirm no consumer broke:

  arch -arm64 ./wt_pytest.py halbert_core/tests/test_peer_pairing_security.py -q

Measured-state checks the tests must perform (no model judgment):
- test_install_id: `tmp_path` state dir; first call creates `<tmp>/install_id` — assert `os.stat(path).st_mode & 0o777 == 0o600`, content matches `^[0-9a-f]{32}$`; second call in a new module instance returns the identical string; assert `socket.gethostname()` NOT in `get_node_identity()["node_id"]` (monkeypatch `HALBERT_PERSONA_ID` unset and `paths.state_dir` to tmp).
- test_bounded_download: spin a local `http.server` in a thread serving a 1 MiB body; `download(url, dest, max_bytes=2*1024*1024)` succeeds and `dest.stat().st_size == 1MiB`; then serve 3 MiB with `max_bytes=1MiB` — assert failure, `not dest.exists()`, `not Path(str(dest)+'.partial').exists()`. For aiohttp: `read_bounded` against a streamed local endpoint raises `DownloadTooLarge` at the cap (assert exception type, exit behaviour deterministic).
- Static check: `grep -n "gethostname" halbert_core/halbert_core/federation/peer_discovery.py` returns at most the last-resort fallback line, and `grep -n "resp.text()\|resp.json()" halbert_core/halbert_core/tools/web_search.py` returns zero hits (both replaced by bounded reads).
- Exit code of the pytest run is 0, and failures are diffed against the known-red baseline named in acceptance criterion 7.

## 11. Exclusions

- A06 restart-ledger fsync and A12-G8 guest_homes.yml rename fsync: same durable_write recipe, different owners — scheduler durability packet and guest-persona packet respectively. Referenced in code comments as consumers, files untouched here.
- The remaining ~63 uncapped outbound fetch sites (66 total minus homebrew.py and the two web_search fetches): M5b tail — a follow-up adoption-audit unit that sweeps `requests.get`/`urlopen` repo-wide onto bounded_download. This packet proves the helper at the three named sites only.
- Repo-wide `utils/durable_write.py` hardening, mode/chmod options beyond 0600, and its own test matrix: owned by PKT-durable-write (M0 dependency), not this packet.
- FD-4 re-pairing UX, peer re-announcement on id change, and any migration of old node_ids: dropped per the RESHAPE/FD-4 default — no users, peers re-pair, old data left unread. Never build.
- PeerListener Zeroconf implementation (TODO federation-9.7), compute-broker/router changes: federation milestone work, untouched — `node_id` stays an opaque string to all consumers.
- Any doctor/diagnostics check or settings surface for identity or download caps: DIAG-01 registry territory if ever wanted; not built here.
- The `max_decompressed` gzip-bomb guard inside bounded_download: noted in the signature for forward-compat but not implemented in this slice (none of the three adoption sites requests compressed payloads today); M5b tail if a consumer needs it.

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
