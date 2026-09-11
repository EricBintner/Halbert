# Halbert — Security Remediation TODO

Working checklist for the 186 confirmed findings in `.handoff/SECURITY-AUDIT-FINDINGS-2026-09-06.md`.
Design: `documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md`.
Full plan with definitions of done: `.handoff/SECURITY-IMPLEMENTATION-PLAN-2026-09-06.md`.

`ROADMAP.md` §3 stays the only doc that says now/next/deferred — this file is the working
checklist underneath the `SEC-*` rows, not a second roadmap.

**Hard sequencing rule:** `SEC-1 → SEC-2/3/4 → SEC-5 + SEC-8 → SEC-7 → SEC-6` ship as one train
and nothing else lands first. No channel work, no signing work, no release notes.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done, wired and tested · `[!]` blocked

---

## P0 — ship-blocking, exploitable now (103 findings · 8 crit · 31 high)

### `[~]` SEC-1 · One door: every listener authenticates — 30 findings (C5 H17 M5 L3)
**Blocks everything.** Closes the most findings of any single change.
- [x] `require_owner` dependency; default-deny router factory (`dashboard/auth.py`, `mount_api` in
      `create_app`). All 38 routers registered through it — a new route is authenticated by omission.
- [x] Per-launch bearer token: `<state_dir>/api-token`, created `0600` in a `0700` dir via
      `os.open` (no chmod-after-write window). `HALBERT_API_TOKEN` overrides.
- [x] Host-header allowlist middleware → 421 for any unlisted Host (DNS rebinding)
- [x] Origin **and** credential check on all four WebSocket handlers
- [x] `_is_local_client` returns **False** on absent `request.client`
- [~] Non-loopback bind refuses to start without a token — **claimed done, actually partial.**
      `guard_bind` runs only in `python -m halbert_core.dashboard`. The two shipped `deploy/*.service`
      units, `packaging/systemd/.../halbert-dashboard.service`, `Halbert/main.py:cmd_dashboard_serve`
      and `app.py`'s own `__main__` block all run uvicorn against `dashboard.app:app` directly and
      never reach it. `Environment=HALBERT_HOST` in those units is inert for the same reason.
      The unit comments have been corrected to say so; the guard still needs wiring where the bind
      address is actually known. Bounded by the fact that `require_owner` now covers every route.
- [x] MCP HTTP refuses to serve with no bearer token; validates Origin and Host
      (`_check_forgery`; "open mode" deleted)
- [x] Wyoming binds `127.0.0.1` (`audio/config.py`, `wyoming_ingress.py`)
- [x] `deploy/*.service` carry no `HALBERT_HOST=0.0.0.0`
- [x] Named routes behind `require_owner` — all of them are now, not just the five named
- [x] **Also found and closed:** `/docs`, `/redoc`, `/openapi.json` served a complete machine-readable
      map of all 334 routes to anyone. Off unless `HALBERT_DEV_DOCS=1`.
- [x] Browser handoff: single-use HMAC ticket → `/auth/enter` → `HttpOnly; SameSite=Strict` session
      cookie. Keeps a browser and `scripts/halbert-kiosk.service` working.
- [x] Tauri shell mints the token, passes it to the sidecar in the environment (not argv) and
      injects `window.__HALBERT_TOKEN__`; `installAuthFetch()` attaches it to backend requests only.
- [x] `tests/test_route_auth_census.py` — 6 tests, incl. the walk-depth guard that catches a census
      silently checking nothing
- [x] Frontend: 8 tests in `src/lib/apiBaseAuth.test.ts`, incl. "never sends the credential to a
      third party"
- [ ] Tauri audio socket per-connection token (`src-tauri/src/audio_capture.rs`) — **still open**
- [ ] `scripts/halbert-kiosk.service` updated to mint a ticket at start

### `[~]` SEC-2 · Command classification and execution containment — 11 findings (C1 H3 M6 L1)
- [x] `get_service_status` stops shell-interpolating a model-supplied argument — the whole module
      is argv now, there is no shell to inject into (`75e3f47c`)
- [x] **Credential reads gated** (not in the audit; `79dca611`). `read_file /etc/shadow` and
      `read_file ~/.ssh/id_ed25519` returned SAFE; `cat ~/.ssh/id_ed25519` returned LOW. The
      SENSITIVE_PATHS elevation only bumps one level and only MEDIUM→HIGH gates, so it never fired
      for a read. Filename-keyed, not directory-keyed, so `sshd_config` stays readable.
- [x] **Pager escape closed** (not in the audit; `79dca611`). `git log -1` auto-runs at MEDIUM,
      spawns a pager, and the pager executes `$GIT_PAGER` as a shell command. Verified running as
      uid 501 through the real `PTYSession`.
- [ ] **Deny-by-default classification — DESIGNED AND MEASURED, NOT LANDED.** The plan's
      `unknown → HIGH` takes the prompt rate on Halbert's own command repertoire from 3.1% to
      **82.8%**. The allowlist alternative converges to ~11%, but the proposed patch has five live
      defects. Referred to Fable — see `REVIEW-PACKET-12` §5.1 and `research/sec-2-3/`.
- [ ] Normalise (expand `~`, `$HOME`, relative) **before** the sensitive-path check
- [ ] `cwd` classified alongside the command
- [ ] `find … -exec` no longer SAFE; word boundary on the `ls|dir|find|locate` rule.
      **Coupled to the default:** 27 of 38 currently-SAFE argv commands (`lspci`, `lsof`,
      `findmnt`…) are SAFE *only* because the rule is a bare prefix match. Fixing the regex alone
      pushes them all into the default branch.
- [ ] Sandbox applied to the agent's own commands, not only the two HTTP routes.
      **See the seatbelt ruling first** — the proposed profile fails silently (`diskutil list`
      returns rc=0 and zero bytes), and the *current* one already blocks all network.
- [ ] `man -P`, `less`/`LESSOPEN` and other read-only binaries that take a program as an argument

### `[~]` SEC-3 · Path containment and the privileged write path — 17 findings (C2 H5 M8 L2)
- [x] Persona purge traversal closed — a persona is a name that cannot express a path, plus a
      resolved-containment check (`75e3f47c`, F7/F171)
- [x] `backup_id` traversal closed — pinned to the shape `create_backup` generates (`75e3f47c`, F28)
- [ ] **One containment primitive — PROPOSED, NOT LANDED.** `research/sec-2-3/containment.py`
      is good work but is not a drop-in: on macOS with `root="/"` it refuses `/etc/hosts` because
      `etc` is a symlink to `private/etc`, so it needs a root allowlist (a product decision — which
      roots may the editor open?). `ResolvedPath` cannot be threaded through `editor.py`, which uses
      the path as a *string* in six places. It breaks the 7 tests in `test_write_paths_guarded.py`.
      And `write_bytes` is `ftruncate(0)` then `write` — a crash mid-write on `sshd_config` leaves
      it empty. Needs the atomic-replace method first.
- [ ] `startswith('/')` gone from `editor.py` (`:348`, `:388`)
- [ ] `sudo -n tee` / `sudo -n cat` fallback deleted — on macOS these can never succeed anyway
      (no polkit, no NOPASSWD, no TTY)
- [ ] Shell helpers replaced by a typed broker; per-action polkit ids;
      `auth_admin_keep` only on the read-only diagnostic set (it is currently on all three,
      including write and exec, so one password unlocks a session of root writes)
- [ ] Editor backups stop writing privileged content into world-readable files
- [ ] Platform note verified on this machine: `O_TMPFILE`, `os.linkat` and `os.openat2` are all
      **absent**; `os.rename in os.supports_dir_fd` is **True**. The plan's stated
      `O_TMPFILE`+`linkat` primitive does not exist here.

### `[ ]` SEC-4 · One enforcing approval and autonomy gate; policy engine deleted — 17 findings (H4 M11 L2)
- [ ] Policy engine deleted (`SEC-D11`); `reach.*` grants become the per-tool policy
- [ ] Scheduler stops executing jobs the guardrail marked `approval_required`
- [ ] Safe-mode flag moves off a CWD-relative path
- [ ] Approval payload re-read at execution; approvals expire

### `[ ]` SEC-5 · The capability gate and the Lease — 10 findings (H1 M7 L2)
**`[!]` Blocked on `SEC-D10`** — bundle-identifier reconcile, needed before the ceiling table compiles.
- [ ] Capability (can) split from consent (may); typed denials; fail direction stated
- [ ] `Lease` object; capture/exec/egress primitives take one positionally
- [ ] Chokepoint lint + deny-all canary

### `[ ]` SEC-8 · Stop everything, and live indicators — 4 findings (M3 L1)
**Ships with SEC-5, never after.**
- [ ] One halt action; `halt.json` `0600`, atomic, flock-guarded, read in boot Phase 0
- [ ] Six doors: tray, every page, voice-at-ingress, hotkey, CLI, HA switch
- [ ] Indicators render from open leases, naming the target; `SIGKILL` test

### `[ ]` SEC-6 · Two-phase boot and first run — 6 findings (H1 M4 L1)
- [ ] Phase 0 starts nothing privileged; subsystems wait on consent
- [ ] The seven first-run screens; review screen; consent records not booleans

### `[~]` SEC-9 · Home Assistant governance — 8 findings (C2 H2 M4)
Independent of SEC-1 in code; reachable through SEC-1's door.
- [x] Unknown domain → confirm, never auto-execute (was Level 1 "act, log only")
- [x] Tiers keyed on domains Home Assistant actually has. `garage_door` and
      `water_valve` do not exist — HA uses `cover` and `valve` — so L2/L3 matched
      nothing while `cover` sat in L1 and opened the garage silently.
- [x] L3 now covers what cannot be undone from a chat message: `shell_command`,
      `python_script`, `hassio`, `homeassistant`, `automation`, `script`,
      `rest_command`, `command_line`, `recorder`, `backup`
- [x] Entity check moved where `data:` cannot route around it — `evaluate_call()`
      judges the union of `entity_id`, `data.entity_id` and `data.target.entity_id`,
      most-restrictive-wins. All three call sites (MCP, route, tool) switched.
- [x] `POST /api/home/voice/speak` takes a JSON body, not a query parameter
- [x] 11 new tests in `test_ha_governance_targets.py`, incl. one pinning the old
      permissive path so nobody "simplifies" `evaluate_call` back to `evaluate`
- [ ] Per-entity opt-in for L2 domains (the design's "T2 per-entity ○") — deferred
      to the SEC-5 consent model, which is where the grant record lives
- [ ] HA→Halbert direction: the component still relays any HA caller's text into a
      full agent turn (that half is SEC-12 + SEC-10)

---

## P1 — before the product is described publicly as secure (40 findings · 5 high)

- [ ] **SEC-7** · The consent ledger — 2 findings
- [ ] **SEC-10** · Speaker authority and the voice path — 5 findings (H1)
- [ ] **SEC-11** · The egress choke point — 11 findings (H1)
- [ ] **SEC-12** · Remote surfaces propose, never commit — 6 findings (H1)
- [ ] **SEC-14** · The self-modification fence and skills — 4 findings (H1)
- [ ] **SEC-15** · Prompt-injection containment — 6 findings (H1)
- [ ] **SEC-17** · Settings IA: lying controls deleted, missing ones shipped — 6 findings

## P2 — the "defensible to an outside reviewer" bar (28 findings · 9 high)

- [ ] **SEC-13** · Data at rest, erasure and export — 16 findings (H6)
- [ ] **SEC-16** · Packaging, signing and the install chain — 12 findings (H3)
- [ ] **SEC-20** · Threat model, honest documents, test gates — 0 primary, depends on all above
- [x] **SEC-21** · `:cloud` suffix bypassed the secure-model gate — **fixed 2026-09-08**; `is_local_model()` at five sites; APPLE-1 reconcile at boot. Filed as SEC-15 (collision); see `ISSUE-SEC-15-CLOUD-SUFFIX-BYPASSES-SECURE-GATE-2026-09-07.md`

## P3 — hardening (15 findings · 2 crit · 3 high)

- [ ] **SEC-18** · Windows: the empty ceiling — 9 findings (C2 H3).
      Priced P3 by risk (no Windows artifact exists), scheduled early by cost (~1 day).
- [ ] **SEC-19** · Sensor-input trust and retention hygiene — 6 findings

---

## Founder calls that block work

| Id | Question | Blocks |
|---|---|---|
| `SEC-D10` | Bundle identifier reconcile — `platforms.yml` vs `DECISIONS FDR-03` | **SEC-5, hard** |
| `C3-19` | Dashboard bearer token whenever bound off loopback — currently "ratify before remote-client work"; the shipped units already bind off loopback, so this is due now | SEC-1 |
| `SEC-D1` | Does the App Store channel ship at all? | SEC-5 ceiling, SEC-16 |
| `SEC-D2` | X11 screen capture — supported or refused? | SEC-5, SEC-17 |
| `SEC-D3` | Voiceprint retention position | SEC-13, SEC-20 |
| `SEC-D4` | Bystander policy | SEC-6, SEC-10, SEC-13 |
| `SEC-D5` | Does Windows remain a stated target? | SEC-18 |
| `SEC-D11` | Delete the policy engine, or repair it? | SEC-4 |

The remaining calls (`SEC-D6` haloysius-absent boot halt, `SEC-D7` profile naming, `SEC-D8`
`observe → suggest`, `SEC-D9` FDA/Accessibility, `SEC-D12` the deliberate fail-open) have defaults
recorded in §C of the plan and do not block the P0 train.
