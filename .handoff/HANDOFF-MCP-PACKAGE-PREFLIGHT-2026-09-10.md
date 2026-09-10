# MCP server package preflight (FD-10) — dispatchable

**Status:** not built. Verified 2026-09-10 by grep over `halbert_core/`: the only
`preflight` matches are CORS preflight in `mcp/server.py:1652,1704`, and there is
no OSV, advisory or package-vulnerability call anywhere in the tree.

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
