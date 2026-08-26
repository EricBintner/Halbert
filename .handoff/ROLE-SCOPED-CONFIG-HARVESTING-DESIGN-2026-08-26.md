# Role-Scoped Config Harvesting — Design

2026-08-26

## Goal

Reduce RAG noise by giving the agent narrow, subsystem-scoped context instead
of always searching the full corpus. Three initial roles: **network**,
**display**, **storage**. For each role, an `<role>-admin` SourcePrep scope
bundles (a) live host config files relevant to that subsystem and (b) a small
hand-curated set of high-priority reference docs. A broader `<role>-knowledge`
tier (the full doc corpus per role) and an adaptive "recently/commonly
accessed" scope are explicitly **out of scope** for this pass — this design
covers `-admin` only.

This is additive: the existing flat `host` scope (fed by
`config-registry.yml`'s blanket `/etc/**/*.conf` glob) and the platform scopes
(`knowledge_linux`, `knowledge_macos`, `knowledge_bsd`, `knowledge_common`)
are untouched. Role scopes are new, narrower siblings, not replacements.

## Why this is tractable

SourcePrep already has a working scope primitive — `ScopeRecord`,
`get_context(scope=)`, per-scope path registration via add/remove, and (as of
the in-flight uncommitted change to `sourceprep_client.py`) a
`scope_mode="hard"` isolation flag that hard-filters instead of just
score-boosting. Nothing new needs to be invented at the SourcePrep layer —
this design only needs to (1) decide what content feeds each new scope and
(2) make sure that content reaches SourcePrep safely.

Halbert also already has a full config-harvesting pipeline
(`halbert_core/halbert_core/config/`: `manifest.py`, `snapshot.py`,
`drift.py`, `watcher.py`, `edge_extractor.py`) built in Phase 1/3. The role
manifests in this design reuse that machinery unchanged — this is
config-and-wiring work, not new harvesting infrastructure.

## Blocking prerequisite — fix before any role scope ships

Research turned up a live secret-leak risk in the pipeline that currently
reaches SourcePrep. **This must be fixed first**, independent of the role-scope
work, because network-admin (one of the three MVP scopes) would otherwise ship
plaintext WiFi passwords and VPN keys into a searchable scope on day one.

**The disconnect:** `config/snapshot.py` redacts secrets via
`ingestion/redaction.py::redact_text()` before writing to
`data/config/raw/<hash>.txt`. But that output is never read by anything else —
it is orphaned, used only for local drift detection. The code path that
actually reaches SourcePrep is different: `config/watcher.py`'s debounced
`create_sourceprep_reindex_callback()` calls
`sourceprep_setup.py::SourcePrepSetup.apply()`, which calls
`_stage_host_tree()`, which calls `register_host_project.py`'s
`_stage_config_files()` — and that function does a raw `shutil.copy2()`
**directly from live `/etc/...` paths**, with **no redaction at all** (only
whole-file excludes for `shadow`/`ssl`/`letsencrypt`).

**Required fixes, in order:**

1. **Redaction regex.** `ingestion/redaction.py`'s `TOKEN_RE` currently matches
   `(api|secret|token|key|password)[=:]\S+` with no whitespace tolerance.
   Concretely: NetworkManager `.nmconnection` files store WiFi passwords as
   `psk=<password>` — "psk" isn't in the keyword list, so it doesn't match.
   WireGuard `.conf` files store `PrivateKey = <base64>` — standard WireGuard
   formatting has spaces around `=`, which the regex's `[=:]\S+` (no
   whitespace) doesn't match either. Fix: add `psk` (and `psk-` variants) to
   the keyword alternation, and allow optional whitespace around the
   separator.
2. **Parser drop-on-error.** `config/parser.py::_parse_ini_like` uses
   `configparser.ConfigParser(interpolation=None)` with the library default
   `strict=True`. A config snippet with a repeated key (common in systemd
   `Environment=`/`ExecStartPre=` drop-ins) raises `DuplicateOptionError`; a
   snippet with no leading `[Section]` header (common in NetworkManager
   dispatcher scripts and bare `KEY=value` drop-ins) raises
   `MissingSectionHeaderError`. Neither is caught inside `_parse_ini_like`, so
   it propagates to `snapshot.py`'s outer `try/except` — and because parsing
   and raw-text writing share that one try block, **the entire file is
   dropped, not degraded**. Both new role manifests (network's dispatcher
   scripts, display's `xorg.conf.d` snippets) will hit this routinely. Fix:
   catch both exceptions in `_parse_ini_like` and fall back to storing the
   file as opaque `kind:"text"` (same fallback `_parse_text` already uses for
   unrecognized extensions), so parse failure never means data loss.
3. **Rewire staging onto redacted output.** `_stage_config_files()` must stop
   reading live OS paths directly and instead consume
   `config/snapshot.py`'s redacted `data/config/raw/<hash>.txt` output (after
   fixes 1–2 land). This is the actual fix for the leak: today's bypass exists
   independent of any role-scope work, so this is required regardless, but it
   is a hard prerequisite for shipping network-admin specifically.
4. **Run it for real, once, end-to-end.** As of this writing, `data/config/`
   output directories are completely empty — `snapshot()` has never actually
   executed on this machine. Before any role scope ships, run the full chain
   once (manifest → snapshot → redact → stage → scope register → query) and
   confirm by hand that no secret pattern survives into staged output.
5. **Add the missing integration test.** No existing test chains
   snapshot → redact → stage → scope-query. Add one, using a fixture
   directory containing a fake `.nmconnection` (with a `psk=` line) and a
   fake WireGuard `.conf` (with a `PrivateKey = ` line), asserting the staged
   output contains neither secret verbatim.

Everything below (the three manifests, scope registration) assumes this
prerequisite is done first.

## Per-role manifests

Each role gets its own manifest file, following the existing `Manifest`
schema (`include`/`exclude` globs) that `config/manifest.py` already parses
and `config/snapshot.py`/`config/watcher.py` already consume unchanged:
`config/scopes/network.yml`, `config/scopes/display.yml`,
`config/scopes/storage.yml`.

Two implementation notes discovered during research, not present in the
existing single global manifest:

- `Manifest.parsers` (the per-manifest `parsers:` dict) is dead code — loaded
  by `manifest.py` but never consulted anywhere in `parser.py`. Role manifests
  should not rely on it; format dispatch is (and will remain) purely
  extension-based in `parser.py`.
- `Manifest.iter_paths()` derives each glob's root via
  `os.path.dirname(pattern)` and walks it with `os.walk`, which does **not**
  expand a literal `~`. Several new display-role paths are per-user
  (`~/.config/monitors.xml`, `~/.local/share/kscreen/*.json`,
  `~/.config/sway/config`, `~/.config/hypr/hyprland.conf`). These manifests
  must use the expanded absolute home path (or `manifest.py` needs a small
  `os.path.expanduser()` pass over include/exclude patterns at load time —
  whichever the implementer prefers, but one of the two is required for the
  display manifest to actually watch anything under the home directory).

### network (`config/scopes/network.yml`)

Reused from `NetworkScanner`'s already-known paths (`network.py`), so this
list is not new knowledge, just relocated into a manifest:

- `/etc/NetworkManager/system-connections/*.nmconnection`
- `/etc/systemd/network/*.network`, `*.netdev`
- `/etc/netplan/*.yaml`
- `/etc/network/interfaces`

New, from the cross-platform gap sweep (all real, static, on-disk config —
none of these are command-output-only):

- `/etc/resolv.conf`
- `/etc/systemd/resolved.conf`
- `/etc/wpa_supplicant/*.conf`
- `/etc/iwd/main.conf`
- `/etc/netctl/*` (Arch/Manjaro/EndeavourOS)
- `/etc/NetworkManager/dispatcher.d/*`
- `/etc/ufw/*.rules`, `/etc/firewalld/zones/*.xml`, `/etc/nftables.conf`

**macOS:** no entries. `MacNetworkScanner` is entirely command-derived
(`networksetup`, `scutil`, `ifconfig`, `airport`) — the backing
`SystemConfiguration` plists are binary and exclusively managed through those
commands. Network-admin content for macOS hosts comes only from the
high-priority-docs bundle (below), not from a manifest.

Exclude (secrets, already excluded project-wide, kept here for clarity):
none beyond what `config-registry.yml` already excludes — the P0 redaction
fix is what protects these paths, not a manifest-level exclude, since the
whole point is to harvest them.

### display (`config/scopes/display.yml`)

No reuse — `display.py` is entirely env-var/command-derived
(`xrandr`, `lspci`, `gsettings`), and its one hardcoded path
(`/sys/kernel/debug/vgaswitcheroo/switch`) is live sysfs state, not static
config.

New, from the cross-platform gap sweep:

- `/etc/X11/xorg.conf.d/*.conf`
- `~/.config/monitors.xml` (GNOME per-user monitor layout)
- `~/.local/share/kscreen/*.json` (KDE)
- `~/.config/sway/config`
- `~/.config/hypr/hyprland.conf`
- `/etc/prime-discrete` (Ubuntu hybrid-graphics persisted choice; minor)

**macOS:** no manifest entries, and this is structural, not a gap to close
later. There is no `macos/display.py` scanner (a docstring in
`macos/__init__.py` claims one exists; it does not — confirmed no such file
is imported anywhere), and macOS display configuration has no user-editable
config file at all — the backing store is a binary per-display plist under
`ByHost` preferences, legitimately read only via `system_profiler` or
`displayplacer`. macOS display-admin is **curated docs only**.

### storage (`config/scopes/storage.yml`)

No reuse — `storage.py` is entirely command/sysfs-derived (`lsblk`,
`smartctl`, `/proc/mdstat`, `btrfs`/`zfs`/`bcache` commands).

New, in priority order:

- `/etc/fstab` — the single biggest gap found; never read anywhere in the
  current codebase despite being the most sysadmin-relevant storage config
  that exists (persistent mounts, options, `subvol=`/`compress=`).
- `/etc/crypttab`
- `/etc/mdadm/mdadm.conf`
- `/etc/lvm/lvm.conf`
- `/etc/zfs/zpool.cache`, `/etc/zfs/zed.d/*`

**macOS:** `/etc/synthetic.conf` only (custom root-level mount points),
low priority. Everything else on macOS (`diskutil`, APFS containers) is
correctly command-output-only — APFS has no user-editable config file, so
there is nothing else to harvest there.

*(Side note, explicitly not this design's job: there is no LVM discovery at
all today, live or file-based — `pvs`/`vgs`/`lvs` are unreferenced anywhere.
That's a `StorageScanner` gap, not a config-harvesting gap, and is out of
scope here.)*

### High-priority docs (all three roles)

A small, hand-curated, hardcoded list per role — not derived automatically —
pointing at existing files under `knowledge/{linux,macos,bsd,common}/`. Kept
deliberately small (a handful of files per role, not a subtree) so the
`-admin` scope stays cheap and high-signal, distinct from the deferred
`-knowledge` tier. Exact file selection is a curation task for whoever
implements this, not specified further here.

## Staging and scope registration

Each role manifest's matched files are staged into
`sourceprep/host/<role>/` (a new subdirectory under the existing `host/`
staging root, alongside — not replacing — whatever the existing flat
`config-registry.yml`-driven staging already covers). Each
`sourceprep/host/<role>/` directory plus its curated docs bundle is
registered as its own SourcePrep scope, named `network-admin`,
`display-admin`, `storage-admin`, using the existing scope
add/remove-paths API (no new SourcePrep-side capability required) and the
in-flight `scope_mode="hard"` isolation flag, the same way the platform
scopes already enforce host/knowledge_linux/knowledge_macos isolation.

One `ConfigWatcher` instance per role manifest (the existing class already
supports being pointed at an arbitrary `manifest_path`; no changes needed
there), each wired to `create_sourceprep_reindex_callback()` for its own
scope's re-stage-and-rebuild.

## Explicitly out of scope for this pass

- The `<role>-knowledge` tier (full doc corpus per role, e.g.
  `network-knowledge`) — a separate, later design.
- An adaptive "recently/commonly accessed" scope with a frequency threshold.
- Query-time auto-routing that picks a role scope from message content
  (parallel to the existing platform-axis `scope_for_query` routing). For
  this MVP, role scopes are explicitly invoked (by scope name), not
  auto-selected. Worth revisiting once both tiers exist and routing has two
  axes to combine (platform + role), not one.
- A Rust rewrite of any part of the harvesting pipeline. The existing
  Python + `watchdog` approach is event-driven (inotify/FSEvents under the
  hood, not polling) and is watching, per role, a few dozen files at most
  once scoped this narrowly — there is no performance case for a rewrite
  here. (Caveat: this has not been load-tested in practice, since the
  pipeline has never run end-to-end on this machine — see the blocking
  prerequisite above.)
- Fixing the pre-existing duplication across scanners (identical cron-dir
  lists copy-pasted into `backup.py`/`scheduled.py`/`system_profile.py`;
  `system_profile.py` being a third independent reimplementation of
  network/storage/security discovery). Real technical debt, unrelated to
  this design, flagged here only so it isn't confused for something this
  work touches.

## Testing

- Unit tests for the two redaction/parser fixes (concrete fixtures: a
  `.nmconnection` with `psk=`, a WireGuard `.conf` with `PrivateKey = `
  including the space, an ini-like file with a duplicate key, one with no
  section header).
- The integration test described in the blocking prerequisite
  (snapshot → redact → stage → scope-query, asserting no secret survives).
- Scope-isolation test cases for the three new role scopes, following the
  existing pattern in `scripts/corpus_quality_gate.py`'s scoped-query suite
  (host/knowledge_linux/knowledge_macos/knowledge_bsd/knowledge_common) —
  add role-scoped query/expected-source assertions the same way, confirming
  e.g. a storage-admin query returns `/etc/fstab`-sourced chunks and not
  network- or display-admin content.

## Implementation order

1. Blocking prerequisite (redaction fix, parser fix, staging rewire, one
   real end-to-end run, integration test).
2. `config/scopes/network.yml`, `display.yml`, `storage.yml` with the path
   lists above (network first — it has the most reuse and the clearest
   payoff given the P0 fixes are network-secret-driven anyway).
3. Curate the high-priority-docs list per role.
4. Register the three scopes, wire the three watchers, verify with the
   scope-isolation test suite.
