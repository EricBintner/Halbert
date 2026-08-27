# Role-Scoped Config Harvesting — Design

2026-08-26 (rev. 2 — role taxonomy folded in)

## Goal

Reduce RAG noise by giving the agent narrow, subsystem-scoped context instead
of always searching the full corpus. A new **role axis** of SourcePrep scopes,
each named `<role>_admin`, bundles (a) live host config files for that
subsystem and (b) a small curated set of high-priority reference docs.

A broader `<role>_knowledge` tier (the full doc corpus per role) and an
adaptive "recently/commonly accessed" scope are explicitly **out of scope**
for this pass — this design covers the `_admin` tier only.

This is additive. The existing flat `host` scope (fed by
`config-registry.yml`'s blanket `/etc/**/*.conf` glob) and the platform doc
scopes (`knowledge_linux`, `knowledge_macos`, `knowledge_bsd`,
`knowledge_common`) are untouched.

## Why this is tractable

SourcePrep already has a working scope primitive — `ScopeRecord`,
`get_context(scope=)`, per-scope path registration via add/remove, per-scope
`pipeline_profile`, and (as of the in-flight uncommitted change to
`sourceprep_client.py`) a `scope_mode="hard"` isolation flag that hard-filters
rather than score-boosts. Nothing new is needed at the SourcePrep layer.

Halbert also already has the harvesting pipeline
(`halbert_core/halbert_core/config/`: `manifest.py`, `snapshot.py`,
`drift.py`, `watcher.py`, `edge_extractor.py`) from Phase 1/3. Role manifests
reuse it unchanged. This is config-and-wiring work, not new infrastructure.

**Baseline for how greenfield this is:** the discovery scanners collectively
know only ~28 distinct `/etc` paths, and `config-registry.yml`'s
`/etc/**/*.conf` glob structurally *misses* most of the highest-value files on
Linux — `fstab`, `crypttab`, `passwd`, `sudoers`, `exports`, `*.nmconnection`,
`*.network`, `*.rules`, `*.repo`, `*.list`. Nearly every role below is new
ground, not a re-packaging of existing knowledge.

## The role taxonomy

Names use the `DiscoveryType` value vocabulary
(`halbert_core/halbert_core/discovery/schema.py:21`) in **underscore form**,
so `id == display_name` and reconcile-by-name matches query-by-id — avoiding
the existing `knowledge-linux` / `knowledge_linux` hyphen/underscore split.

| Scope | Owns | Linux | macOS | Wave |
|---|---|---|---|---|
| `network_admin` | interfaces, DNS, routing, wireless, VPN, name resolution | rich | moderate | 1 |
| `service_admin` | what runs at boot/login and how it is supervised | thin (narrow, see below) | **rich** | 1 |
| `storage_admin` | mount intent, encryption, RAID/LVM/pool config, backup policy | rich | thin (autofs) | 1 |
| `security_admin` | sshd, sudo, PAM, MAC, firewall, hardening sysctls, audit | rich | moderate | 2 |
| `shell_admin` | login environment, PATH, shell rc, locale/time | rich | moderate | 2 |
| `package_admin` | repos, mirrors, pins, auto-update policy | rich | **none** | 2 |
| `boot_admin` | bootloader, initramfs, kernel cmdline | rich | **none** | 3 |
| `sharing_admin` | samba/NFS/avahi/rsyncd exports | moderate | thin | 3 |

Stop at eight. The ceiling is not the daemon (scope count is cheap) but
`scripts/corpus_quality_gate.py`'s hand-written `SCOPED_QUERIES` suite, at
roughly 4–5 entries per scope.

### Platform asymmetry — do not tidy this away

The two platforms genuinely do not have the same roles.

- **Both, file-backed:** `network_admin`, `security_admin`, `shell_admin`,
  `service_admin`.
- **Linux-only:** `package_admin`, `boot_admin` (macOS `com.apple.Boot.plist`
  holds one empty `Kernel Flags` key), and scheduling (macOS has no
  `/etc/crontab` and no `/etc/periodic` — scheduling on macOS *is* launchd).
- **Inverted:** `service_admin` is macOS's richest role and Linux's thinnest.
- **File-rich one side, thin the other:** `storage_admin` (Linux rich; macOS
  has no `fstab`, `/etc/synthetic.conf` **does not exist on a stock host**,
  and APFS container layout is command-output-only via `diskutil apfs list` —
  but autofs is real mount intent that lives in files, so `/etc/auto_master`,
  `/etc/auto_home` and `/etc/autofs.conf` make the role **file-backed on
  Darwin**, verified 3 matches on a stock host).
- **File-rich one side, docs-only the other:** `sharing_admin`, logging.

A docs-only role scope is legitimate — it stages curated
`knowledge/<platform>/` files and no host config. It is not, however, a free
choice for a *wave-one* role: staging nothing produces an empty scope, and
under `scope_mode="hard"` an empty mask excludes everything rather than
narrowing. A role that matches even one real file must be file-backed. That
is why `storage_admin` is file-backed on Darwin.

### Deferred (name reserved, no scope yet)

- `backup_admin` — Linux content is thin and folds under `storage_admin`;
  macOS `com.apple.TimeMachine.plist` is binary *and* TCC-denied. Promote when
  borgmatic/restic/sanoid are actually detected on the host.
- `kernel_admin` — real Linux policy files (`modprobe.d`, `modules-load.d`,
  `udev/rules.d`, `sysctl.d`) but they are almost entirely *aliases* claimed
  by other roles. Promote if alias-only membership proves insufficient in gate
  testing.
- `container_admin`, `logging_admin`, `scheduling_admin`, `users_admin`,
  `printing_admin` — conditional-install, vestigial, or absorbed. Promotion
  trigger: a registered scanner **plus** a `_DOMAIN_KEYWORDS` entry, so
  `scope_for_query` can actually route to it.

### Dropped

- **`display_admin` — dropped from the pilot.** It is the only candidate with
  zero backing on every axis: not a `DiscoveryType` (only `DESKTOP` exists),
  no registered scanner on either platform, no `_DOMAIN_KEYWORDS` key so query
  routing can never reach it, no dashboard page, no doc directory. On macOS
  its backing store is UUID-keyed binary blobs that stay semantically opaque
  even after conversion. Its Linux content (`xorg.conf.d`, `monitors.xml`,
  `hyprland.conf`) is per-user desktop preference, not system administration.
- **`audio`, `power`, `hardware`** — binary/opaque on macOS, ~70%
  command-only on Linux, no editable intent surface. Hardware *inventory*
  stays a scanner concern inside the flat `host` scope.
- **`virtualization`** — on macOS this is `~/.docker`, `~/.colima`: per-user
  developer tooling, not OS administration. Belongs to a future dev-tooling
  tier, not a `*_admin` OS role.

### Degenerate platforms

NixOS and Gentoo — both detected by `utils/platform.py` — collapse the entire
taxonomy into one declarative file tree (`/etc/nixos/**`, `/etc/portage/**`).
On those hosts, degrade to a single `declarative_config` scope plus curated
docs rather than producing eight near-empty scopes.

## Membership: primary + alias

Scopes are **masks over one shared index**, so registering a path into two
scopes costs zero extra indexing and zero query time. Forcing single ownership
would guarantee wrong answers on genuinely multi-role files. So each file has
a *primary* role and zero or more *alias* roles.

**Governing principle: a file belongs to the role that answers the question a
user would ask about it, not the mechanism that reads it.**

**Corollary: mechanism directories are never assigned by glob.**
`/etc/systemd/system/`, `/etc/default/`, and `/etc/sysconfig/` are
role-agnostic *containers* — grub, tlp, snapper, nfs, iptables, and locale all
live in `/etc/default/`. A glob there poisons every scope. Assign file by
file.

| File | Primary | Alias |
|---|---|---|
| `/etc/default/grub` | `boot_admin` | `security_admin`, `storage_admin` (worst collision on Linux — one line per role) |
| `/etc/fstab`, `/etc/crypttab` | `storage_admin` | `boot_admin` |
| `/etc/systemd/system/*.mount`, `*.timer`, `*.network` | the subsystem, by unit name | `service_admin` |
| `/etc/systemd/*.conf` family | per-file (`resolved`→network, `journald`→logging, `logind`→power+users) | — |
| `sshd_config` | `security_admin` | `network_admin` |
| firewall (nft/ufw/firewalld/iptables) | **`security_admin`** — revised from rev. 1, which put these in network | `network_admin` |
| `/etc/sysctl.d/*`, `/etc/modprobe.d/*`, `/etc/udev/rules.d/*` | `kernel_admin`; until it ships → `security_admin`, `security_admin`, `storage_admin` | `network_admin` |
| `/etc/nsswitch.conf`, `/etc/pam.d/*`, `/etc/passwd` | `users_admin`; until it ships → `security_admin` | `network_admin` |
| `/etc/exports`, `nfs.conf` | `sharing_admin` | `storage_admin` |
| `/etc/environment`, `/etc/profile.d/*` | `shell_admin` | — |
| auto-upgrade configs | `package_admin` | `security_admin` |
| `/etc/nixos/**`, `/etc/portage/**` | single `declarative_config` scope | — |

Because every systemd unit routes to its subsystem first, **`service_admin` on
Linux is deliberately narrow**: `/etc/systemd/{system,user}.conf`,
`/etc/init.d/*`, `/etc/rc.local`, `/etc/xinetd.d/*`, `/etc/tmpfiles.d/*`,
OpenRC `/etc/conf.d/*` + `/etc/runlevels/*` (Gentoo), plus only those units no
other role claims.

## Blocking prerequisites

These are required before **any** role scope ships. Items 1–5 fix a live
secret-leak risk; item 6 is required specifically because plists are macOS's
primary harvestable format.

**The disconnect (items 1–3):** `config/snapshot.py` redacts secrets via
`ingestion/redaction.py::redact_text()` before writing to
`data/config/raw/<hash>.txt` — but that output is never read by anything else.
It is orphaned, used only for local drift detection. The path that actually
reaches SourcePrep is different: `config/watcher.py`'s debounced
`create_sourceprep_reindex_callback()` → `SourcePrepSetup.apply()` →
`_stage_host_tree()` → `register_host_project.py::_stage_config_files()`,
which does a raw `shutil.copy2()` **directly from live `/etc/...` paths**
with **no redaction at all** (only whole-file excludes for
`shadow`/`ssl`/`letsencrypt`). Verified: no `redact` reference exists anywhere
in that file.

> **Status (2026-08-27):** the paragraph above describes the state *before*
> commit `0cb99ad`, and is kept as the diagnosis that motivated the work. The
> leak is closed. Item 3 below prescribed a fix that was **not** the one that
> shipped — it has been corrected in place; read it, not this paragraph, for
> what the code now does.

1. **Redaction regex.** `TOKEN_RE` is
   `(?i)(api|secret|token|key|password)[=:]\S+` (`redaction.py:8`). It misses
   NetworkManager WiFi passwords (`psk=<password>` — "psk" isn't a keyword)
   and WireGuard keys (`PrivateKey = <base64>` — `[=:]\S+` allows no
   whitespace, and standard WireGuard formatting has spaces). Add `psk` to the
   alternation and allow optional whitespace around the separator.
2. **Parser drop-on-error.** `config/parser.py::_parse_ini_like` uses
   `configparser` with the default `strict=True`. A repeated key (common in
   systemd `Environment=`/`ExecStartPre=` drop-ins) raises
   `DuplicateOptionError`; a missing `[Section]` header (common in
   NetworkManager dispatcher scripts and bare `KEY=value` files) raises
   `MissingSectionHeaderError`. Neither is caught locally, and because parsing
   and raw-text writing share one try block in `snapshot.py`, **the entire
   file is dropped, not degraded**. Catch both and fall back to
   `kind:"text"`.
3. **Redact staging.** `_stage_config_files()` must stop copying live OS
   paths verbatim. Required regardless of role scopes; a hard prerequisite for
   `network_admin` specifically.

   **What shipped — corrected 2026-08-27.** This item originally read "consume
   `data/config/raw/<hash>.txt` instead of copying live OS paths", and that is
   not what was built. `register_host_project.py::_stage_one_file()` reads the
   **live path** through `config/parser.py::parse()` and redacts the result
   with `redact_text()` on its way to the staging tree. It never opens the
   snapshot. Both designs close the leak; the wrong one is written down here
   on the security-critical path, where a reviewer checking the code against
   this doc would look for a snapshot read that does not exist.

   Inline won on **ordering**. Consuming `raw/<hash>.txt` makes staging
   depend on `snapshot()` having run first: with no snapshot, staging
   produces nothing; with a snapshot older than the file on disk, staging
   ships stale content — and "stale" on this path means a credential that was
   supposed to have been rotated out of the index is still in it, silently,
   because the staged tree looks populated either way. Reading the live file
   has no such state to get wrong. Going through the parser rather than
   reading bytes is what carries the plist conversion, which is what makes a
   binary plist greppable and redactable at all.

   The snapshot's own sinks are redacted in their own right — `raw/` since
   this merge, `canon/` since the follow-up — so neither sink is the weaker
   guarantee and nothing depends on which one a future reader reaches for.
4. **Run it once, end-to-end, for real.** `data/config/` output directories
   are currently empty — `snapshot()` has never executed on this machine.
   Confirm by hand that no secret pattern survives into staged output.
5. **Integration test.** No test chains snapshot → redact → stage →
   scope-query. Add one with a fixture `.nmconnection` (`psk=` line) and
   WireGuard `.conf` (`PrivateKey = ` with the space), asserting neither
   secret survives verbatim.
6. **Plist support in the parser.** `config/parser.py:24` opens *every* file
   with `errors="replace"` and line 38 hashes that mangled text. There is **no
   `.plist` branch anywhere** in the dispatcher, so every binary plist is
   silently corrupted and then drift-detected against its own corruption. Fix
   with stdlib `plistlib.load()` on an `"rb"` handle — no subprocess, ~10
   lines. (Measured alternative for reference: `plutil -convert xml1` is ~7ms
   per file, but `plistlib` handles both binary and XML natively.)

### macOS redaction, additionally

`TOKEN_RE` is Linux-oriented and has no hostname/username/realm pass.
`com.apple.smb.server.plist` contains the machine's NetBIOS name, the owner's
real name, and an LKDC Kerberos realm hash. macOS needs those rules added.

**`~/Library/Preferences` must be strict-allowlist, never a glob** — it holds
~9,600 plists including recent-document lists, search history, account
identifiers, and per-app tokens. Harvesting it wholesale would be a serious
privacy incident. `~/Library/LaunchAgents` and `~/.zshrc` are safe and worth
taking.

`/Library/Managed Preferences` (MDM), when present, **overrides all other
config on the machine** and should rank above host files rather than equal to
them. Treat as an optional include.

### IP address policy — decided 2026-08-26

**Non-routable addresses are exempt from redaction; public addresses are still
redacted.**

Exempt: loopback (`127.0.0.0/8`, `::1`), RFC1918 private
(`10/8`, `172.16/12`, `192.168/16`), link-local (`169.254/16`, `fe80::/10`),
the unspecified address `0.0.0.0`, and the broadcast address
`255.255.255.255`.

**Why.** Verified on real staged output, blanket IPv4 redaction gutted
`/etc/hosts` — `127.0.0.1 localhost` became `<ip> localhost`,
`255.255.255.255 broadcasthost` became `<ip>`, and `#ListenAddress 0.0.0.0`
became `<ip>`. Halbert administers the machine it runs on, so its own
loopback and private addressing is core operational data, not a secret it
needs protecting from itself. A public address can identify the host or a
remote peer to an outside observer — harvested config reaches an LLM that may
be a cloud model — so those stay redacted.

The blanket rule was also inconsistent in practice: `::1 localhost` survived
because `IPV4_RE`'s `\b` cannot anchor before a leading colon, so the policy
was already de facto partial.

**Separate defect, not a policy question:** `IPV6_RE` matches any
colon-separated numeric triple, so sshd's `MaxStartups 10:30:100` became
`MaxStartups <ip6>`, and it ate a timestamp inside an RCS ID. Those are not
addresses. The pattern needs to require hex-group structure that a bare
decimal triple cannot satisfy.

**Related false positives** found in the same pass, to fix via the existing
`_NON_SECRET_KEYS` mechanism rather than by weakening keyword matching:
`SHAuthorizationRight: system.preferences` (the `authorization` substring
firing on a *right name*) and `SecureSocketWithKey: DISPLAY` (the `key`
substring firing on an *env-var name*). Both redact a value that is a
well-known identifier, not a credential.

## Wave 1 manifests

Each role gets a manifest following the existing `Manifest` schema
(`include`/`exclude`) that `config/manifest.py` already parses:
`halbert_core/config/scopes/{network,service,storage}.yml`. They ship as
package data rather than from the repo's `config/` tree: a repo-relative path
does not exist under a wheel, where role staging then failed and left the
registered scopes pointing at directories nothing had created.

Two implementation notes not present in the existing global manifest:

- `Manifest.parsers` (the per-manifest `parsers:` dict) is **dead code** —
  loaded by `manifest.py` but never consulted in `parser.py`. Format dispatch
  is purely extension-based. Do not design per-role parsing around it.
- `Manifest.iter_paths()` derives each glob's root via
  `os.path.dirname(pattern)` and walks with `os.walk`, which does **not**
  expand `~`. Several paths below are per-user. Either write them as expanded
  absolute paths, or add an `os.path.expanduser()` pass over include/exclude
  at load time. One or the other is required.

### `network_admin`

**Linux** — reused from `NetworkScanner` (`network.py`): `*.nmconnection`,
`/etc/systemd/network/*.network` + `*.netdev`, `/etc/netplan/*.yaml`,
`/etc/network/interfaces`. New: `/etc/hosts`, `/etc/hostname`,
`/etc/resolv.conf`, `/etc/systemd/resolved.conf`, `/etc/nsswitch.conf`
(alias), `/etc/NetworkManager/NetworkManager.conf` + `conf.d/*`,
`/etc/NetworkManager/dispatcher.d/*`, `/etc/systemd/network/*.link`,
`/etc/wpa_supplicant/*.conf`, `/etc/iwd/main.conf`, `/etc/netctl/*` (Arch),
`/etc/dnsmasq.conf`, `/etc/openvpn/**`. Distro divergence rev. 1 missed:
RHEL≤8 `/etc/sysconfig/network-scripts/ifcfg-*` (gone in RHEL9 → NM keyfiles)
and SUSE's differently-shaped `/etc/sysconfig/network/ifcfg-*` +
`/etc/sysconfig/network/routes`.

**macOS — file-backed, correcting rev. 1.**
`/Library/Preferences/SystemConfiguration/preferences.plist` is **XML,
world-readable, 26 KB** (verified on a live host) and holds the complete
`networksetup` backing store: `CurrentSet`, every NetworkService UUID,
`IPv4/ConfigMethod`, DNS, service order. Also `/etc/hosts`, `/etc/pf.conf` +
`/etc/pf.anchors/*`, `/etc/resolv.conf` (generated — informational),
`/etc/networks`, `/etc/nfs.conf`, `com.apple.Boot.plist`.

Note `com.apple.airport.preferences.plist` (the WiFi PSK store) returns
"Operation not permitted" even to a read — being unreadable is a *feature*
here, given prerequisite 1.

Firewall rule files are **not** here — they moved to `security_admin`, aliased
back into this scope.

### `service_admin`

**macOS (rich)** — `/Library/LaunchDaemons` (~19),
`/Library/LaunchAgents` (~20), `~/Library/LaunchAgents` (~9). Measured with
`file(1)`: **100% XML, zero binary.** This is the real "what runs on this
machine and why" surface, third-party included.
`/System/Library/LaunchDaemons` adds ~422 more, all XML — Apple stock, so
inventory rather than host config: exclude, or tier separately.

**Linux (narrow, by design)** — `/etc/systemd/system.conf`,
`/etc/systemd/user.conf`, `/etc/init.d/*`, `/etc/rc.local`,
`/etc/xinetd.d/*`, `/etc/tmpfiles.d/*.conf`, OpenRC `/etc/conf.d/*` +
`/etc/runlevels/*`, plus only units no other role claims. Every unit routes to
its subsystem first (`.mount`→storage, `.timer`→scheduling,
`.network`→network).

### `storage_admin`

**Linux** — `/etc/fstab` (the single largest gap: never read anywhere in the
codebase today), `/etc/crypttab`, `/etc/mdadm/mdadm.conf` (Debian/SUSE) vs
`/etc/mdadm.conf` (RHEL/Arch), `/etc/lvm/lvm.conf` +
`/etc/lvm/{profile,archive,backup}/*`, `/etc/multipath.conf`,
`/etc/zfs/zpool.cache` + `/etc/zfs/zed.d/*` + `/etc/zfs/vdev_id.conf`,
`/etc/systemd/system/*.{mount,automount,swap}`, `/etc/snapper/configs/*` +
`/etc/default/snapper`, `/etc/sysconfig/btrfsmaintenance` (SUSE). Backup
policy folds in here: `/etc/borgmatic.d/*.yaml`, `/etc/restic/*`,
`/etc/rsnapshot.conf`, `/etc/timeshift/timeshift.json`,
`/etc/sanoid/sanoid.conf`, `/etc/btrbk/btrbk.conf`.

**macOS — thin, not absent.** There is no `fstab`; `/etc/synthetic.conf` does
not exist on a stock machine (it appears only if an admin creates one), so
rev. 1's single macOS storage entry would match nothing on a default host; and
APFS container layout is correctly command-output-only (`diskutil apfs list`).
None of that is harvestable.

Autofs is, and it is genuine mount intent that lives in files:
`/etc/auto_master`, `/etc/auto_home` and `/etc/autofs.conf` all exist on a
stock host (verified: 3 matches). The role is therefore **file-backed on
Darwin** — `roles.py` lists `Darwin` in `file_backed_platforms` and
`storage.yml` includes all three. An earlier revision called this docs-only
and gated Darwin out, which left the scope empty; under `scope_mode="hard"` an
empty mask excludes everything rather than narrowing, so that produced a
broken scope rather than a thin one.

*(Out of scope but noted: there is no LVM discovery at all today, live or
file-based — `pvs`/`vgs`/`lvs` are unreferenced. That's a `StorageScanner`
gap, not a harvesting gap.)*

## Waves 2 and 3 — path sketches

Full manifests to be authored per wave; captured here so the research isn't lost.

- **`security_admin`** — Linux: `sshd_config` + `sshd_config.d/*`,
  `/etc/sudoers` + `sudoers.d/*`, `/etc/security/{limits.conf,limits.d/*,
  pwquality.conf,faillock.conf,access.conf}`, `/etc/sysctl.conf` +
  `/etc/sysctl.d/*`, `/etc/login.defs`, `/etc/audit/auditd.conf` +
  `rules.d/*.rules`, firewall four ways (`/etc/nftables.conf`,
  `/etc/iptables/rules.v{4,6}` Debian, `/etc/sysconfig/iptables` RHEL,
  `/etc/firewalld/**/*.xml`, `/etc/ufw/*`), MAC split
  (`/etc/selinux/**` RHEL vs `/etc/apparmor.d/**` Debian/SUSE vs neither on
  Arch), `/etc/crypto-policies/config`, `/etc/fail2ban/**`. macOS:
  `/etc/pam.d/*` (~25 files, all ASCII), `sshd_config` +
  `sshd_config.d/100-macos.conf`, `/etc/ssh/ssh_config`, `/etc/sudoers` +
  `sudoers.d/`, `/etc/ftpusers`. Note `com.apple.alf.plist` **no longer
  exists** on macOS 26.x — firewall state is `socketfilterfw` only.
  **Hard-exclude** `/etc/shadow`, `/etc/gshadow`, `/etc/sssd/sssd.conf`.
- **`shell_admin`** — Linux: `/etc/profile`, `/etc/profile.d/*.sh`,
  `/etc/environment`, `/etc/shells`, `/etc/inputrc`, `/etc/skel/.*`,
  `/etc/bash.bashrc` (Debian/Arch) vs `/etc/bashrc` (RHEL/SUSE),
  `/etc/zsh/*`, `/etc/fish/config.fish`; per-user is where the value is
  (`~/.bashrc`, `~/.zshrc`, `~/.profile`, `~/.ssh/config`, `~/.gitconfig`,
  `~/.tmux.conf`). Locale/time fold in: `/etc/locale.conf` vs
  `/etc/default/locale`, `/etc/localtime`, `/etc/timezone`,
  `/etc/vconsole.conf`, `/etc/systemd/timesyncd.conf`, `/etc/chrony.conf`
  (RHEL/Arch) vs `/etc/chrony/chrony.conf` (Debian/SUSE). macOS: `/etc/paths`,
  `/etc/paths.d/*`, `/etc/zshrc`, `/etc/zprofile`, `/etc/bashrc`,
  `/etc/profile`, `/etc/manpaths` + `manpaths.d/`, `~/.zshrc` — all plain
  text, small, high signal.
- **`package_admin` (Linux-only)** — apt (`sources.list`,
  `sources.list.d/*.{list,sources}`, `apt.conf.d/*`, `preferences.d/*`),
  pacman (`pacman.conf`, `pacman.d/mirrorlist`, `pacman.d/hooks/*.hook`,
  `makepkg.conf`), dnf (`dnf.conf`, `/etc/yum.repos.d/*.repo`), zypper
  (`/etc/zypp/**`), plus `/etc/flatpak/remotes.d/*`. **Exclude**
  `/etc/apt/auth.conf.d/**` (credentials). *No macOS entry*: Homebrew is
  effectively command-only — there is no `Brewfile` (that's generated output
  of `brew bundle dump`), `Library/Taps` is empty on modern JSON-API-backed
  Homebrew, `HOMEBREW_*` settings live in shell rc files (already covered by
  `shell_admin`), and `/opt/homebrew/etc` holds *formula-installed* configs
  belonging to other roles, not Homebrew configuration.
- **`boot_admin` (Linux-only)** — `/etc/default/grub` + `grub.d/*.cfg`,
  `/etc/grub.d/*`; generated config diverges three ways
  (`/boot/grub/grub.cfg` Debian/Arch vs `/boot/grub2/grub.cfg` + `grubenv`
  RHEL/SUSE vs `/boot/efi/EFI/<distro>/grub.cfg`); systemd-boot
  `/boot/loader/loader.conf` + `entries/*.conf`, `/etc/kernel/cmdline`.
  Initramfs splits three ways: `/etc/mkinitcpio.conf` + `mkinitcpio.d/*.preset`
  (Arch) vs `/etc/dracut.conf` + `dracut.conf.d/*` (RHEL/SUSE) vs
  `/etc/initramfs-tools/**` (Debian).
- **`sharing_admin`** — Linux: `/etc/samba/smb.conf`,
  `/var/lib/samba/usershares/*`, `/etc/exports` + `exports.d/*`,
  `/etc/nfs.conf` + `nfs.conf.d/*`, `/etc/idmapd.conf`,
  `/etc/avahi/avahi-daemon.conf` + `services/*.service`, `/etc/rsyncd.conf`,
  `/etc/vsftpd.conf` (Debian) vs `/etc/vsftpd/vsftpd.conf` (RHEL). macOS
  (thin): `com.apple.smb.server.plist`, `/etc/nfs.conf`.

### High-priority docs (all roles)

A small, hand-curated, hardcoded list per role pointing at existing files
under `knowledge/{linux,macos,bsd,common}/`. Deliberately small (a handful per
role) so `_admin` stays cheap and high-signal, distinct from the deferred
`_knowledge` tier. Stage only the running host's platform docs.

## Composition model

**One scope per role, platform pre-collapsed at staging.**

Confirmed in `sourceprep_client.py:114`: `scope` is `Optional[str]` — a single
scope, not a list. Cross-product scopes (`network_admin_macos`) are rejected:
Halbert runs on exactly one host, so staging *already* collapses the platform
axis — a Linux box never stages `com.apple.Boot.plist`. A
`network_admin_macos` scope on a Linux host would be permanently empty, and
under `scope_mode="hard"` an empty mask excludes everything.

**The platform axis stays only on the `knowledge_*` tier**, where
cross-platform lookup is genuinely wanted.

Use `pipeline_profile: system_config` per role scope, and keep each docs
bundle small — otherwise `profile_for_path` logs a per-file warning wherever a
bundle overlaps `knowledge_linux`'s paths.

## Staging and scope registration

Each role manifest's matched files stage into `sourceprep/host/<role>/`, a new
subdirectory under the existing `host/` staging root — alongside, not
replacing, the existing flat `config-registry.yml`-driven staging. Alias
membership is expressed by registering the same staged path into the alias
scope, not by staging a second copy.

Each `sourceprep/host/<role>/` plus its curated docs bundle registers as a
scope via the existing add/remove-paths API, with `scope_mode="hard"`.

One `ConfigWatcher` per role manifest — the existing class already accepts an
arbitrary `manifest_path`, so no changes needed there.

## KNOWN LIMITATION — role trees duplicate the flat host tree

**This contradicts the primary+alias model stated above, and the model is the
part that is currently wrong.** Recorded here rather than quietly fixed,
because both candidate fixes change staging topology and cannot be verified
without a built index.

That section claims *"scopes are masks over one shared index, so registering a
path into two scopes costs zero extra indexing."* True of scope registration —
but wave 1 does not register one file into two scopes. `stage_role_tree()`
writes a **second physical copy** into `sourceprep/host/<role>/`, while the
flat `host` scope's `paths: ["host"]` and the project's
`include_globs: ["host/**"]` already cover it.

Measured on the development host: the flat tree stages 42 files; **40 of them
stage again** under role trees (39 launchd plists + `/etc/hosts`). Total goes
42 → 99 with 40 duplicated.

Consequences:

1. Overlapping files are indexed twice.
2. `host`-scoped queries can return the same content from two different paths.
3. **The sharp one:** `remap_edges_for_unified_root` maps config edges
   `file:/etc/…` → `file:host/etc/…` only. Edges therefore attach solely to
   the flat copy, so `trace_expand: true` expands nothing inside a role
   scope — role scopes silently lose the trace-graph expansion that the
   platform scopes get.

**Two candidate fixes, both design-level:**

- **(a) Masks over the flat tree.** Stage once into `host/` as today, and
  register each role scope with the concrete `host/`-relative paths its
  manifest matched. This is the honest reading of the primary+alias model and
  makes aliasing free as claimed. Cost: scope `paths` become *derived from
  host state* rather than static template entries, which changes the template
  model and `_reconcile_scopes`.
- **(b) Prune overlaps from the flat list.** Remove from
  `_LINUX_CONFIG_PATHS`/`_MACOS_CONFIG_PATHS` anything a role manifest claims,
  so each file stages exactly once. The `host` scope still covers everything
  because role directories live *under* `host/`. Smaller change, but the edge
  remap must become role-aware or consequence (3) persists.

(b) is the smaller change; (a) is the one that matches the design. Decide with
a working index in front of you, not from the code.

**Also latent:** a role subdirectory name could collide with a real absolute
path — `/storage/...` on Linux would stage to `host/storage/...`, the same
place `storage_admin` writes. Not reachable from the current path lists.

## Explicitly out of scope

- The `<role>_knowledge` tier — a separate, later design.
- An adaptive "recently/commonly accessed" scope with a frequency threshold.
- Query-time auto-routing that picks a role scope from message content. For
  this pass, role scopes are explicitly invoked by name. Revisit once both
  tiers exist and routing has two axes to combine.
- A Rust rewrite of the harvesting pipeline. `watchdog` is event-driven
  (inotify/FSEvents), and each role watches a few dozen files at most once
  scoped this narrowly. (Caveat: unverified in practice — the pipeline has
  never run end-to-end here.)
- Fixing pre-existing scanner duplication (identical cron-dir lists in
  `backup.py`/`scheduled.py`/`system_profile.py`; `system_profile.py` being a
  third independent reimplementation of network/storage/security discovery).
  Real debt, unrelated to this design.

## Known gaps this design does not close

**Zero macOS scanners are registered.** `discovery/engine.py::
_register_default_scanners` registers Backup, Service, Storage, Network,
Security, Sharing, Flatpak, Snap, AppImage — **none** of the
`discovery/scanners/macos/*` classes (`LaunchdScanner`, `MacNetworkScanner`,
etc.) are imported or registered. macOS role scopes would ship with harvested
config but no live discovery behind them. Not a blocker for harvesting, but it
means the macOS story is half-built.

Relatedly, `macos/__init__.py`'s docstring advertises `MacDisplayScanner`,
`MacWifiScanner`, `MacAudioScanner` and others that **do not exist as files**.
The docstring is aspirational; treat it as stale.

## Unverified claims to confirm before shipping

SourcePrep's source is not reachable from this machine (only its staged data
directory), so two reported server-side behaviors could not be verified. Both
are serious if true:

1. **Fail-open on unknown scope name.** Reportedly an unrecognized scope
   yields `mask=None` and falls back to the **global union with HTTP 200** — a
   typo'd scope name would silently search the entire corpus, the exact
   inverse of narrowing. If confirmed, must fail closed before any role scope
   ships.
2. **`to_remove` always empty.** `sourceprep_setup.py:334` computes
   `to_remove` from `rec.get("paths")`, sourced from `_list_scopes()`
   (`GET /projects/{pid}/scopes`). If that endpoint returns summaries without
   `paths`, `current_paths` is always empty — so `to_remove` is always empty
   and scope masks only ever grow (and `to_add` re-sends everything each
   time). Latent today; materially harmful with eight churning role scopes.
   Fix by fetching `GET /scopes/{sid}` per scope.

## Testing

- Unit tests for the redaction and parser fixes: a `.nmconnection` with
  `psk=`, a WireGuard `.conf` with `PrivateKey = ` (with the space), an
  ini-like file with a duplicate key, one with no section header, a binary
  plist, an XML plist.
- The integration test from prerequisite 5 (snapshot → redact → stage →
  scope-query, asserting no secret survives).
- Scope-isolation cases for each new role scope, following
  `scripts/corpus_quality_gate.py`'s existing scoped-query pattern — e.g. a
  `storage_admin` query returns `/etc/fstab`-sourced chunks and no
  `network_admin` content. Budget ~4–5 queries per scope.

## Implementation order

1. Blocking prerequisites 1–6, plus confirming the two unverified SourcePrep
   behaviors.
2. Wave 1 manifests: `network_admin`, `service_admin`, `storage_admin`
   (network first — most reuse, and the P0 fixes are network-secret-driven
   anyway; `service_admin` second because it validates the asymmetric-content
   design on macOS's richest role rather than deferring that discovery).
3. Curated docs bundle per wave-1 role.
4. Register the three scopes, wire three watchers, verify with the
   scope-isolation suite.
5. Wave 2 (`security_admin`, `shell_admin`, `package_admin`), then wave 3
   (`boot_admin`, `sharing_admin`).
