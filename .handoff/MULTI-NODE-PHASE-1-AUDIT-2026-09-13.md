# Multi-Node Phase 1 — Progress Audit (2026-09-13)

What is committed where, what merges cleanly, and what remains.

## Branch state

`feat/multi-node-phase-1` (worktree `.claude/worktrees/multi-node-phase-1`),
base `76312c25`, four commits, working tree clean:

| Commit | Content |
|--------|---------|
| `3c5f0216` | **Task 1 — TLS peer transport.** `federation/tls.py` (cert generation, fingerprints, pinned `requests.Session`, TLS listener with lifecycle integration), `tls_pin` on `PeerCredential`, pairing advertises fingerprint+port, satellite `pairing_client`, pinned sessions in peer provider / compute router / conversation store / threads. `cryptography` guarded per the subtractive contract. 24 focused tests + live smoke (pinned HTTPS pairing, wrong-pin rejection, 401 unauthenticated). |
| `7a2533f6` | **Task 2 — Streaming redaction.** `SlidingWindowRedactor` in `security/result_redaction.py` — emits only line-boundary text with no open construct (partial line, unclosed PEM, deferred secret-key values, `|`/`>` block scalars, plist secret keys/flags held until their extent is decided) using the redaction module's own predicates; `feed+flush == redact_string(whole)` across the test corpus. `compute_endpoint` `stream: true` → SSE `StreamingResponse` slicing the completed response through the window (upstream broker→model streaming still unbuilt). 137 tests. |
| `ca121afa` | **Task 3 — Resilient peer conversation store.** `agents/resilient_peer_store.py`: write-through local `SqliteConversationStore` mirror + `staged_invocation` FIFO queue + `local_peer_id_map` for local↔peer id translation; daemon flush thread with exponential backoff (cap 300 s) and dead-lettering after 5 attempts; `redact_message` never staged. Wired in `threads.py::_create_conversation_store` with fallback to the raw proxy. 15 tests. |
| `b43e9d37` | **Task 4 — Two-node lifecycle test** (`tests/federation/test_two_node_lifecycle.py`): one process, two nodes — cert minting, pair→approve→verify with pin propagation into both `peers.json`, streamed redacted compute, online write-through, simulated host sleep staging, wake + ordered flush + id resolution. Plus the three DECISIONS.md ratification rows (`SEC-TLS`, `REPL-CACHE`, `COMP-STREAM`, all `pending`). |

Total: 522 federation/redaction/store tests passing on the branch
(`arch -arm64 ./wt_pytest.py`); the only failure in the touched suites is
`test_get_thread_manager_uses_default_db`, which **also fails on main** —
this machine's `being.yml` sets `canonical_thread_url`, so the local-store
default the test asserts never applies. Pre-existing environment issue,
not a regression.

## Committed on main since the branch point

`main` moved to `d8f3b466` — the **warm-standby replication + State Vault**
merge, a *different* multi-node resilience stream:

- `halbert_core/halbert_core/replica/` — snapshot push, liveness, promotion
  ("satellite becomes canonical"), fallback, replica store.
- `halbert_core/halbert_core/backup/` — vault manifest, encryption, restore
  engine; routes + CLI + onboarding "restore from backup" UI.
- Security review work (all merged; `fix/sec-review-auth-mounts` tip
  `fd3f5fd5` is an ancestor of main — nothing outstanding): trust_anchor
  role (`c92f30cb`), approvals router auth (`dadb86e3`), unknown-peer-role
  warnings (`14967fd3`), production mount auth tests.

Earlier worry — uncommitted trust-anchor edits in the main checkout — is
resolved: they are committed and merged. The main worktree's only
untracked files are `AGENTS.md.backup-2026-09-10`,
`CLAUDE.md.backup-2026-09-10`, and `web/`.

## Merge surface

`git merge-tree` against current main: **four files with real conflicts**,
all mechanical same-region additions, no semantic overlap:

- `agents/threads.py` — main's replica wiring and the resilient-store wrap
  both touched `_create_conversation_store`.
- `dashboard/app.py` — TLS listener startup/shutdown vs replica startup.
- `dashboard/routes/peers.py` — TLS advertisement fields vs trust-anchor/
  replica route additions.
- `federation/peers_config.py` — `tls_pin`/`tls_enabled` fields vs new
  credential fields.

Everything else (replica/, backup/, most tests) merges cleanly.
`tests/test_thread_manager_store_injection.py` changed on main and should
be re-checked after resolving `threads.py`.

## Design question the merge surfaces (founder-visible)

Two resilience models now coexist:

- **main**: warm-standby *replication* — the satellite keeps a replica
  pushed from the canonical host, with promotion to canonical on failure.
- **this branch**: satellite-side *cache + write staging* — the satellite
  writes locally when the host is unreachable and replays in order.

They are complementary (replication covers read availability + host loss;
staging covers satellite-initiated writes during outage), but the merge
should say so explicitly rather than leaving two unconnected stories.
DAG branch grafting remains deferred either way (dispatch §7).

## Remaining work

1. Resolve the four conflict files; re-run `wt_pytest.py` for the touched
   suites plus `test_thread_manager_store_injection.py`.
2. Get the three DECISIONS rows ratified (SEC-TLS, REPL-CACHE, COMP-STREAM).
3. Deferred per dispatch §7 — upstream model→endpoint streaming deltas
   (the endpoint slices a completed response today), DAG grafting,
   PAKE, Root CA, SWIM, CRDT replication.
4. Residual documented on `SlidingWindowRedactor`: a registered multi-line
   secret that is not PEM-shaped can straddle a line cut.
