# Fable: review six calls, update the plan. ~15 minutes.

**Budget is tight — this is deliberately a small job.** Read this file only.
Do not read source, do not run tests, do not search the tree. Everything
needed is inline. Nothing here changes code.

**The plan you are updating:** `.handoff/HANDOFF-MCP-PACKAGE-PREFLIGHT-2026-09-10.md`
(FD-10, the opt-in OSV package preflight for MCP servers). It is **built and
green** — 8501 tests pass. Six defaults in it were then researched and found
wrong or improvable. Your job is to rule on the six and write the ruling into
the plan. An implementer picks the code up after you.

---

## What the thing is, in three sentences

Before Halbert launches a third-party MCP server, the preflight works out which
package the config entry would install (`npx -y pkg@1.2.3` → npm `pkg` `1.2.3`)
and asks OSV whether that exact release has a known advisory. It refuses the
server — never the daemon — on a HIGH/CRITICAL advisory or a malware record.
It is off by default and switched on by an operator file.

---

## The six calls

Each is: what ships now → what was measured → the recommendation. Measurements
are from live queries against `api.osv.dev` and from running Halbert's own write
classifier on 2026-09-10.

### R1 — an unpinned entry should warn, not refuse
**Now:** `npx -y @modelcontextprotocol/server-filesystem` (no version) is
REFUSED. That is the commonest real MCP entry shape.
**Measured:** OSV accepts a version-less query. That package with no version
returns 2 advisories; pinned at today's release it returns 0 — so a version-less
answer says *this package has a history*, not *what you will get*. A malware
(`MAL-`) record, though, is conclusive at package level.
**Recommend:** query without the version. A `MAL-` record → refuse. Anything
else → warn and launch, saying the entry is unpinned; refuse under `strict`.

### R2 — the line is "does it fetch at launch", not "can I name it"
**Now:** `python -m mcp_server_git` is refused (a module name is not a
distribution name); a bare path proceeds. The two are hard to tell apart.
**Reasoning:** `npx`/`uvx`/`pipx run`/`npm exec` fetch from a public registry at
launch, so the artifact is decided at launch and must be preflighted.
`python -m`, a bare path and `node server.js` do not fetch — the operator
installed that deliberately, earlier. Refusing there claimed a protection this
gate does not have; it cannot see inside the child's environment.
**Recommend:** adopt fetch-at-launch as the rule. `python -m` proceeds.
**Stated cost:** a compromised release already installed in the operator's venv
is not caught. It never was.

### R3 — move the switch file to the config directory
**Now:** `mcp_preflight_config.yml` lives under `paths.data_dir()`
(`~/.local/share/halbert`).
**Measured** with Halbert's own write classifier: a write there classifies
MEDIUM — **no confirmation** — so the agent can switch its own security gate off
without asking. The same write to the config directory classifies HIGH.
`mcp_config.yml` and `vision_config.yml` are both already in the config
directory.
**Recommend:** move it beside `mcp_config.yml` (`get_config_dir()`). One line.
**Not your problem, already filed separately:** the underlying cause is that two
resolvers disagree about the data directory on macOS, which leaves the state
ledger and `skills_config.yml` unprotected too.

### R4 — add a Go resolver
**Measured:** OSV has a populated `Go` ecosystem and accepts both `v1.3.1` and
`1.3.1`. `go run mod@v1.2.3` fetches at launch.
**Recommend:** build it. Small.

### R5 — add the Deno `npm:` specifier
**Measured:** `deno run npm:@scope/pkg@1.2.3` is a pure string rewrite onto an
npm coordinate. `jsr:` has no OSV ecosystem.
**Recommend:** build the `npm:` case; leave `jsr:` unsupported.

### R6 — do not implement CVSS v4 scoring
**Measured:** across 694 real advisories — 59.5% carry a v3 vector (already
scored locally), 30.3% carry no severity at all, but 95.9% of *those* have a
scored twin in the same OSV response. End to end: **0 of 18 real pinned releases
fold to "severity unknown"**. The v4-only-with-no-severity-word gap is 2.2% of
records and never stands alone.
**Recommend:** do not build it. A 270-entry macrovector table buys nothing
measurable. Same evidence says `strict` mode is not a nuisance mode.

Also not recommended, for the record: `cargo` (real OSV ecosystem, but not how
MCP servers ship) and `docker` (no OSV ecosystem for images — vetting one means
pulling the thing you are vetting; it already warns, and refuses under `strict`).

---

## Your task

**1.** For each of R1–R6 decide `accept`, `reject`, or `amend`. One line of
reasoning each. You are the review, not a rubber stamp — R1 and R2 loosen a
security gate and R3 tightens one, so say so if you disagree.

**2.** Append one section to `.handoff/HANDOFF-MCP-PACKAGE-PREFLIGHT-2026-09-10.md`:

```markdown
## Plan update — Fable review, 2026-09-10

| # | Call | Verdict | Why |
|---|---|---|---|
| R1 | unpinned warns instead of refusing | | |
| R2 | fetch-at-launch replaces can-I-name-it | | |
| R3 | switch file moves to the config directory | | |
| R4 | add a Go resolver | | |
| R5 | add the Deno `npm:` specifier | | |
| R6 | do not implement CVSS v4 | | |

**Left to implement:** <the accepted rows, as a short list>
```

**3.** In that same plan file, fix the two sections the accepted rows contradict,
so nobody implements from stale text:

* the policy table under **The policy, as built** — change the `package named,
  no version` row from `REFUSE / REFUSE` to `warn, proceed / REFUSE` if R1 is
  accepted;
* the section **The line between absent and unobservable** — it currently argues
  the opposite of R2. Replace its argument with the fetch-at-launch rule if R2
  is accepted.

Leave every other section alone. If you reject a row, leave the matching section
exactly as it is.

**4.** Amend `DECISIONS.md` row `FD-10` (built), dated 2026-09-10, in place:
append one sentence naming which of R1–R6 were accepted. Do not restructure the
table — the file is append-only and that row is already long.

---

## Boundaries

* **No code.** Not one line. The implementer needs your ruling, not a patch.
* **No test runs, no greps, no source reads.** The measurements above are done.
* Do not commit. Concurrent sessions edit this repo; leave the working tree for
  the founder.
* If a call genuinely needs the founder rather than you — R1 and R3 are the
  candidates — write `founder` in the Verdict cell and say why in one line.
  That is a valid answer and costs nothing.
