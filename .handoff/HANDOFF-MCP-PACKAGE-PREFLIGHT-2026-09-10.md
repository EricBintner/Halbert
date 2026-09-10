# MCP server package preflight (FD-10) — BUILT 2026-09-10

**Status:** built. `halbert_core/mcp/package_preflight.py`, gated at the launch
point in `MCPClient._ensure`, 75 tests in
`halbert_core/tests/test_mcp_package_preflight.py`. The dispatch brief is kept
below verbatim; what landed, and the eight defaults it landed on, is recorded in
[§ What landed](#what-landed) at the end and in `DECISIONS.md` row `FD-10`
(built).

**The review landed 2026-09-10** — see [§ Plan update](#plan-update) at the
end. Six of the defaults were researched afterwards (measurements in
`.handoff/FABLE-HANDOFF-MCP-PREFLIGHT-PLAN-UPDATE-2026-09-10.md`); all six
calls were accepted, R1 and R2 amended, **none implemented yet**. The policy
table and § The line between absent and unobservable below are rewritten to
the rulings and marked † where they run ahead of the code.

*Original status, kept for the record:* not built. Verified 2026-09-10 by grep
over `halbert_core/`: the only `preflight` matches are CORS preflight in
`mcp/server.py:1652,1704`, and there is no OSV, advisory or
package-vulnerability call anywhere in the tree.

**Not urgent, and here is the honest reason:** there is no `mcp_config.yml` on
this host (`~/.config/halbert/` holds `being.yml`, `models.yml`,
`preferences.yml`, `personas/`, the GPU cache — nothing else). No MCP server is
configured, so this guards a surface that currently has nothing on it. Build it
before the first third-party server is added, not after.

## What already exists, so you do not rebuild it

`halbert_core/mcp/entry_guard.py` — `validate_server_entry(name, entry)` runs at
config parse time and refuses a server entry whose command matches:

- a shell interpreter taking an inline script (`sh -c`, `python -c`, `pwsh
  -Command`, …) — "an MCP server is a program with a protocol; a shell with an
  inline script is a payload with a launcher";
- a fetch piped into something that runs it, in either order;
- raw egress helpers (no MCP server needs one to speak its protocol);
- writes to surfaces that survive a restart;
- base64-into-interpreter.

That is a **static scan of the config entry**. It says nothing about what the
package the entry launches actually contains — which is the gap FD-10 names.

Also relevant: `mcp/config.py` `register_server_secrets` registers bearer tokens
into the redaction registry, and `mcp/client.py` `CHILD_ENV_ALLOWLIST` /
`child_env()` mean a child server sees an allowlisted environment rather than
the daemon's.

## The task

An **opt-in** preflight that runs before a server is launched for the first time
(and on a version change), resolves what the entry would actually install, and
checks it against a vulnerability/advisory source.

1. **Resolve the package identity** from the entry. `npx -y @scope/pkg@1.2.3`,
   `uvx pkg`, `python -m mod`, a bare path — each needs its own small resolver,
   and an entry whose identity cannot be resolved is a REFUSAL to preflight, not
   a pass. Say which it was.
2. **Query the advisory source.** OSV (`https://api.osv.dev/v1/query`) takes
   `{"package": {"name": ..., "ecosystem": "npm"|"PyPI"}, "version": ...}`. No
   API key. Cache by `(ecosystem, name, version)` with a TTL and a **negative**
   cache, so a repeated launch is not a repeated request.
3. **Decide, and let the operator decide too.** Default posture: refuse on a
   CRITICAL or HIGH advisory, warn-and-launch below that, and refuse on
   "could not tell" only if the operator turned strict mode on. The three-way
   split matters — absent tooling proceeds, *unobservable* tooling refuses with
   the uncertainty named. That rule is already recorded for the scheduler and
   the discovery scanners; this is the same rule.
4. **Opt-in.** Off by default (FD-10 says opt-in). It is a network call on a
   local-first machine, so it must be a thing the operator switched on. Put the
   switch beside the other operator switches, in the shape `vision_config.yml`
   and the new `skills_config.yml` established — under the data directory, read
   on every call, cached on the file's own `(mtime_ns, size)` signature.
5. **Never block the daemon's start.** A preflight that cannot reach the network
   must not stop Halbert coming up. Refuse the SERVER, log the reason, carry on.

## Tests to write

- an entry resolving to a package with a known-HIGH advisory is refused, and the
  refusal names the advisory id;
- an entry whose package identity cannot be resolved is refused with
  `unresolvable`, and the message says so rather than implying a clean scan;
- a network failure refuses that one server and does not raise into daemon start;
- the negative cache means two launches make one request;
- with the switch off, nothing is queried at all — assert on the HTTP seam, not
  on a log line;
- strict mode turns "could not tell" from warn into refuse.

## Constraints

- **Halbert's MCP client is a cloud pipeline.** Do not send anything but the
  package coordinates: name, ecosystem, version. Not the entry, not the env, not
  the command line — those carry paths and sometimes tokens.
- Keep it out of `mcp/client.py`'s transport. This belongs beside
  `entry_guard.py`, at config/launch time, as a second gate with its own name.
- The entry guard's refusals and this one are different findings and should read
  differently: one is "this entry is not a server", the other is "this server's
  package has a known problem".

## Where the decision is recorded

`DECISIONS.md`, row `FD-8`/`FD-10` (2026-09-09): "The opt-in OSV malware
preflight (`FD-10`) is recorded and **not** built." When this lands, that row
changes and the founder ratifies it.


---

<a id="what-landed"></a>
## What landed

### The module

`halbert_core/halbert_core/mcp/package_preflight.py`, beside `entry_guard.py`,
with its own name. Pure resolution, one network seam, no import-time I/O.

* `resolve_package(command, args)` — pure, no I/O. Resolvers for `npx`/`bunx`/
  `npm exec`/`pnpm dlx`, `uvx`/`uv tool run`, `pipx run`, and `python`. Handles
  `--package=`/`-p`, `--from=`/`--from`, `--spec`, the `--` separator, and
  scoped names (the `@` in `@scope/pkg` is not the version separator). An
  unknown `-`-prefixed token is treated as boolean; if that guess is wrong the
  token picked fails its ecosystem's name grammar and the answer is
  `unresolvable`, never a confidently wrong query.
* `check_server(server, *, config=None, query=None)` — the gate. **Never
  raises**: every failure mode, including a bug in the module itself, comes back
  as a `PreflightResult`.
* `cvss_v3_base_score(vector)` and `severity_of(vuln)` — OSV carries the CVSS
  *vector*, not the score, so without a local scorer "refuse on HIGH" would
  degrade to "severity unknown" on most real advisories. v3.1 Appendix A
  rounding, verified against the specification's worked examples.

### The gate's placement

`MCPClient._ensure`, immediately before `build_transport` — so it runs on a
first launch and on every config-signature change, and a signature change is
what a version bump in the entry *is*. Out of the transports entirely, as the
brief required. `run_package_preflight` owns three things the module does not:
it runs the synchronous `requests` call on a worker thread, bounds it by wall
clock with the same margin `HTTPTransport._exchange` uses, and treats a failure
to even *run* the check as the switch being off rather than as a refusal of
every server — the gate's OFF state is the shipped one, and a typo in its config
file must not take the MCP surface down.

A refusal is `MCPPreflightRefused`, a direct `MCPClientError` subclass and
deliberately **not** in the `MCPConnectionError` family: nothing was launched
and nothing was contacted, so "not connected" would be the wrong thing to tell a
caller. `connect()` already collects `MCPClientError` per server, so one refused
server never stops the daemon coming up — asserted by a test that boots two
servers and watches the good one come up.

### The switch

`mcp_preflight_config.yml` under the data directory, in the
`vision_config.yml` / `skills_config.yml` shape, cached on the file's own
`(mtime_ns, size)`:

```yaml
enabled: false          # opt-in; nothing is resolved or queried while off
strict: false           # refuse anything not positively cleared
timeout_seconds: 6.0
cache_ttl_seconds: 21600
```

A malformed file leaves the gate off. The endpoint is a module constant and
**not** a config key: an operator-settable endpoint would turn this switch into
a way to point Halbert's only MCP-side egress at an arbitrary host.

**Why the CONFIG directory and not the data directory (R3, implemented).** It
was measured, not chosen for tidiness. Halbert's own write classifier rates a
`write_file` to the data directory MEDIUM — no confirmation — so a gate whose
switch lived there could be turned off by the agent itself without asking; the
same write to the config directory rates HIGH. A test asserts that HIGH against
the real classifier, so the property cannot rot. The two files the brief named
as the shape disagree about the directory (`vision_config.yml` is in the config
directory, `skills_config.yml` in the data directory); `vision_config.yml` is
the right sibling, because it is a gate and the other is a preference list.

*A related hole is filed separately and is NOT this module's:* on macOS
`platform.get_data_dir()` and `paths.data_dir()` resolve to different places, so
the classifier's data-directory protection currently covers a nearly empty
directory while the real store — `state_ledger.db`, `skills_config.yml` — sits
unprotected at MEDIUM.

### The policy, as built

| outcome | default | `strict: true` |
|---|---|---|
| no package (a path, a local script, a URL, `python -m mod` †) | proceed | proceed |
| no advisory | proceed | proceed |
| advisory, HIGH or CRITICAL | REFUSE | REFUSE |
| a malware record (`MAL-`) | REFUSE | REFUSE |
| advisory, below HIGH | warn, proceed | REFUSE |
| advisory, severity unknown | warn, proceed | REFUSE |
| launcher outside npm/PyPI | note, proceed | REFUSE |
| package named, no version † | warn, proceed — REFUSE on a `MAL-` record or an open-range HIGH/CRITICAL | REFUSE |
| package not identifiable | REFUSE | REFUSE |
| source unreachable | REFUSE | REFUSE |

† R1/R2 rulings of 2026-09-10 (§ Plan update), **implemented**. Two rows the
review added beyond the six are in the code too: a redirected registry in the
entry's own `env` REFUSES at both postures (R10), and every warn row above
raises a finding on the operator's surface rather than only a log line (R9).

Where the brief's item 1 ("unresolvable is a refusal, not a pass") and item 3
("refuse on could-not-tell only under strict") looked in tension, the six named
tests settled it: *unresolvable* and *unreachable* refuse outright. *Unpinned*
did too until R1 moved it to warn, so the rows `strict` moves are now three —
an unpinned entry, an advisory OSV carries no severity for, and a distribution
mechanism with no advisory source.

### The line between absent and unobservable

*Rewritten 2026-09-10 under R2 (§ Plan update) and implemented the same day.*

The line is **does the entry fetch from a public registry at launch**, not
"can I name a package". `npx`/`bunx`/`npm exec`/`pnpm dlx`/`yarn dlx`,
`uvx`/`uv tool run`, `pipx run`, `deno run npm:…` and `go run mod@ver` decide
the artifact at launch — the launch *is* the install — so that artifact is what
gets preflighted. `python -m mcp_server_git`, `node server.js`,
`command: /opt/thing/server` and `python /opt/thing/server.py` do not fetch:
whatever runs was installed earlier and deliberately by the operator, and this
gate cannot see inside the child's environment, so refusing there claimed a
protection it does not have. All of those PROCEED, without a note. Stated
cost: a compromised release already installed in the operator's venv is not
caught. It never was.

Inside the fetch-at-launch family there are three outcomes, not two:

* **named and pinned** — queried at that exact version; the table applies.
* **named, no version** (`npx -y @scope/pkg`, `go run mod@latest`) — R1: a
  package-level query. Two answers are conclusive at package level and
  REFUSE: a `MAL-` record, and a HIGH/CRITICAL advisory whose affected range
  is still open (an `introduced` event with no `fixed` and no `last_affected`),
  because the launch-time artifact is inside that range by construction.
  Anything else warns and launches, the message saying the entry is unpinned
  and how many advisories the package has carried; `strict` refuses.
* **fetches but cannot be named** (`npx github:user/repo`, a tarball URL, a
  name that fails its ecosystem's grammar) — `unresolvable`, REFUSED: the
  artifact is decided at launch *and* nothing can be asked about it. The
  message says the entry can be rewritten to a registry coordinate — which is
  why this refuses where `docker run` only notes: here the operator has a fix.

`jsr:` and `docker run` fetch at launch with no advisory source behind them;
they stay `unsupported_launcher` — a note by default, a refusal under `strict`.

### Stated gaps, not papered over

* `docker run`, `go run`, `deno`, `cargo` distribute real packages this module
  has no advisory source for. They land in `unsupported_launcher`: a note by
  default, a refusal under `strict`.
* CVSS v4 vectors are not scored. A v4-only record falls to "severity unknown",
  which is a could-not-tell row, never a clean pass.
* A bare path is not screened by this gate at all. Its threat model is a
  *published* package; a local binary is `entry_guard`'s and the write
  classifier's problem.

### What goes on the wire

`{"package": {"name": ..., "ecosystem": ...}, "version": ...}` and nothing else,
built from the three resolved fields. A test drives a real entry carrying a home
directory path and a token-shaped argument through the gate and asserts the
posted body is exactly the coordinates. The entry's own strings are what a
planted config controls, so every one that reaches a log line or an error goes
through `_safe()` — control characters flattened, length capped — and a name
that fails its ecosystem's grammar is `unresolvable` rather than a query.

### Tests

`halbert_core/tests/test_mcp_package_preflight.py` — 72 offline + 3 live.
All six the brief asked for, plus resolver tables, the CVSS scorer against the
specification's worked examples, the cache's TTL and per-version keying, the
proof that a failure is *not* cached (a blip must not be sticky for the TTL),
config reload without a restart, and two log-forging attempts through a planted
package name and a planted advisory id.

The switch-off test asserts on the HTTP seam (`_osv_post`), not on a log line,
per the brief — a log assertion would pass just as happily for a request that
went out silently. There is a second one at the client layer: with the switch
off, `_ensure` completes a launch and the seam was never touched.

The three live tests are skipped unless `HALBERT_LIVE_OSV=1`. The wire contract
*was* verified against the real `api.osv.dev` on 2026-09-10:
`lodash@4.17.20` → 5 advisories, CVSS_V3 vectors, worst HIGH;
`left-pad@1.3.0` → no `vulns` key at all;
`requests@2.19.0` (PyPI) → 10 advisories, `database_specific.severity:
MODERATE`. The local scorer and GitHub's own word agreed on every record seen.

### Not done, deliberately

The dashboard's `mcp_config.yml` write path is **not** gated by this. The entry
guard belongs there because it is static and instant; a network call in a form
submission is a different thing, and the brief did not ask for it.

### Founder decision

`DECISIONS.md` row `FD-10` (built), 2026-09-10, `pending`. The eight defaults
above are an AI session's choices under the brief; the one most worth an
explicit ruling is the first — refusing every unpinned entry.

---

<a id="plan-update"></a>
## Plan update — Fable review, 2026-09-10

| # | Call | Verdict | Why |
|---|---|---|---|
| R1 | unpinned warns instead of refusing | **accept, amended** | An opt-in gate that refuses the commonest entry shape gets switched off, which loses even the malware check; `strict` keeps pin-required for operators who want that stance. Amendment: a package-level answer is conclusive in two cases, not one — a `MAL-` record, and a HIGH/CRITICAL advisory whose affected range is still open (`introduced`, no `fixed`/`last_affected`), because the launch-time artifact is inside that range by construction. Refuse on both; warn on the rest. |
| R2 | fetch-at-launch replaces can-I-name-it | **accept, amended** | Refusing `python -m` claimed a protection the gate cannot deliver (it cannot see the child's venv) and taught operators the gate is noise. Amendment: the rule has three legs, not two — does not fetch → proceed; fetches and named → query; fetches and unnameable → `unresolvable`, refuse — and `yarn dlx` joins the npm launcher family. |
| R3 | switch file moves to the config directory | **accept** | Measured: today the agent can turn its own gate off with a MEDIUM (unconfirmed) write; the config directory classifies HIGH and is where `mcp_config.yml` already lives. No shim for the old path — a file left there is left unread. |
| R4 | add a Go resolver | **accept** | `go run mod@v1.2.3` is a real launch-time fetch with a populated OSV ecosystem, which cargo is not — cargo has no built-in run-a-named-crate verb. Normalise the `v` prefix once so the cache keys on one spelling; `@latest` or no version follows R1. Do it last; it is the least likely shape. |
| R5 | add the Deno `npm:` specifier | **accept** | A string rewrite onto a coordinate the npm resolver already handles. `jsr:` stays `unsupported_launcher` (note; `strict` refuses) — not a pass, and not `unresolvable`, since there is no source to resolve against. |
| R6 | do not implement CVSS v4 | **accept** | Zero of 18 real pinned releases fold to unknown and the v4-only gap never stands alone; the existing unknown-severity row (warn; `strict` refuses) already covers it. |

Not escalated: R1 is the one loosening, and it loosens an opt-in gate whose
`strict` mode keeps today's behaviour, so it is ruled here rather than punted.
The founder overturns it by flipping the R1 row; nothing else depends on it.
`cargo` and `docker`: agreed, no change.

### Recommendations beyond the six

Not in the handoff; the reviewer's own. Recommendations, not rulings — the
implementer takes them unless the founder strikes one.

| # | Recommendation | Why |
|---|---|---|
| R7 | The R1 open-range check is its own logic, tested on its own | It must read `affected[].ranges[].events`, never the severity word — the two are independent in OSV data, and a test on severity alone passes with the range check missing. An `affected` entry that lists explicit `versions` and no ranges is closed by construction. A record carrying `withdrawn` is skipped at every severity: a withdrawn HIGH must not refuse a clean package. |
| R8 | `strict` + unpinned refuses without querying | The outcome is fixed before the request, so a deterministic refusal needs no egress — the same rule as "never a model where a template suffices", one layer down. Test: the seam is untouched. |
| R9 | A warning the operator never sees is a pass | Every warn outcome — unpinned, below-HIGH, severity unknown, unsupported launcher — reaches the operator-facing findings surface (the bell), not only a log line. Test on the finding being raised, not on the log, for the same reason the switch-off test asserts on the HTTP seam. |
| R10 | A registry override in the entry's `env` makes the coordinate a lie | `NPM_CONFIG_REGISTRY`, `PIP_INDEX_URL`/`UV_INDEX_URL`/`UV_DEFAULT_INDEX`, `GOPROXY` in the entry mean the fetched artifact is not the one OSV was asked about. Treat the entry as *fetches but cannot be named* → `unresolvable`, refused, the message naming the key. A local check on the entry; nothing extra on the wire. Stated cost: an `.npmrc` or `pip.conf` in the working directory does the same thing invisibly, so this catches only the declared case. |

**Implemented 2026-09-10, in this order** — full suite 8556 passed, 0 failed
(135 tests in `test_mcp_package_preflight.py`, 3 of them live and opt-in):

1. **R3** — `_config_path` → `get_config_dir()`. One line, first: it is a live
   gap in a built gate.
2. **R1** — version-less OSV query for an unpinned entry, cached on
   `(ecosystem, name, "")`; `MAL-` or open-range HIGH/CRITICAL → refuse; else
   warn with "unpinned" in the message; `strict` → refuse **without querying
   (R8)**. Tests: the four outcomes, the seam untouched under `strict`, and
   the R7 set — range-not-severity, `versions`-only is closed, `withdrawn` is
   skipped.
3. **R2** — `python -m` → proceed with no note; add `yarn dlx`;
   unresolvable-on-a-fetching-launcher keeps refusing. Tests: the two flipped
   cases, and that `npx github:user/repo` still refuses.
4. **R5** — `deno run npm:@scope/pkg@ver` → npm coordinate; `jsr:` →
   `unsupported_launcher`.
5. **R4** — `go run mod@ver` → ecosystem `Go`, `v` normalised.
6. **R6** — nothing to build. The "v4 not scored" line under § Stated gaps
   stays true.
7. **R9** — every warn outcome raises a finding on the operator surface.
   Test on the finding, not the log.
8. **R10** — a registry-override env key in the entry → `unresolvable`.
   Tests: one entry per key, and a clean entry that still resolves.

Then update § What landed to match, and the `FD-10` (built) row moves from
`pending` when the founder ratifies.


---

## Implementation notes — 2026-09-10, after the review

All ten rows (R1–R10) are in the code. Full suite **8556 passed, 0 failed**.
Verified live against `api.osv.dev` afterwards, default posture:

```
proceed  unpinned    npx -y @modelcontextprotocol/server-filesystem
proceed  clean       npx -y @modelcontextprotocol/server-filesystem@2026.8.31
proceed  unpinned    uvx mcp-server-git
REFUSE   advisory    uvx --from requests==2.19.0 x        (10 advisories, worst HIGH)
proceed  no_package  python3 -m mcp_server_git
REFUSE   advisory    go run github.com/gogo/protobuf@v1.3.1
REFUSE   advisory    deno run npm:lodash@4.17.20
```

`strict` refuses the two unpinned rows, and refuses them **without a request**.

### Two things the implementation found that the review could not

**An unpinned resolution carried no identity.** Every resolver returned
`Resolution("unpinned", detail)` with `identity=None`, because before R1 nothing
downstream needed it. R1's package-level query does, and the `None` fell through
to the `unresolvable` branch — so the first cut of R1 silently refused every
unpinned entry with the wrong reason while looking like it worked. Caught by the
test asserting the query was made with an empty version, not by the one
asserting the verdict. The unpinned resolutions now carry
`PackageIdentity(ecosystem, name, "")` and the `None` branch is a guarded
`pragma: no cover` that refuses rather than guesses.

**The composed message was ungrammatical.** `_unpinned_verdict` prefixed the
resolution's own detail, which already ended "…is not pinned to a version, so
the entry installs whatever npm publishes at launch", producing "…at launch is
unpinned; the package has…". The verdict now takes the bare coordinate
(`npm '@scope/pkg'`) and the resolver's explanation is used only where it stands
alone — the `strict` refusal. Not a correctness bug; it would have been the
first thing an operator read.

### R9's shape, spelled out

`report_finding()` files under detector `mcp_package_preflight`, deduplicated on
`(detector, title)` so relaunching a server does not stack findings. A refusal
files at `critical`, a warning at `warning`; `clean`, `no_package` and
`disabled` file nothing — a finding raised on every healthy launch is a finding
nobody reads. It never raises: a findings store that is locked or missing must
not stop a server launching, because this is a notification and not a gate.

### R10's stated cost, kept

The check reads the entry's env KEYS and never the values — those are routinely
URLs with a token in them, and a test asserts a planted `sk-secret` reaches
neither the detail nor the message. It catches the declared case only: an
`.npmrc` or `pip.conf` in the working directory redirects the same way and no
config-entry check can see it.

### The adversarial pass, and what it found

Four more defects, after the review's ten rows were in and green. Each is now
pinned by a test named for it.

* **Legacy uppercase npm names were refused as malformed.** npm only started
  requiring lowercase around 2017; `JSONStream` and its cohort are still
  installable. A lowercase-only grammar made them `unresolvable`, which under
  this gate means refusing a real server over a real package. The case is now
  carried through untouched, because OSV matches the name as published.
* **A refusal named the wrong advisories.** `_advisory_ids` capped at six and
  took whichever came back first, so a package with eight LOW findings and one
  `MAL-` record refused for malware while citing six unrelated LOW ids — the
  brief's own first test ("the refusal names the advisory id") defeated by
  volume. Refusals now name the records responsible for them.
* **One arm of the malware test never fired.** It checked
  `database_specific.malicious`, a shape OSV does not emit; the real feed
  writes `malicious-packages-origins`. The `MAL-` id prefix was carrying the
  whole check alone. Both keys are accepted now.
* **`npx -p a -p b` installs both packages and only the first was checked** —
  a second package could ride in behind a cleared one. An entry naming more
  than one is refused rather than half-checked.

One thing the pass could not fix, now stated in the module: an advisory source
cannot tell "this release has no advisory" from "no such package", so a typo'd
or unpublished name answers CLEAN. Closing it would mean a second request to a
second host on every launch.

### Founder decision

**Ratified 2026-09-10.** FD-10's recorded default was *Not now*; the founder
overruled it and ratified the gate as built. R7–R10 — the reviewer's own four
recommendations beyond the six — are kept in full. The `DECISIONS.md` row reads
`ratified 2026-09-10 (founder)`.
