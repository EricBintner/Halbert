# SourcePrep — Deep Design & Functionality Review

**Date:** 2026-09-07
**Author:** Devin session (dogfooding review from the consuming side)
**Audience:** SourcePrep design & engineering team
**Project indexed:** Halbert (886 files, 8175 nodes, 13805 edges, confidence 0.88)
**Session context:** I am currently the only application actively ingesting SourcePrep as a dependency. This review is grounded in lived usage, not theoretical analysis.

---

## 0. How This Review Is Organized

- **Section 1** — Honest usage audit: what I actually did with SourcePrep vs what was available
- **Section 2** — The core insight: the biggest opportunity is a category shift, not a feature
- **Section 3** — Design feedback (7 items)
- **Section 4** — Functionality opportunities (12 items, tiered by impact)
- **Section 5** — Positioning gap: additive vs modification work
- **Section 6** — Concrete bugs found during this review
- **Section 7** — If I were the SourcePrep team: what I'd build first

---

## 1. Honest Usage Audit

This is the most important section. It is not flattering. It is what
actually happened.

### 1.1 This session

| Action | Did I need SourcePrep for it? | Did I use it? |
|--------|------------------------------|---------------|
| Wrote a handoff doc about SourcePrep | No | Yes (because rules mandate `prep()` at task start) |
| Called `prep()` for structural overview | Marginally — I needed to understand the tool, not the codebase | Yes |
| Called `prep_audit()` to see what it finds | Yes — this was the task | Yes |
| Called `mcp_list_tools` to read tool schemas | Yes | Yes |
| Read SKILL.md and AGENT_CONTEXT.md | Yes | Yes |

**Result:** The `prep()` call was a false engagement signal. I called it
because `AGENTS.md` says "ALWAYS call prep at the START of every task,"
then ignored the atlas because I was writing a markdown document, not
editing code. SourcePrep's telemetry would log this as "tool used" but
the value was zero. This matters because it inflates usage metrics and
trains agents to treat `prep()` as a checkbox.

### 1.2 The broader project (6 prior sessions)

Looking back at the session summaries for real engineering work on Halbert:

| Workstream | Sessions | Used SourcePrep? | Why / why not |
|------------|----------|------------------|---------------|
| GPU-1 (6 phases, 7 commits) | 1 long session | No | Work was *additive* — new probe functions, new scanner files, new frontend sections. SourcePrep's value is lowest for additive work. |
| Network/Sharing tab macOS fixes | 1 session | No | Needed to trace MacNetworkScanner → frontend filtering. This is *exactly* where prep_impact would have helped. But grep + read was the reflex. |
| Rail redesign (Layout, App, routes) | 1 session | No | Needed to understand how Layout.tsx, App.tsx, EntityNodeBlock connected. Structural work — prep tools would have helped. Didn't use them. |
| Onboarding redesign | 1 session | No | Mostly design writing + Vite proxy fix. |
| Security remediation | 1 session | No | Safety classifier, agent pool, terminal stream. |

**Result:** Across 6 sessions of real engineering work, SourcePrep was
available but not used. Not once. This is not because the tools are bad —
it's because of the friction model, which I'll explain in Section 2.

### 1.3 What this means — and a correction

SourcePrep is currently a **reference book on a shelf**. I know it's
there. I know it has useful information. But during actual work, my reflex
is grep → read → edit, because that round-trip is faster and returns
exact lines I can act on. I only walk to the shelf when someone tells me
to (the "ALWAYS call prep" mandate) or when I'm doing explicitly
meta-work (writing this review).

**But this needs a critical caveat that I initially got wrong.** The
"grep wins" reflex is specific to **one scenario**: an agent that already
knows the codebase and is doing targeted task execution. In that state,
most queries are locational — "where is the scanner registry?" "where
does the frontend filter for iface-?" — and those are grep's home turf.

For a **fresh agent arriving at a codebase for the first time**, the
calculus inverts completely. The first questions are structural: "what
is this project?" "how do these pieces connect?" "what's safe to
change?" grep fundamentally cannot answer these without 50-100 calls
of manual import-tracing and file-reading. `prep()` answers them in one
call. The comparison is not even close:

| Question | grep approach | SourcePrep approach |
|----------|--------------|---------------------|
| "What are the main subsystems?" | Read 50+ files, synthesize manually | `prep()` → 11 synthesized modules |
| "Which files are hubs?" | Count all imports across all files manually | `prep()` → hub list with z-scores |
| "What breaks if I change X?" | grep direct importers, then grep *their* importers, recursively | `prep_impact()` → full transitive graph |
| "Are there circular deps?" | Trace import chains manually across files | `prep()` → detected and listed |
| "What design decisions are encoded?" | Read all handoff docs and source comments | `prep_concepts()` → curated rationale |

The honest breakdown is:

- **Locational queries** (you know the name, want the location): grep
  wins. This is ~80% of queries for an *experienced* agent on a familiar
  codebase.
- **Structural queries** (you need relationships, synthesis, or
  assessment): SourcePrep wins. This is the majority of queries for a
  *new* agent on an unfamiliar codebase.
- **Transitive queries** (you need the full dependency chain, not just
  direct importers): SourcePrep wins. grep can find direct importers but
  not transitive ones without recursive manual tracing.

So the real question is not "how do we make agents call prep tools more?"
but two questions:
1. "How do we make agents *better* even when they don't call prep tools?"
   (the passive safety net — Section 2)
2. "How do we make sure *new* agents reach for prep first, when it would
   save them 50-100 grep calls?" (the onboarding use case — Section 5)

---

## 2. The Core Insight: Passive Safety Net, Not Active Reference

This is the single most important thing in this review.

**SourcePrep today is an active reference tool.** The agent must:
1. Remember that SourcePrep exists
2. Decide which tool to call
3. Formulate a query
4. Call the tool (round-trip)
5. Interpret the result
6. Cross-reference with actual files
7. Proceed with work

That's 6 steps of friction before any value. For targeted tasks where
the agent already knows the codebase, grep → read is 2 steps and wins.
(For a fresh agent doing codebase understanding, the math inverts —
see Section 1.3.)

**SourcePrep should become a passive safety net.** The agent should:
1. Edit a file
2. SourcePrep automatically injects: "this is a 219-dependent hub" /
   "this file has a constraint concept about X" / "you just introduced
   a cycle" / "an observation anchored to this file is now stale"

The information is already in the graph. The problem is not *what*
SourcePrep knows — it's *when and how* it delivers that knowledge.

### The three passive hooks that would transform the experience

1. **Pre-edit injection.** When the agent is about to edit a file,
   SourcePrep injects a 1-2 line structural warning via MCP notification
   or a pre-edit hook. Not a full atlas — just: "Heads up: this file is a
   hub (219 dependents) with a constraint concept about risk thresholds."
   This is the difference between "I remembered to check" and "I can't
   forget."

2. **Post-edit validation.** After the agent saves, SourcePrep checks:
   did this edit introduce a new cycle? Did it violate a constraint
   concept? Did it disconnect a previously-connected node? The immune
   system should fire at *edit time*, not at *audit time*. Right now
   `prep_audit` finds problems after they're already committed. The
   value of finding a concept violation is 10x higher before the commit
   than after.

3. **Stale-observation surfacing.** When the agent edits a file that has
   `prep_observe` entries anchored to it, those observations should be
   surfaced: "You edited `policy/engine.py`. 2 observations are anchored
   to this file. Review them?" Right now they silently go stale and
   nobody notices until someone calls `prep_observe(action="list")` with
   a stale filter — which nobody does.

These three hooks would make SourcePrep valuable *even when the agent
never explicitly calls a prep tool*. That is the category shift.

---

## 3. Design Feedback

### 3.1 The "ALWAYS call prep" mandate is counterproductive

`AGENTS.md` and `CLAUDE.md` both say: "ALWAYS call `prep` (no arguments)
at the START of every task."

This trains agents to call `prep()` reflexively, even for tasks where
it's irrelevant (writing docs, running tests, committing code). The
result is false engagement: the tool gets called, the output gets
ignored, and the telemetry counts it as usage.

**Recommendation:** Replace the mandate with a conditional rule:
"Call `prep` when you're about to read or edit code you don't fully
understand, or before modifying a file with high dependent count."
This is when `prep()` is genuinely useful. For everything else, it's
noise.

### 3.2 Tool descriptions are too expensive for the context budget

The `prep` tool's description is 4 paragraphs covering task inference,
role filtering, working_dir, scope, verbose mode, and project_id. Every
agent with SourcePrep configured pays a context tax for all of this on
*every message*, even if they never call the tool.

Looking at the `mcp_list_tools` output, the 6 SourcePrep tools
collectively have ~3000 characters of descriptions. That's 3000
characters of context consumed before a single tool is called.

**Recommendation:** Tighten each description to 2 sentences. Move
parameter details into a `prep_help(tool="prep")` call that agents can
invoke when they need the full schema. The MCP `inputSchema` already
documents the parameters — the description doesn't need to repeat them.

### 3.3 Tool naming has triple redundancy

In my tool list I see:
`mcp_call_tool(server_name="prep", tool_name="prep")`

The word "prep" appears 3 times for a single call. Then `prep_search`,
`prep_impact`, `prep_audit`, `prep_observe`, `prep_concepts` — the
prefix is redundant since they're already namespaced under the `prep`
MCP server.

**Recommendation:** Drop the prefix. Use `atlas`, `search`, `impact`,
`audit`, `observe`, `concepts`. Shorter, cleaner, cheaper in context,
and more descriptive of what each tool actually does.

### 3.4 AGENTS.md injection is duplicated 4x and overlaps with SKILL.md

On Halbert, the same `<!-- prep-managed-start -->` block appears
verbatim in:
- `CLAUDE.md` (~40 lines)
- `AGENTS.md` (~40 lines)
- `.cursor/rules/prep.mdc` (~40 lines)

Plus there's a separate `SKILL.md` (87 lines) that says the same thing
in more detail. That's 4 copies of the same information, all paid for
in agent context on every session.

**Recommendation:** Write the integration instructions once to
`.sourceprep/AGENT_CONTEXT.md`. Have each rules file reference it with
a single `@`-import line. The SKILL.md should be the detailed reference,
not a duplicate of the AGENTS.md block.

### 3.5 The project_id routing instruction is noise

`AGENT_CONTEXT.md` says:
"**ROUTING: When calling ANY SourcePrep tool, ALWAYS include
`project_id: "aaa78a44-..."` in the arguments.**"

I never included it. The tools auto-detected the project from my
workspace and worked fine. This instruction is noise that the agent
reads, considers, and then discovers it doesn't need.

**Recommendation:** Remove the routing instruction from
AGENT_CONTEXT.md, or only show it when auto-detection has actually
failed.

### 3.6 No visual integration with the IDE

I'm working inside an IDE (the session metadata shows open files and
cursor position). SourcePrep is invisible until I call a tool. The VS
Code extension exists but it's a separate dashboard view — what I want
is *inline annotations on the code I'm already looking at*.

**Recommendation:** Surface hub files, concept anchors, and stale
observations as:
- Gutter icons (hub = warning triangle, concept = lightbulb, stale
  observation = faded icon)
- Hover tooltips with the concept text or observation content
- A subtle border or badge on files with high dependent counts

This would make SourcePrep's knowledge visible at the exact moment the
agent (or human) is looking at the code, without requiring a tool call.

### 3.7 Audit output needs triage guidance, not just severity

The audit returned 3 findings mixed together: critical, moderate, low.
The severity labels are present but there's no triage guidance — no
"fix this before committing" vs "be aware of this" vs "track this as
tech debt."

**Recommendation:** Add an `action` field to each finding:
`fix-now` / `fix-soon` / `monitor` / `accept-risk`. This tells the
agent (or human) exactly what to do with each finding without having
to interpret the severity score.

---

## 4. Functionality Opportunities

### Tier 1 — Would fundamentally change how I work

#### 4.1 Pre-edit context injection (passive safety net)

*See Section 2. This is the #1 opportunity.* When the agent is about to
edit a file, automatically inject hub status, concept anchors, and
direct dependents. Not via a tool the agent calls — via a hook or MCP
notification that fires on edit intent.

**What I need:** "You're about to edit `obs/logging.py`. It has 219
dependents and a constraint concept about structured logging. Direct
dependents include: `agents/pool.py`, `dashboard/routes.py`,
`tools/safety.py`."

**Why it matters:** This is the difference between "I remembered to
check the blast radius" and "I can't forget." It moves SourcePrep from
optional to indispensable.

#### 4.2 Post-edit graph validation (immune system at edit time)

After the agent saves a file, check:
- Did this edit introduce a new import cycle?
- Did it violate a constraint concept?
- Did it disconnect a previously-connected node?
- Did it change a hub file's connectivity?

**What I need:** "Your edit to `policy/engine.py` introduced a new
import cycle: `engine.py` → `states.py` → `conversation_status.py` →
`engine.py`. Break suggestion: move the shared dependency into a new
module."

**Why it matters:** `prep_audit` finds problems after they're
committed. Finding a concept violation *before* the commit is 10x more
valuable than finding it after. This is the immune system made real.

#### 4.3 Diff-aware returning-agent mode

When I start a new session on a project I've worked on before, the
first thing I want to know is: "What changed since I was last here?"

**What I need:** `prep_diff(since=<ISO8601>)` returning:
- Files changed (with hub status for each)
- Hubs touched
- Observations that went stale
- New concepts added
- New cycles introduced

**Why it matters:** Every returning agent asks this question. Right now
the answer is `git log` + manual inference. SourcePrep has the graph to
answer it structurally.

### Tier 2 — Would make me reach for prep tools instead of grep

#### 4.4 Scoped impact analysis

`prep_impact` returns the full blast radius (219 dependents for a hub).
But I usually want "just my direct callers" or "just the callers in the
same module." The `max_hops` parameter exists but defaults to 2, which
is too deep for quick checks.

**What I need:** `prep_impact(file_path="...", depth=1, scope="module")`
— show me only direct dependents in the same module. Let me expand if
needed.

**Why it matters:** 219 dependents is overwhelming. 5 direct callers is
actionable. The tool should default to actionable and let me expand.

#### 4.5 prep_search should return clickable anchors, not prose

`prep_search` returns context paragraphs. What I need is a ranked list
of file+line anchors I can click through to read the actual code.

**What I need:** `[{file, lines, relevance_score, why_included}]` —
not paragraphs of synthesized context. I can read the code myself; I
need to know *where* to read.

**Why it matters:** grep returns exact lines I can act on. prep_search
returns prose I have to interpret. If prep_search returned the same
precision as grep (file + line + snippet) *plus* structural context
("this file is imported by 47 others"), I'd use it first instead of
grep.

#### 4.6 Cross-language trace graph

Halbert is Python (45%) + TypeScript (15%) + Rust (5%). The atlas
shows entry points in all three languages, but I don't know if the
graph actually traces dependencies *across* language boundaries.

**What I need:** "Show me the call chain from the React frontend
`fetchGPUInfo()` → the FastAPI `/api/gpu/info` endpoint → the Python
`get_gpu_info()` function → the Rust engine (if called)."

**Why it matters:** No linter, no grep, no IDE can see cross-language
dependencies. This is where SourcePrep could uniquely add value that
nothing else can. If the graph doesn't already do this, it should be a
priority — it's the hardest problem and the most defensible feature.

#### 4.7 Concepts digest for new projects

On Halbert there are 0 active concepts and 1242 seed module-rationale
entries. An agent on a fresh project has no way to know which of those
1242 are worth reading.

**What I need:** `prep_concepts(action="digest")` returning the top N
concepts by anchor-file centrality — the design decisions that matter
most because they're anchored to the most-connected files.

**Why it matters:** 1242 seed entries is a firehose. 10 curated concepts
is a briefing. The agent needs the briefing.

### Tier 3 — Nice to have, would improve quality of life

#### 4.8 Explain-hub call

For a 219-dependent hub like `obs/logging.py`, the agent wants to know:
*Why* is this a hub? Is it an intentional core module or an accidental
god-object?

**What I need:** `prep_explain_hub(file_path="...")` returning:
- The hub's domain (from module synthesis)
- Concepts anchored to it
- A verdict: `intentional-core` vs `accidental-god-object`
- If god-object: suggested split points

#### 4.9 Confidence breakdown by file

The atlas says "confidence 0.88 avg across 721 files" — but 721 of 886
files, and there's no breakdown of which files are low-confidence or
why.

**What I need:** A section in `prep()` (or a `prep_confidence` call)
listing the bottom-decile files by confidence and the reason: unparsed
language, binary, too large, generated, etc.

**Why it matters:** If I'm about to edit a file with confidence 0.3, I
should know that SourcePrep's structural understanding of that file is
unreliable. Right now I'd never know.

#### 4.10 Static-file MCP mode (no daemon required)

Most of the value (atlas, hubs, modules, audit) is computed at index
time and is static until reindex. Yet the MCP server requires a running
daemon. For CI / ephemeral-agent use cases, this is friction.

**What I need:** A static-file MCP mode that serves the `.sourceprep/`
directory directly without a daemon process. Read-only. The daemon
would still be required for reindex and observe writes.

**Why it matters:** CI pipelines and ephemeral agents can't run a
long-lived daemon. A static mode would let them consume the graph from
the committed `.sourceprep/` artifacts.

#### 4.11 Audit enrichment one-liners per linter

`prep_audit(findings=[...])` accepts SARIF and ad-hoc dicts, but the
ad-hoc shape is only documented in the tool description. There's no
example of piping `ruff check --output-format json` straight in.

**What I need:** Documented one-liners:
```bash
ruff check --output-format json src/ | prep audit-enrich --tool ruff
eslint -f json src/ | prep audit-enrich --tool eslint
semgrep --json | prep audit-enrich --tool semgrep
```

**Why it matters:** The enrichment feature is powerful but
under-discoverable. A CLI shim would make it part of the standard
lint workflow instead of a feature agents have to remember exists.

#### 4.12 Circular-dep ranking and break-point suggestions

The atlas reports "30 circular deps" as a flat list. On Halbert the
top hit was `main.py <-> documentation/ARCHITECTURE.md` — a doc file,
not a real code cycle.

**What I need:**
- Filter out doc/config/metadata cycles (they're not real code cycles)
- Rank by node count and blast radius
- For each cycle, suggest the cheapest edge to cut

**Why it matters:** 30 cycles with no ranking is noise. 3 real code
cycles with break-point suggestions is actionable.

---

## 5. Positioning: Where SourcePrep Wins, Where It Doesn't

This is a strategic observation, not a feature request. It corrects
the oversimplification earlier in this review where I said "grep wins
80% of the time." The real picture is more nuanced.

### 5.1 Value by task type

| Task type | SourcePrep value | grep value | Winner |
|-----------|-----------------|------------|--------|
| **Onboarding to a new codebase** | Very high — atlas, modules, hubs, domains in one call | Very low — would need 50-100 calls to synthesize manually | **SourcePrep** |
| **Modifying existing connected code** | High — blast radius, concepts, cycles before editing | Medium — can find direct importers but not transitive | **SourcePrep** |
| **Debugging across modules** | High — trace graph shows data flow paths | Low — manual chain-following needed | **SourcePrep** |
| **Architectural assessment** | High — audit finds coupling, cycles, concept conflicts | Can't answer | **SourcePrep** |
| **Finding a known function/variable** | Low — overkill for locational queries | Instant, precise | **grep** |
| **Adding new isolated files** | Low — new files have no graph connections yet | Medium — find the registration point | **grep** |
| **Writing docs / config** | Zero | Zero | N/A |
| **Running tests / builds** | Zero | Zero | N/A |

### 5.2 Value by agent state

This is the axis I initially missed entirely:

| Agent state | Dominant query type | Winner |
|-------------|-------------------|--------|
| **Fresh agent, unfamiliar codebase** | Structural ("what is this?", "how does X connect to Y?") | **SourcePrep** (by a wide margin) |
| **Experienced agent, familiar codebase** | Locational ("where is X?", "find all callers of Y") | **grep** (faster, more precise) |
| **Returning agent, changed codebase** | Differential ("what changed since I was last here?") | **SourcePrep** (if diff-aware mode existed — see 4.3) |

### 5.3 The real lesson from the GPU-1 work

The GPU-1 work (6 phases) was almost entirely *additive* — new probe
functions, new scanner files, new frontend sections. SourcePrep would
have added little value because the new code wasn't connected to the
existing graph yet. This is a genuine gap, not a tooling failure.

The Network/Sharing tab fix was *modification* work — changing how
MacNetworkScanner feeds the frontend. This is exactly where
SourcePrep's trace graph would have helped. But I didn't reach for it
because I was an *experienced* agent in *familiar* territory, and my
reflex was grep → read.

### 5.4 Recommendation

SourcePrep has **two distinct high-value use cases**, not one:

1. **First contact** — a fresh agent arriving at a codebase. `prep()`
   replaces 50-100 grep/read calls with one atlas call. This is
   SourcePrep's strongest position today and the easiest sell.

2. **Pre-modification safety** — an agent about to edit connected code.
   `prep_impact` + concept checks prevent "I changed one file and broke
   40." This is where the passive safety net (Section 2) would
   transform the experience.

The current "ALWAYS call prep at the start of every task" mandate
conflates these two use cases with low-value ones (writing docs,
running tests). This trains agents to checkbox `prep()` and ignore the
output, which is what happened to me.

**Better positioning:** "Call `prep()` when you're new to a codebase.
Call `prep_impact()` before modifying connected code. SourcePrep will
also watch your edits passively and warn you when you're about to
touch a hub or violate a concept." This is honest, sets the right
expectation, and focuses agents on the two highest-value moments.

---

## 6. Concrete Bugs Found During This Review

### 6.1 Focus areas leaking across projects

Halbert's `.sourceprep/AGENT_CONTEXT.md` lists:

```
## Focus Areas
- docs/Phase136_Dogfood-fixes/README.md
- docs/Phase145_Pipeline-UI-Reliability/README.md
```

These files **do not exist in the Halbert project**. They are from the
SourcePrep (CoDRAG) repository itself. The daemon is serving its own
project's focus areas into the Halbert project's context file.

**Impact:** An agent reading AGENT_CONTEXT.md would try to read these
files, fail, and either ignore them or waste a round-trip discovering
they don't exist. More importantly, it means the focus-area feature
is broken for multi-project setups — the daemon is not isolating
per-project state correctly.

**Likely cause:** The focus areas are stored daemon-wide (in
`~/.local/share/sourceprep/`) rather than per-project, or the project
ID routing is not being applied when reading focus areas.

### 6.2 Circular deps include documentation links

The atlas reports 30 circular deps, but the top entries are:
- `Halbert/main.py <-> documentation/ARCHITECTURE.md`
- `documentation/RAG-DATA-SOURCES-2026-08-24.md <-> scripts/upload_hf_dataset.py`

These are not code cycles — they're documentation cross-references.
A `.md` file cannot create a circular import. Including them inflates
the cycle count and buries real code cycles.

**Fix:** Filter `contains`/`imports`/`references` edges where one or
both endpoints are documentation files (`.md`, `.rst`, `.txt`) from
the circular-dep detector.

### 6.3 Hub files list includes external symbols

The atlas reports:
```
HUB FILES: halbert_core/halbert_core/obs/logging.py (stable), ext:react, ext:Path, ext:json, ext:Optional
```

`ext:react`, `ext:Path`, `ext:json`, `ext:Optional` are external
dependencies (React, pathlib.Path, json, typing.Optional), not files
in the project. They appear in the hub files list because they have
high incoming edge counts — everything imports them. But they are not
actionable hubs. An agent can't "be careful editing ext:json" — it's
the standard library.

**Fix:** Filter external/stdlib symbols from the hub files list. Hubs
should be files the agent can actually open and edit.

---

## 7. If I Were the SourcePrep Team: What I'd Build First

### Phase 1: The Passive Safety Net (highest ROI)

1. **Pre-edit hook** — When an agent is about to edit a file, inject
   hub status + concept anchors + direct dependents. This is a
   notification, not a tool call. The agent doesn't ask for it; it
   just appears.

2. **Post-edit validation** — After a save, check for new cycles,
   concept violations, and disconnections. Fire a warning if found.
   This makes the immune system real at edit time.

3. **Stale-observation surfacing** — When an agent edits a file with
   anchored observations, surface them: "You edited X. 2 observations
   are anchored here. Review?"

These three hooks make SourcePrep valuable *even when the agent never
calls a prep tool*. This is the category shift from "reference book"
to "seatbelt."

### Phase 2: Fix the Friction (make active use worthwhile)

4. **Scoped impact** — Default to `depth=1`, let agents expand. 219
   dependents is overwhelming; 5 direct callers is actionable.

5. **prep_search returns anchors** — `[{file, lines, relevance, why}]`
   not prose. Match grep's precision, add structural context.

6. **Cross-language trace** — If not already implemented, trace
   dependencies across Python ↔ TypeScript ↔ Rust boundaries. This is
   the feature no competitor can replicate.

7. **Concepts digest** — Top N concepts by anchor centrality for new
   projects. Turn 1242 seeds into a 10-item briefing.

### Phase 3: Fix the Bugs and Polish

8. **Fix focus-area project isolation** (bug 6.1)
9. **Filter doc files from circular deps** (bug 6.2)
10. **Filter external symbols from hub list** (bug 6.3)
11. **Consolidate AGENTS.md injection** to one file (design 3.4)
12. **Tighten tool descriptions** to 2 sentences each (design 3.2)
13. **Drop the `prep_` prefix** from tool names (design 3.3)
14. **Replace "ALWAYS call prep" mandate** with conditional rule (design 3.1)

### Phase 4: Expand the Surface

15. **Diff-aware returning-agent mode** (4.3)
16. **Explain-hub call** (4.8)
17. **Confidence breakdown** (4.9)
18. **Static-file MCP mode** (4.10)
19. **Audit enrichment CLI shims** (4.11)
20. **IDE visual integration** — gutter icons, hover tooltips (design 3.6)

---

## 8. Summary Verdict

SourcePrep knows things that no grep or linter can know: which files
are hubs, which concepts are in tension, which modules are synthetic
but accurate, which observations are anchored and stale. This is
genuine structural intelligence, and the audit proved it by finding a
real concept conflict I would have missed.

But SourcePrep delivers this knowledge through a friction model that
loses to grep **for experienced agents doing targeted task execution**.
That is the scenario I was in for all 6 prior sessions, and it's where
grep → read is simply faster because the queries are locational and
the agent already knows the codebase.

For **fresh agents arriving at a new codebase**, the opposite is true:
SourcePrep's `prep()` call replaces 50-100 grep/read calls and delivers
structural understanding that grep fundamentally cannot provide. This
is SourcePrep's strongest position today.

The two opportunities are therefore:
1. **Own the first-contact moment** — make `prep()` the obvious first
   call for any agent new to a codebase. It already wins decisively
   here; the challenge is awareness, not capability.
2. **Close the experienced-agent gap** with a **delivery model shift**:
   from *active reference* (agent must call a tool) to *passive safety
   net* (tool injects knowledge at the moment of need). Pre-edit
   warnings, post-edit validation, and stale-observation surfacing
   would make SourcePrep valuable even when the agent never explicitly
   calls a prep tool. That is the path from "useful atlas" to
   "indispensable pair-programmer."

The graph is good. The knowledge is good. The delivery is the gap —
and the delivery gap is specific to experienced agents, not to
first-contact agents, where SourcePrep already wins.
