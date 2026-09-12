# PKT-P5 — Centralized SSRF / base-URL guard

Tier: **opus**   Milestone: **M3**   Effort: **S-M**
Collision lane: **none (file-disjoint)**   Merge order: **n/a**
Verified against: halbert `main` @ `fbd725e9` (2026-09-11)

---

## 1. Packet

**P5** — Centralized SSRF / base-URL guard.

## 2. User problem

Halbert validates outbound base URLs in three disconnected places, and the main one is bypassable. `is_safe_url(url, provider)` at `halbert_core/halbert_core/dashboard/routes/llm.py:98-130` is the de-facto SSRF check for provider/test/probe calls (consumed at llm.py:507, 681, 739 and re-imported by `dashboard/routes/compute.py:37,218`), but its local-provider branch (llm.py:113-114) returns True unconditionally for provider in ("ollama", "lm-studio", "apple-foundation") — before any resolution — so `provider='ollama'` plus an arbitrary URL skips the entire private-network check. The deep-eval (group1, RESHAPEd SSRF packet) confirms this is a real hole: the "local model traffic is local" guarantee is only as strong as a literal string the caller passes. Meanwhile URL validation is duplicated per call site with different rules: `mcp/client.py:348 validate_http_url()` checks scheme+netloc only, `persona/guest_homes.py:62-67 _normalise()` checks scheme+netloc only, and fetches that follow redirects (`rag/ingestion.py:254` requests.head with allow_redirects=True; `federation/connectivity.py:127` allow_redirects=True) re-resolve nothing per hop, so a safe URL can 302 to 169.254.169.254. Credentialed URLs (scheme://user:password@host) are not structurally rejected or redacted at any of these boundaries — VMV-3's guest-home fix and MCP-C's scheme validation are waiting on one shared guard (backlog §3.16). The backlog verdict for P5 is RESHAPE: keep the centralized guard, drop per-route duplication; drop the link-detection and ReDoS-guard items (no consumer / unwired).

## 3. What to build

Create `halbert_core/halbert_core/security/url_guard.py` — one choke-point module, no route-local copies. Public surface: (1) `validate_base_url(url, *, local: bool) -> str` — parse with urllib.parse.urlparse; require scheme in ("http","https") and a netloc; reject any userinfo (parsed.username or parsed.password set) so credentialed URLs can never be fetched or later rendered as display names; resolve the hostname once via socket.getaddrinfo and classify every returned address with the ipaddress module (is_private / is_loopback / is_link_local / is_reserved / is_multicast), plus the existing literal denylist ("169.254.169.254", "metadata.google.internal"). When local is False, any non-public address rejects. When local is True, loopback is permitted only on the allowlisted port set currently at llm.py:64 `_ALLOWED_LOCAL_PORTS = {11434, 1234, 1235, 11435}` (move the set into url_guard); private/link-local/reserved ranges still reject even for local — closing the llm.py:113-114 unconditional-True hole. The `local` flag is derived by callers from `is_local_model()` (model/llm_config.py:181), never from a provider-name string, per the model-locality invariant. (2) `check_redirect(url, *, local: bool) -> None` — the same validation exposed as a per-hop re-validator that fetching code calls on every 3xx Location before following; document that `allow_redirects=True` without per-hop re-validation is the banned pattern. (3) A small result/exception type (e.g. `UrlRejected(ValueError)` with a reason string) so routes can return their existing 400s. Migrate the four existing call sites in this packet: llm.py:507/681/739 and compute.py:218 call `validate_base_url(...)` with locality from is_local_model(); delete `is_safe_url` from routes/llm.py and the re-import in routes/compute.py. Keep `mcp/client.py:validate_http_url` and `guest_homes._normalise` untouched (MCP-C and VMV-3 respectively will re-point them at url_guard). Add `halbert_core/tests/test_url_guard.py` covering: scheme rejection (file://, gopher://, empty), userinfo rejection (http://user:pass@host), metadata denylist, DNS pinned to a private address (monkeypatch socket.getaddrinfo), local=True allowing 127.0.0.1:11434 but rejecting 127.0.0.1:9999 and 10.0.0.5:anything, local=False rejecting loopback even on allowlisted ports, and check_redirect rejecting a redirect from a public host to 169.254.169.254.

## 4. What NOT to build

No proxy opt-in / trust_env work (that is the env-policy axis, cross-cutting item 7 — belongs to TT-02/MP-6's build_subprocess_env lane, not this file). No bounded response-body caps (stays with the fetching callers; VMV-3 owns media limits). No outbound secret-pattern scanning, credential registration with the redaction registry, SecretRef grammar, or sealing — the credential-registration slice of the deep-eval packet is a separate RESHAPE child, and sealing is DEFERRED per founder decision F-A5. No history-read projection, audit-extras closure, tee fail-closed, OSC 133 stripping, or media deny-list — those are the other RESHAPE children of the same deep-eval packet (P2/P4 lanes), not P5. Do not migrate mcp/client.py:validate_http_url (MCP-C's packet), guest_homes._normalise (VMV-3's packet), or the redirect-following fetchers rag/ingestion.py:254 and federation/connectivity.py:127 (MP-6 redirect-policy consumer) — this packet ships the guard plus the four llm/compute call sites only; the other consumers re-point in their own packets. No link detection (dropped per RESHAPE — no consumer) and no ReDoS guard (dropped per RESHAPE — unwired). No new runtime dependencies — stdlib only (urllib, socket, ipaddress), consistent with the Haloysius two-dependency contract. No UI surface, no model involvement — this is a deterministic predicate, per "never a model where a template suffices".

## 5. Target files
- `halbert_core/halbert_core/security/url_guard.py` [new file]

## 6. Dependencies

None — may dispatch immediately.

## 7. Effort

**S-M** — S-M. One new module of roughly 150 lines of stdlib-only code (parse, one getaddrinfo resolution, ipaddress classification, an allowlist set moved verbatim from llm.py:64), a mechanical four-site migration (llm.py:507/681/739, compute.py:218) that deletes more code than it adds (is_safe_url's 33 lines and the compute.py re-import go away), plus one test file. The design is fully pinned by the deep-eval RESHAPE line and backlog §3.16 — no open decisions, no founder gates, no dependencies (dispatch-index lane "-", merge order n/a). It is not S-only because the local/allowlisted-port semantics must be preserved exactly (the llm.py:878-898 discovery block documents why loopback probing exists and must keep working for Ollama/LM Studio/Apple Foundation discovery), and the locality flag must be wired through is_local_model() rather than the provider string, which touches the request models at the three llm.py call sites.

## 8. UX rationale

No new surface — this is invisible hardening under the one seamless conversation. What the user experiences is that the promises Halbert already makes become true: when a connection slot is a local slot, traffic stays on this machine — measured, not assumed — because the locality judgment now comes from is_local_model() and the port allowlist instead of a caller-supplied provider string. When a base URL is rejected, the existing dashboard routes keep returning their current 400s with a plain reason ("that address is not one I may contact"), spoken as the computer in first person; no stack traces, no raw URLs with credentials echoed back — credentialed URLs are rejected structurally, so a pasted `http://user:pass@host` can never round-trip into a settings label, an error message, or a model prompt. Error text and colours on the settings surface are unchanged and remain governed by shared-tokens/tokens.css; no emoji; no model is ever named — the rejection speaks about the address, never the provider's product.

## 9. Acceptance criteria

1. `halbert_core/halbert_core/security/url_guard.py` exists and exports validate_base_url, check_redirect, and the local-port allowlist; `is_safe_url` no longer exists in dashboard/routes/llm.py and the `from .llm import is_safe_url` line is gone from dashboard/routes/compute.py (grep confirms zero references to is_safe_url outside build/lib). 2. The four migrated call sites (llm.py x3, compute.py x1) call url_guard.validate_base_url with locality derived from is_local_model(), and provider='ollama' with a URL resolving to a non-loopback private address is now rejected where it previously returned True. 3. Credentialed URLs (any userinfo) are rejected at validate_base_url regardless of locality. 4. Loopback on a non-allowlisted port (e.g. 127.0.0.1:9999) and private RFC-1918 addresses are rejected even with local=True; 127.0.0.1:11434 passes with local=True, so local provider discovery keeps working. 5. check_redirect applied to a 3xx chain public→169.254.169.254 rejects the second hop. 6. The new test file passes and no test outside the known-red baseline (test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py — ~23 failures as of 2026-09-11) regresses.

## 10. Verification (measured state, not model judgment)

From the worktree root: `arch -arm64 ./wt_pytest.py halbert_core/tests/test_url_guard.py -v` — every test passes (from the main checkout instead: `arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_url_guard.py -v`). Then prove the hole is closed with measured grep state: `grep -rn "is_safe_url" halbert_core/halbert_core/ --include="*.py" | grep -v build/lib` exits 1 (no matches — the old function and its re-import are gone), and `grep -n "validate_base_url" halbert_core/halbert_core/dashboard/routes/llm.py halbert_core/halbert_core/dashboard/routes/compute.py` shows exactly four call sites. Then the no-regression gate: `arch -arm64 ./wt_pytest.py halbert_core/tests/test_llm_routes.py halbert_core/tests/test_compute_probe.py halbert_core/tests/test_llm_discover.py -q` — exit code 0 with all tests passing (these files are green on main and exercise the migrated call sites). Finally a targeted behavioural check: `arch -arm64 ./wt_pytest.py halbert_core/tests -q 2>&1 | tail -5` — the failure count equals the known-red baseline (~23, confined to test_agent_model_override.py, test_agent_model_selected_event.py, test_no_model_names_in_user_facing_source.py, test_num_ctx.py); any new failure is this packet's.

## 11. Exclusions

To other units: (a) migrating `mcp/client.py:348 validate_http_url()` onto the guard → MCP-C (URL scheme validation consumer per §3.16); (b) migrating `persona/guest_homes.py:62 _normalise()` and the credentialed-URL display-name fix → VMV-3, which lists P5 as a dependency; (c) per-hop redirect re-validation wired into the actual redirect-following fetchers `rag/ingestion.py:254` and `federation/connectivity.py:127` → MP-6's redirect-policy slice (this packet ships check_redirect as the primitive only); (d) proxy opt-in / trust_env=False on local-model sessions → the env-policy module (cross-cutting item 7, TT-02/MP-6 lane); (e) bounded response bodies and media limits → VMV-3; (f) credential registration with the redaction registry at llm_config.py:465/898-906, error-text routing, history-read projection for GET /agent/timeline, audit-extras closure, tee fail-closed → the sibling RESHAPE children of the same deep-eval packet (separate dispatch units); (g) OSC 133 marker stripping → the shared prompt-sanitizer unit (cross-cutting item 1). Deferred per founder decision: SecretRef grammar and secret sealing → F-A5 says defer until execute_code needs a credential in-process (M5b tail at the earliest). Dropped per RESHAPE: link detection (no consumer exists anywhere in the tree) and the ReDoS guard (unwired — nothing calls it). Not in scope at all: any UI change, any migration of stored config (no-users rule — no back-compat shims), and any change to the three discovery URL constants at llm.py:896-898 beyond what the allowlist move requires.

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
