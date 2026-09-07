# D-2 Design: Halbert Skills System — CC-compatible, progressively disclosed, self-improving

**Date:** 2026-09-07
**Status:** design only — no code, no packets cut yet
**Sources:** `OSS-REVIEW-OPENCLAW-2026-09-07.md` §7 (format, catalog, ladder, gating, custodian, telemetry, security) · `OSS-REVIEW-HERMES-2026-09-07.md` §5 (learning loop) and §6 (skill ledger, "event tables with a named consumer") · founder directives: deterministic policy over LLM judgment on security paths; no model names anywhere user-or-model-visible; never a model where a template suffices.
**Companion (parallel):** D-1 `DESIGN-SESSION-TREE-AND-COMPACTION-2026-09-07.md` — interaction points flagged inline as **[D-1]** for reconciliation when it lands.

---

## 0. What exists today, and the one structural decision

Halbert already has a skills subsystem (`halbert_core/skills/`): `parser.py` (frozen `Skill` dataclass, YAML frontmatter, `kind: ops|lens`), `loader.py` (four search dirs, same-name override, refusal to let a user file replace a built-in and drop its declared safety), `registry.py` (aliases, `extends` flattening), `matcher.py` (weighted domain/keyword scoring, cap 3 active, explicit-name invocation), `composer.py` (prompt/safety/scope/model/budget merge, char caps of 4k/8k). Nine bundled skills ship in `skills/builtin/`, eight of them `ops` and one lens (`understated`). Wiring runs `intake/pipeline.py` (matcher → `MessageIntake.active_skills`) → `agents/state_machine.py` (safety bound onto the executor's framework at turn start, expertise text injected between the identity block and the turn prompt at §1707–1781) → `context/assembler.py` (retrieval scope).

That system is **matcher-driven auto-injection**: the host decides which skills are active and injects their whole body. Claude Code's Agent Skills are **progressively disclosed**: the prompt carries a catalog (`name`/`description`/`location`); the model reads SKILL.md on demand. The reviews are explicit that we want both properties, so the design decision is:

**Two delivery tracks over one parsed `Skill` model.**

- **Track A — bound activation** (deterministic, host-side): `kind: ops` and `kind: custodian` skills with triggers. The matcher decides activation; frontmatter `safety`/`allowed_tools`/`scope`/`model` compile onto the turn exactly as today. *Safety is compiled, never disclosed* — a skill's protected paths cannot depend on the model choosing to read a file. What changes is the body: instead of blanketing the full text into messages[0] on both LLM calls of a turn (the double-payment the composer's caps already lament), a matched skill injects a short activation notice plus the body under the truncation ladder (§2.3). The full body also remains readable at its catalog location.
- **Track B — catalog disclosure** (model-side): *every* skill — bundled, user, workspace, agent-authored, ingested ecosystem packs, and matched Track-A skills alike — appears in one `<available_skills>` catalog. The model consults a skill by reading its `location` through the existing `read_file` tool; that read is a telemetry receipt (§6). Ecosystem packs and agent-authored skills carry no triggers and no safety block, so they exist *only* as Track-B entries — this is the class the matcher structurally cannot see today.

`kind: lens` stays out of both tracks' decision logic: a lens is voice only, selected by `active_lens` (design decision CD-2), never by the matcher and never by model discretion; lenses appear in no catalog.

This keeps every existing guarantee (safety merge, scope resolution, lens purity checks in the parser) and adds the ecosystem and self-improvement surfaces the reviews describe, without a second skill format.

---

## 1. On-disk format

### 1.1 Layout

```
<root>/<skill-name>/
    SKILL.md            required: frontmatter + body
    references/         optional: longer docs the body points at
    scripts/            optional: executables the body may invoke
    .halbert-skill.json optional sidecar: provenance + lifecycle (§5.4)
```

`SKILL.md` and bare `<name>.md` remain accepted (current loader contract); the directory layout is required for ecosystem compatibility and for the sidecar.

### 1.2 Frontmatter — CC-compatible core + namespaced extensions

**CC-compatible fields, byte-compatible semantics** (OpenClaw review §7: the catalog renderer is "byte-for-byte aligned with the upstream Agent Skills formatter"):

| field | meaning |
|---|---|
| `name` | `^[a-z0-9][a-z0-9-]{0,63}$`, unique per resolved registry |
| `description` | the routing surface. **≤60 chars** for Halbert-authored skills, enforced by *hard create-time rejection* (Hermes: "hard-rejects over-budget descriptions at create time — enforcement, not lint"). Ingested ecosystem packs we do not control are load-time clamped with a visible `…` marker, never edited on disk |
| `allowed-tools` | accepted as CC writes it; maps onto our `allowed_tools` tuple |
| `license`, `metadata` | passed through untouched |

Unknown frontmatter keys are *tolerated, not rejected* — the parser already behaves this way, and it is what makes third-party packs load. Tolerance ends at our own extension schema below.

**Halbert extensions, namespaced** under `halbert:` (single key holding a mapping), so a future upstream field can never collide with ours:

```yaml
halbert:
  id: sk_01JZQ…            # stable skill ID, stamped at creation (§5.4)
  kind: ops | lens | custodian        # default ops
  triggers: {...}           # as today
  safety: {...}             # as today (ops/custodian only)
  role / scope / knowledge_scope / trace_expand   # as today
  tier: chat | specialist | vision    # renames `model:`; see Determination, §4.3
  priority / budget_multiplier / subagent / max_turns  # as today
  extends / aliases                   # as today
  requires:                 # capability gating, §3
    bins: [zfs, smartctl]   # all must exist on PATH
    anyBins: [gsed, sed]    # at least one
    env: [HA_TOKEN]         # all must be set (names, never values)
    os: [darwin, linux]
    config: [ha_connection] # capability-registry names
  state: draft | trusted | archived   # agent-authored lifecycle, §5.6
```

Migration stance: today's flat Halbert keys (`triggers`, `safety`, `model`, …) remain readable for one cycle; the loader warns and rewrites nothing. *No migration machinery beyond the reader* — per the no-legacy-support posture, old files that aren't rewritten simply keep working through the compat reader.

### 1.3 Roots and precedence

Three roots, least specific first, later wins **within a persona** — deliberately *not* OpenClaw's seven-layer sprawl (anti-pattern #4):

1. **bundled** — `halbert_core/skills/builtin/`
2. **user** — `~/.config/halbert/skills/`
3. **workspace** — `<host-project>/.halbert/skills/` plus `<host-project>/.claude/skills/` for CLI/ecosystem compat. The daemon already restricts itself to roots 1–2 (`daemon_skill_dirs()`), because "whatever shell the user happened to start it from" must not define the machine's prompt; that restriction is load-bearing and stays.

The existing refusal stands: a non-bundled skill that takes a built-in's *name* is refused, not merged, because overriding by name would silently disarm the builtin's declared safety (`loader.py`'s own comment). Persona scoping adds the fourth dimension, next.

### 1.4 Per-persona scoping — the custodian pattern

OpenClaw's custodian skills are "dangerous ops runbooks [that] load **only** for the configured system-custodian agent — hidden from user-facing agents by *discovery scoping*, not prompt policing" (review §7). Halbert adopts this as the general mechanism:

- Each persona owns an ordered **root set**. The machine's own persona gets all three roots. The maintenance/custodian persona gets all three **plus** `~/.config/halbert/custodian/skills/` — dangerous runbooks (`kind: custodian`, all following the **Gather → Mutate → Repair → Prove → Report** contract ending in one live end-to-end proof). The guest persona gets a *named subset* of the user root only.
- Scoping happens in the **catalog builder**: a persona's catalog is rendered from the registry filtered by that persona's root set. The custodian files are never in a user-facing persona's search path, so there is nothing for prompt text to police. This is the same shape as the guest tool surface (`persona/guest_tools.py`): the guest's *tool schemas* are narrowed at `get_schemas()`; the guest's *skill catalog* is narrowed at catalog build. One idea, two surfaces.
- Track-A activation is persona-diminished identically: the matcher runs over the persona-scoped registry view, so a guest turn cannot match `storage-ops` even by explicit invocation. Combine with the existing guest narrowing in `tools/executor.py` (schemas hidden, named calls refused and audited) and a custodian skill is unreachable from a guest turn by three independent mechanisms — by construction, not by policy prose.

---

## 2. Discovery, catalog, and prompt integration

### 2.1 The `<available_skills>` block

Rendered into `AgentPromptBuilder.build_system_prompt`'s assembly (Halbert's tiered XML), placed between the identity block and the turn-volatile sections — the seam where `_composed_prompt_block()` already hangs matched-skill text. Shape exactly as the ecosystem formatter:

```xml
<available_skills>
<skill>
<name>zfs-snapshot-rollback</name>
<description>Roll back a ZFS dataset to a named snapshot safely</description>
<location>~/.config/halbert/skills/zfs-snapshot-rollback/SKILL.md</location>
</skill>
…
</available_skills>
```

Compatibility is the point: an ecosystem pack that works in Claude Code ingests unchanged (OpenClaw: "Match the format … and Halbert ingests ecosystem skill packs directly"). The matcher remains a Halbert-native *bonus* channel on top of the catalog, never a replacement for it — an ecosystem skill with no `halbert.triggers` still routes, because the 60-char description is the routing surface and the model reads the file.

### 2.2 Cache boundary and structured snapshots

Two directives land together here:

1. **Stable-prefix assembly with a literal cache boundary** (OpenClaw §7). Everything above a `CACHE_BOUNDARY` marker — identity, catalog, bound-skill bodies, user rules — is a pure function of versioned inputs; everything volatile (date, modality guidance, continuity hint) sits below it. The stable prefix is sha256-keyed over `(prompt-template versions, identity inputs, skill snapshot version, user-rules version)` and LRU-memoized. Skill catalog changes are one bit in the key, so a skill edit invalidates exactly the cache entries that must die and no more.
2. **Never re-parse the rendered prompt** — the anti-pattern both reviews flag (OpenClaw's own §7 and its anti-pattern #2: "regex-parses its own rendered prompt in two places and pays for it with parity tests"). Halbert's loader already produces structured `Skill` objects; the catalog renders from those, and any consumer that wants skill facts (the telemetry matcher, the dashboard, the curator) reads the registry/snapshot, never the prompt string. The registry gains a monotonic `snapshot_version` bumped on any add/remove/reload; the memoized catalog render is keyed by `(snapshot_version, persona, budget)`.

A filesystem watcher (mtime debounce, same discipline as the config watcher) on the live roots triggers registry reload; daemon restarts re-probe from scratch.

### 2.3 The token-budget ladder

When the catalog plus bound-skill bodies exceed the skill section's budget, degrade *in this order* (OpenClaw `skill-prompt-limits.ts`, "~100 lines of Python"):

1. drop descriptions (names + locations only);
2. binary-search skill count (drop lowest-priority Track-B entries first; persona-scoped ordering is deterministic so the cut is explainable);
3. binary-search description length;
4. **identity floor**: names and locations are never cut. A skill the model cannot discover does not exist; a skill whose description got trimmed still does.
5. every degradation appends an honest truncation notice ("catalog truncated from 41 to 12 skills; full list at `halbert skills list`") telling the operator how to audit.

Characters, not tokens — the composer's own comment applies: "this runs before any tokeniser is in scope, and a character bound that is roughly right beats a token bound that needs a model handle to compute."

### 2.4 Explicit invocation and reserved names

The matcher's `explicit=` path already gives `/storage-ops`-style invocation. Formalize: a slash-command channel (intake recognizes `/<name>` and routes to `explicit`) with a **reserved-name set** checked at load and at create — reserved = registered tool names + intake slash builtins + persona handback names. A skill (or an MCP-adjacent artifact) that tries to claim a reserved name is refused at spec-build, the same posture as the loader's builtin-name refusal. The dashboard's slash affordance is a D-1/UI question; the intake-level check lands regardless. **[D-1]**

---

## 3. Capability gating

Frontmatter `halbert.requires` is evaluated at **catalog build**, against the live host, producing a catalog that is "always an honest set of things runnable *right now*" (OpenClaw §7). Evaluation:

- `bins` / `anyBins`: `shutil.which` probes at registry load — presence checks, exactly the philosophy the capability registry already states ("probes are cheap … not network probes"). `bins` is all-of, `anyBins` any-of (copy the distinction verbatim).
- `os`: checked against `current_platform()` from `skills/matcher.py` (alias normalization reused).
- `env`: variable *names* must be set in the daemon environment. Values are never read, logged, or copied.
- `config`: names of `capabilities.py` capability keys, answered by `has_capability()` — a skill that says `config: [ha_connection]` appears on house-configured nodes and vanishes on a bare sysadmin box, with zero new probe code.

Gating verdicts are cached per `(skill, snapshot_version)` and re-evaluated on capability re-probe. Two behaviors matter beyond the plain gate:

- **Quarantined-secret vanishing**: when a credential a skill names in `requires.env` enters quarantine (the security workstream's secret-sealing subsystem), the skill drops out of every catalog rather than appearing with unusable prerequisites (OpenClaw §7, explicit behavior).
- Gated-out skills remain visible to operators via `halbert skills list --all` with the failing clause named — honesty upward, invisibility to the model.

---

## 4. Security

### 4.1 Load-time content scanning

Every SKILL.md body (and every `references/*.md` it ships) passes a scanner at load — *markdown bodies, not just code*, per OpenClaw ("content scanning for prompt-injection phrasing in markdown bodies … not just code for malware"). Checks:

- classic injection phrasing ("ignore all previous instructions", role-reassignment openers, hidden-instruction HTML comments with directive content);
- Halbert's own control-tag surface: body text is run through the same defang machinery `prompts/agent_prompts.py` applies to untrusted rows (`_CONTROL_TAG_RE` collapsing `continuity`/`speech`/`text`/`modality_context`), so a skill cannot forge a modality directive or close the continuity block;
- oversized base64/hex blobs and URLs in instruction position are flagged for operator review, not silently loaded.

Bundled skills that trip the scanner fail CI; user/workspace/pack skills that trip it are **refused with the finding logged**, not scrubbed — silently rewriting an instruction file is how you get instruction files you can't audit. (Composition-time defanging stays on as defense in depth regardless.)

### 4.2 Boundary-safe reads and untrusted frontmatter

- Skill files are read with `realpath` confinement (must resolve under the declaring root — symlink escape refused), hard byte caps (SKILL.md 128 KiB; frontmatter block 8 KiB; per-`references` file 256 KiB), strict UTF-8, no NULs.
- Frontmatter is untrusted input throughout: `yaml.safe_load` only (current behavior), every scalar length-capped, `name` charset-enforced, and no frontmatter string reaches a shell, a path join, or a Jinja/`str.format` template raw. The sidecar JSON gets the same treatment.

### 4.3 The Determination rule — no model names, enforced

Founder directive (binding): no skill text may name or recommend AI models — not in the body, the description, the catalog, or any UI surface the catalog feeds; "never a model where a template suffices" and tiered slots only. Enforcement is deterministic, at three seams:

1. **Linter** (§5.6): a fixed banned-term matcher over description + body + frontmatter strings (same machinery class as the repo's vocabulary guard), hard-fail on hit.
2. **Parser**: the current `"provider:model"` passthrough in `model:` frontmatter is **retired**. `halbert.tier` accepts `chat | specialist | vision` — nothing else, and the compat reader downgrades legacy passthrough values to `chat` with a warning rather than honoring them.
3. **Ingest**: an ecosystem pack whose text names models is refused at ingest with the offending lines in the refusal report. We do not auto-scrub; the operator edits or drops the pack.

This is exactly the "deterministic policy over LLM judgment" posture applied to the skills plane: the rule is a matcher, not a vibe.

---

## 5. The learning loop — Halbert's self-improving surface

This is Hermes §5 ported onto Halbert's seams, with Hermes's own incident history as the argument for every guard. Hermes's anti-pattern #9 is adopted as a hard constraint: **no cache-parity agent fork** — the review "fork-with-suppressed-flags implementation is where their incidents lived. Design background passes as first-class queued jobs with explicit isolation."

### 5.1 Deterministic nudge counters

- **What counts**: tool iterations per session — `len(ctx.tool_calls)` at the end of a turn in `agents/state_machine.py` (the seam where `ctx.max_loops` already bounds the loop). A per-session counter `tool_iters_since_review` accumulates; **threshold: ≥10** (Hermes's number, calibrated; ours is tunable in config, default 10).
- **Reset on use**: any skill receipt this turn (§6 — matcher activation, explicit invocation, or a catalog `read_file` of a skill path) resets the counter. The loop exists to notice work that *should* have had a skill and didn't.
- **Rehydration**: on session resume, the counter is rebuilt from persisted tool-call rows since the last review event — Hermes's "rehydrated from history on restart," and in Halbert the rows already live in the conversation store. **[D-1]** — the transcript tree's tool rows are the rehydration source; reconcile with D-1's node types.
- A second counter, `turns_without_memory_write ≥ 10 → memory review`, is noted for the memory workstream but is *not* this design's scope.

### 5.2 The review job

When the counter trips, review runs **post-delivery, as a queued job on the Halbert scheduler** (the same cron substrate packet-03 maintains — one-shot job, no user-visible reply): the turn's answer is already delivered; review happens off the user's path and never eats a turn (OpenClaw memory rule, generalized).

- **Dispatch-side whitelist** (copy Hermes verbatim): the review job is assembled with the normal tool schemas so the advertised surface stays byte-identical (prefix cache stability), but *dispatch* filters execution to the read-and-author set — `read_file`, skill-catalog queries, and the skill-authoring tools of §5.3. Dangerous commands are auto-denied regardless of the job's own prompt.
- Any live turn cancels the review job; the job surfaces a one-line summary into the findings stream, never into chat.

### 5.3 Policy text — the anti-hoarding doctrine

The review prompt carries Hermes's doctrine adapted (source: Hermes review §5; phraseology near-verbatim, Hermitian incident citations dropped, Halbert nouns substituted):

> You are deciding whether anything from this session is worth teaching Halbert permanently. Hoarding is the failure mode, not forgetting. **Never capture**: environment-dependent failures (a fix that only worked because of this machine's state), transient errors, claims that a tool does not work, or unresolved failures — never dress up dead ends as best practice. Prefer, in order: (1) patch the skill that should have fired this session, (2) patch another existing skill, (3) create a new skill — and stop at the first rung that covers it. User frustration is a first-class signal: repeated rephrasing, consecutive failures of the same tool, or an abrupt change of tack each count as evidence a skill is missing or wrong. If nothing clears this bar, write nothing and report that.

### 5.4 Write-path guards

- **Read-before-write**, enforced per review-turn with a `contextvars.ContextVar` set (the direct Python port of Hermes's ContextVar guard): the authoring tool refuses a create-or-patch of skill `sk_X` unless *this turn* contains a `read_file` receipt for `sk_X`'s SKILL.md (or an existence check proving absence, for creates). Transcript quoting does not count — the receipt must be a dispatch.
- **Provenance sidecar, keyed by stable ID**: `created_by: agent | operator` lives in `.halbert-skill.json` beside SKILL.md, joined on `halbert.id` (a ULID stamped at create time) — **never inferred from location, never keyed by name**. A rename, a moved root, or an ecosystem pack that happens to collidingly share a name must not smuggle or forfeit provenance; name is mutable display data, the ID is the identity. One source of truth: the sidecar; the frontmatter `id` is only the join key.
- **Pins**: a foreground pin blocks deletes; an autonomous pin blocks *all* writes while any autonomous persona runs. Guest persona: the skill plane is fully read-only — a borrowed face does not edit the machine's instincts.
- **Archive-not-delete**: every curatorial mutation first tarballs the affected skills into `~/.config/halbert/skills/_archive/<date>-<nonce>.tar.gz` and records the archive path in the ledger row — rollback is mechanical, not forensic.
- **The `absorbed_into` guard** (lift verbatim; Hermes incident #29912 — an LLM archived active clusters with zero verified consolidations): a delete/archive is refused unless it carries `absorbed_into: sk_…` naming a **live, trusted** skill ID whose body verifiably contains the archived material (the curator performs a substring/paraphrase check before accepting).
- **Authoring-time description rejection**: >60 chars → the create tool errors, full stop (§1.2).

### 5.5 Agent-created lifecycle: draft → trusted

Agent-authored skills are born `state: draft`. A draft is visible **only to the custodian persona's catalog** and binds nothing; it is a proposal, not an instinct. Promotion to `trusted` requires the Verification runner below, a clean lint, and — for any skill declaring `safety`/`allowed_tools` — operator acknowledgment in the dashboard. Drafts that go 30 days without a single activation receipt are curator-archived automatically (§6 names telemetry the consumer).

### 5.6 The linter (calibrated)

A deterministic linter turns hoarding failure modes into machine checks (Hermes §5), extended with Halbert's own determinations: description >60 chars (authoring); missing `## Verification` on agent-authored skills; cross-reference/PR-style link density above threshold; >60 reference files; marketing words ("revolutionize", "seamless"); Determination banned terms (§4.3); `requires.env` naming secret-shaped variables without a quarantine declaration. Lint is advisory-to-blocking by state: blocking at create and promotion, informational on operator files.

### 5.7 The Verification runner — closing the Hermes gap

Hermes's SKILL.md carries a `## Verification` section **"but nothing executes it — Halbert's version should run it"** (Hermes review §5, the explicit gap). Design:

- **Contract**: a skill's `## Verification` section contains exactly one canonical fenced code block. The fence's first line is the command. One command, not a script — scripts live in `scripts/` and are *invoked by* the verification line.
- **The runner** (`skills/verification.py`): executes the command deterministically, once, in the most restrictive lane the terminal guard owns — scratch cwd, no network, output capped (head/tail), hard timeout, and the whole thing routed through the same tool lattice as any other command (write-plane rules, approval policy, guest-deny all apply; a verification run is command execution, not a special case). Exit 0 within timeout = pass; anything else = fail with the captured tail in the ledger.
- **When it runs**: at draft→trusted promotion, and re-run by the curator whenever the skill's `requires` verdict changes (a bin vanished from PATH ⇒ re-verify or drop to draft). The runner never runs *on catalog build* — verification is an event, not a render-time side effect.
- A skill with no `## Verification` section cannot be promoted by any party. Operator-authored bundled skills carry verification lines too; CI runs the runner over `skills/builtin/` so the contract stays honest from day one.

---

## 6. Usage telemetry — from day one, with a named consumer

Both reviews converge: OpenClaw §7 ("every tool call is matched against known SKILL.md paths → per-run skill-activation receipts … retrofitting is impossible") and Hermes §6 ("**build event tables with a named consumer, not as an archive**").

- **Seam 1 — reads**: `tools/executor.py`'s `_read_file` handler resolves each path against the registry's known skill paths (SKILL.md, references, scripts) before dispatch; a hit appends a receipt. This single choke point catches every Track-B consultation regardless of which surface asked.
- **Seam 2 — activations**: matcher/explicit activations are currently invisible durable-wise (logged at debug); promote them to the same table.
- **Table** `skill_events` (SQLite, alongside the conversation store — same durability rules as receipts): `ts, run_id, session_id, skill_id, persona, event ∈ {catalog_listed, matched, explicit, read, linted, verification_run, promoted, archived, absorbed}, detail_json`. Rows are keyed by **skill_id**, not name — the same identity discipline as provenance.
- **Consumers (named, not hypothetical)**: (a) the **curator** consumes read/match recency for stale→archive transitions and draft expiry; (b) the **learning loop** consumes per-turn receipts for counter reset; (c) the dashboard consumes counts for a skills panel — a table, not a chat transcript (the "memory is deliberately not chat-UI" directive applied to skills).
- Per-run receipts (`agents/receipt.py` lineage) embed the turn's skill receipts so a run is self-explaining: "turn used storage-ops (matched), zfs-snapshot-rollback (read)."

---

## 7. Packet series

Ordered so each packet lands independently green:

| packet | contents | depends on |
|---|---|---|
| **SK-1** Format & parser | namespaced `halbert:` frontmatter + compat reader; stable `id`; `requires` schema parse; reserved-name refusal; boundary-safe reads (realpath confinement, byte caps); retire `provider:model` passthrough; sidecar schema | none |
| **SK-2** Catalog & disclosure | `<available_skills>` renderer keyed to `snapshot_version`; cache-boundary assembly in `agent_prompts.py`; truncation ladder with identity floor; read-based consultation; `skill_events` table + read/activation seams (telemetry ships *with* the surface it measures); slash channel in intake | SK-1 |
| **SK-3** Persona scoping & custodians | persona root sets; custodian root + `kind: custodian`; Gather→Mutate→Repair→Prove→Report template; guest read-only skill plane; catalog filtering per persona | SK-2 |
| **SK-4** Capability gating | `requires` evaluation against `capabilities.py`/which/env/os; quarantined-secret vanish hook (lands dormant until the secrets subsystem names one); `halbert skills list --all` operator surface | SK-2 |
| **SK-5** Content security & linter | load-time markdown scanner; control-tag defang reuse; Determination banned-term enforcement at lint/parse/ingest; ecosystem-pack ingest with refusal reports | SK-1 |
| **SK-6** Learning loop | nudge counters in the state machine + rehydration; scheduler review job with dispatch-side whitelist; anti-hoarding prompt; read-before-write ContextVar; provenance sidecar writes; pins; archive + `absorbed_into` guard | SK-2, SK-5 |
| **SK-7** Curator & Verification runner | draft/trusted lifecycles; verification runner (scratch lane, one fenced command, lattice-routed); curator consuming `skill_events`; dashboard skills panel (table UI) | SK-6 |

**Open questions for the founder**

1. **Track-A body injection depth**: matched ops skills currently inject their body on both LLM calls of a turn. Keep capped injection (this design's default), or move ops bodies to disclosure too and trust the catalog? The former spends tokens for reliability; the latter makes safety-adjacent expertise model-optional. Recommend keeping injection for `priority: high/critical` only.
2. **Operator ack on promotion**: is a clean lint + passing verification enough to trust an agent-authored skill with no safety block, or does *every* promotion need a dashboard click? Design defaults to click only when the skill binds tools/safety.
3. **Ecosystem packs**: cloned into the user root (editable, updatable, must pass lint+Determination) or vendored read-only under a fourth root? Read-only vendoring is safer but breaks the "patch this session's skill first" ladder for pack skills.
4. **Voice**: should skill consultation be audible ("checking my notes on storage") via the observation/attunement surface, or silent? **[D-1]** also owns whether skill receipts appear in branch summaries.
5. **`extends` for ecosystem skills**: keep Halbert-native only (current), or honor it across pack boundaries? Cross-pack inheritance is a supply-chain lever; recommend refusing `extends` that crosses a root boundary.

**[D-1] reconciliation points**: tool-row rehydration of nudge counters (§5.1); prompt-cache boundary and what compaction must preserve (§2.2 — a compacted session re-renders the catalog at the *recorded* snapshot version or deliberately re-renders and records the bump; D-1 decides, skills supplies the version); slash-command surface (§2.4); skill receipts in branch summaries (Q4).
