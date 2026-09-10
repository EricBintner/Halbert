# Runtime and SQLite pinning — investigate and land

**Dispatchable.** Self-contained. Everything below marked *measured* was run on
this machine on 2026-09-10; everything marked *claim* still needs checking.

**Founder directive that frames the whole thing:** *"we can't be asking users to
install specific python versions, we just need to manage our own environment."*
No recommendation that ends in "install interpreter X" is an acceptable answer.

---

## 1. Why this exists

Halbert stores conversations and state in SQLite through Python's stdlib
`sqlite3`. Which SQLite you get is a property of **how the interpreter was
built**, not of the Python version — so today it is decided by whatever is
first on `$PATH` on whatever machine ran the build.

Two separate problems fall out, and they have one fix:

1. **Version drift.** The shipped SQLite is arbitrary.
2. **A code-execution weakness in the shipped app** (§3). The signed `.app`
   currently launches an interpreter from a user-writable path.

---

## 2. Measured: the interpreter landscape on this machine

**This section is a diagnosis of what is wrong today. It is not a menu — no
row in the tables below is a recommendation.** The answer is §4. A reader who
skims §2 and picks the row with the best SQLite has picked an x86_64-only
interpreter and reproduced the exact mistake this section exists to document.
That misread has now happened twice: once by a previous session, and once by a
reader of *this* doc on 2026-09-10, who came away believing the packet
recommended the Intel Homebrew. It does not, and never did.

Apple **M1 Ultra, arm64**. Both Homebrews are installed and **the Intel one
wins on PATH**:

| Prefix | Architecture | PATH position |
|---|---|---|
| `/usr/local` | **Intel (x86_64, Rosetta)** | **12 — wins** |
| `/opt/homebrew` | arm64 native | 38 |

So a bare `brew` here is the **Intel** one. Always call
`/opt/homebrew/bin/brew` by absolute path.

**The interpreters, with the column that matters:**

| Path | Python | SQLite | Arch |
|---|---|---|---|
| project `.venv` | 3.10.9 | **3.39.4** | universal2 (starts x86_64) |
| `/usr/local/bin/python3.11` | 3.11.14 | 3.53.4 | **x86_64 ONLY** (Intel brew) |
| `/usr/local/bin/python3.12` | 3.12.8 | 3.45.3 | universal2 (python.org) |
| `/opt/homebrew/bin/python3.11` | 3.11.15 | 3.51.2 | arm64 |
| `/opt/homebrew/bin/python3.14` | 3.14.3 | 3.51.2 | arm64 |
| `/usr/bin/python3` | 3.9.6 | 3.51.0 | universal2 (Apple) |
| **`python3` on PATH** | 3.10.9 | 3.39.4 | arm64 — `~/.local/bin/python3` |

**Read that table carefully.** The only interpreter with a SQLite outside the
WAL-reset-vulnerable range is `x86_64`-only. The arm64-native ones are all
vulnerable. **A version table without an architecture column is not a decision
input on this machine** — a previous session recommended
`/usr/local/bin/python3.11` on exactly that mistake.

Note also that the *newer* Homebrew 3.11.15 has an *older* SQLite than the
Intel 3.11.14. Python minor version predicts nothing.

**Six live interpreter sources** (measured 2026-09-10 — corrected up from the
five this doc first claimed): two Homebrews, python.org frameworks, a
`~/.local/bin` shim, miniconda, and a **pyenv shim** at
`~/.pyenv/shims/python3` (`~/.pyenv/versions` holds `anaconda3-2022.05`).
Resolved in an order nobody chose.

**Two `uv` installs, both stale** (measured 2026-09-10):

| Path | Version | Source | PATH |
|---|---|---|---|
| `~/miniconda3/bin/uv` | `0.8.17` (Sep 2025) | miniconda | **wins** |
| `/usr/local/bin/uv` | `0.6.6` (Mar 2025) | Intel brew | shadowed |

*Claim to verify:* those vintages resolve python-build-standalone with SQLite
**3.50.4** (still vulnerable) where current uv resolves **3.53.1**. If true,
"just use uv" without pinning uv itself lands back inside the range. Note the
sharper form of the problem: there is no single "the uv on this machine", so
"whichever uv ran the build" is itself an unpinned input. §5 trap 5 is not
hypothetical here.

### Out of scope for this packet: removing the Intel Homebrew

**Founder ruling, 2026-09-10: removing the Intel Homebrew from this machine is
machine hygiene, not this project's work. Do not fold it into this packet.**
Recorded here only so a future session does not rediscover the question and
wander into it.

Measured 2026-09-10: 172 Intel formulae, 34 top-level installs, 23 with no arm
counterpart — and **13 of those currently win on PATH**, all x86_64 under
Rosetta: `git`, `go`, `just`, `yq`, `yarn`, `redis-server`, `xcodegen`,
`meson`, `iperf3`, `git-lfs`, `cargo-deny`, `ios-deploy`, `ruby`. (`git` would
fall back to Apple's `/usr/bin/git` 2.50.1; `node` is already nvm arm64
v22.19.0, so Intel's node is dead weight.) It is a real migration, not a
delete — which is why it is someone's afternoon, not a line item here.

**The load-bearing fact for *this* packet:** nothing in the macOS build path
depends on `/usr/local`. Every `/usr/local` reference in the repo is a Linux
polkit installer, a CUDA path, a Linux scanner, or RAG-scraper doc text
(measured). So §4 is neither blocked by the Intel brew nor waiting on its
removal — and once the app ships its own interpreter, the product stops caring
which Homebrews exist at all. That independence is the point: **the fix must
not be "the host had the right brew."**

---

## 3. The security finding — verify first, it may reprioritise everything

`halbert_core/halbert_core/dashboard/frontend/src-tauri/binaries/halbert-api-aarch64-apple-darwin`
is **2,231 bytes of bash**, and `tauri.conf.json` bundles it as the
`externalBin` sidecar. So this is what the signed, notarized `.app` executes.
Its interpreter resolution (measured, read the file):

```bash
REPO_ROOT="$HOME/.local/share/halbert/repo"     # user-writable
PYTHON="$REPO_ROOT/.venv/bin/python"            # user-writable
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3)"              # $PATH-dependent
fi
exec "$PYTHON" -m uvicorn halbert_core.dashboard.app:app
```

It also honours `$HALBERT_REPO_ROOT` from the environment.

**Consequence:** anything that can write that path is executed *by the signed
app*, inheriting every TCC grant Halbert holds — screen recording, microphone,
camera, any Full Disk Access. It defeats the point of signing the bundle.

**Severity, stated honestly:** requires an attacker who can already write to
`$HOME`. Not remote code execution. But it converts "wrote one file" into
"holds all of Halbert's system permissions."

`documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md` already
names this the weakest cell in the matrix (see :939, :1029, :1167) and
prescribes the fix. **Confirm that doc's prescription still matches before
designing a new one.**

This also blocks other work: the Secure-Enclave re-auth design
(`A11-G12`) makes the signed app bundle the trust anchor, and you cannot
anchor trust in a bundle whose first act is to exec a user-writable
interpreter. **This is a prerequisite, not an adjacent nicety.**

---

## 4. The recommendation to validate (do not assume it)

From a research pass whose measurements were run on this machine but which
**did not carry an architecture column** — so re-verify on arm64:

**Pin the interpreter, not the SQLite library.** Build the `halbert-api`
sidecar with a uv-managed python-build-standalone (PBS) CPython, freeze with
PyInstaller `--onedir`, ship it inside the `.app`.

*Claims to verify:*
- PBS statically inlines SQLite into the extension (so `brew upgrade` cannot
  move it). Reported check: `_sqlite3.__file__` raises `AttributeError`
  because it is a builtin, vs Homebrew's `.so` linking
  `/opt/homebrew/opt/sqlite/lib/libsqlite3.dylib`.
- Current uv resolves `cpython-3.12.x` and `cpython-3.13.x` **both at SQLite
  3.53.1**, with FTS5/FTS4/JSON1/RTREE/GEOPOLY all present.
- PyInstaller **inherits the build interpreter's SQLite**: a frozen probe
  reported 3.53.1 with no `libsqlite3.dylib` in `otool -L`.
- **Verify all of the above on an arm64 PBS build specifically.**

*Root cause to fix:* `scripts/build-macos.sh:237` is a bare
`python3 -m venv .venv`. Neither `.python-version` nor `uv.lock` exists
(measured — both absent).

*Migration cost, measured:* 39 production `sqlite3.connect` sites, 15
`row_factory = sqlite3.Row`, and **zero** uses of `detect_types`,
`PARSE_DECLTYPES`, `register_adapter`, `register_converter`,
`enable_load_extension` or `create_function`. Under this option, application
code changes: **none**.

---

## 5. Traps — each cost someone something

1. **`pysqlite3-binary` ships no macOS wheels.** Every release back to 0.5.3
   is `manylinux2014_x86_64` only. On macOS it silently source-builds against
   the machine's SQLite, reintroducing the exact problem. The obvious pick,
   and a dead end. (Plain `pysqlite3` — no `-binary` — *does* have arm64
   wheels, but ships 3.51.1, below the 3.51.3 floor.)
2. **`apsw` is deliberately not DB-API 2.0.** Best SQLite (3.53.4), wrong
   shape: no `connect()`, no `Row`, no `row_factory`, no `commit()`. Every
   storage module and its tests would need rewriting.
3. **PyOxidizer is abandoned** — last commit 2024-12-24. Its author's work
   went into python-build-standalone, which is what uv uses.
4. **`--onefile` is the wrong end state.** Extracts to a temp dir on every
   launch; library validation and notarization are harder. But note
   `build-macos.sh:280` copies an `--onedir` *directory* into `externalBin`,
   and **Tauri's `externalBin` handles single files only** — an `--onedir`
   sidecar must move to `bundle.resources` and be launched by path.
5. **uv alone is not a pin.** Without a committed `.python-version`,
   `uv.lock`, *and* a pinned uv version, it still floats.
6. **PBS quirk:** `_sysconfigdata_*.py` embeds absolute build paths. uv
   corrects these on install; hand-rolled extraction does not.
7. **Do not recommend an interpreter by path.** Picking a good one is a fix
   that lasts until someone's PATH differs. Pin explicitly and assert.

---

## 6. What to deliver

1. **Verify §3** and say plainly whether it is as described.
2. **Verify §4's claims on arm64**, with the architecture of every binary
   stated.
3. **A build-time assertion** that fails loudly in CI, not quietly at a user's
   disk. At minimum: `sqlite3.sqlite_version_info >= (3, 51, 3)` and
   `platform.machine() == "arm64"`.
4. **A decision on the x86_64 story.** PyInstaller cannot cross-build. Do we
   ship arm64 only, need a second build host, or go universal2?
5. **The pin itself**: `.python-version`, `uv.lock`, a pinned uv, and
   `build-macos.sh` changed off bare `python3`.
6. **Ratify or replace `ENV-01`** in `DECISIONS.md`, and update the
   `FD-11 (revised)` row — it currently says the SQLite bump is a packaging
   decision, which is this packet.

## 7. Context you should read first

- `DECISIONS.md` — the `FD-11 (revised)` row (2026-09-10) has the corrected
  WAL-reset facts: it is a data race, **not** a crash bug; SQLite's own
  telemetry puts occurrence at or below cosmic-ray rate; the DELETE-journal
  mitigation is **rejected** and upstream's advice is simply to ship a newer
  SQLite. **Do not re-litigate that** — the packaging fix is the whole
  remediation.
- `halbert_core/halbert_core/agents/conversation_sqlite.py:34-110` — the
  version predicate and why the patched builds are exact values, not ranges.
- `documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md` — the
  sidecar prescription.
- Memory: `mac-dual-homebrew-intel-wins-path`, `halbert-venv-arch-arm64-fix`.

**Run tests as:** `cd halbert_core && arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/ -q -p no:randomly`
(the `arch -arm64` prefix is required — the venv is universal2 and starts
x86_64). Baseline on `main` at the time of writing: **8421 passed, 15
skipped, 6 xfailed**.
