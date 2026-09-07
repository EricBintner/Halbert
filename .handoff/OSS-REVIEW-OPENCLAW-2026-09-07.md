# OSS Review: OpenClaw — patterns, code, and workflows worth learning from or lifting

**Date:** 2026-09-07
**Source reviewed:** `/Volumes/Thunderbolt/AI/openclaw` (note: sibling of the `OSS/` folder, not inside it)
**Version reviewed:** `2026.9.2` at `3f3c5b2ebef` ("release-publish/d0c0a2c229b0-1788632460-1440-g3f3c5b2ebef")
**Method:** Eight parallel deep-dive reviews across the whole monorepo: agent runtime/sessions, memory, skills/prompt assembly, security/approvals, channels/routing/multi-user, tools/cron/terminal, gateway/daemon/MCP/lifecycle, models/voice/UI. Each briefed on Halbert's current state and asked for learn/lift verdicts with file-level evidence.
**Follows:** the open-claude-code review pass. Same intent — learn from their patterns, work anything useful into our needs.

---

## What OpenClaw is (framing)

A personal AI assistant gateway: TypeScript pnpm monorepo, MIT, run by a foundation. "Your assistant, on your devices, in your chats." Its stated architecture case is **"trusted gateway, untrusted execution, deterministic policy"** — which is nearly word-for-word Halbert's security posture (deterministic policy, never LLM-based gating, redaction at a choke point). That alignment is why so much here is liftable: they solved the same problems a personal-machine assistant hits, with the same distrust of LLM judgment in security paths.

Scale note: this is a much larger project than open-claude-code (~1,400 files in `src/gateway` alone). Much of its bulk exists because it is multi-provider, multi-channel, multi-process, multi-platform. **Halbert should lift the contracts and invariants, not the indirection.** Every area report included anti-pattern warnings; they are collected at the bottom.

---

## Ranked verdict: what to lift, by Halbert workstream

### 1. Memory / continuity (memory_v2's "91% unwired" problem) — the single biggest win

OpenClaw's memory is: plain Markdown files + one SQLite index (FTS5 + sqlite-vec) + a background consolidation pass ("dreaming"). Five stated design rules, all of which Halbert should adopt verbatim: no hidden state (memory is files you can edit), **writing is the hard part** (they cite LongMemEval — what gets written matters more than how it's indexed), the write path is the security boundary, deterministic gates with model judgment only inside them, and **memory failures never eat a turn**.

The structural idea: **two tiers, promotion as the only bridge.**
- **Curated core** (`MEMORY.md`/`USER.md`, ~10KB budget) — small, always injected into context.
- **Episodic tier** (daily notes + indexed session transcripts) — lossless, append-only, *never auto-injected*, reachable only via explicit search or escalation.
- Nothing crosses episodic → curated except promotion gates.

The pieces that answer Halbert's three open wiring questions:

**When to write** — not per turn. Three hooks:
1. *Pre-compaction flush* (`extensions/memory-core/src/flush-plan.ts`): when the context window nears compaction, a silent flush turn runs first ("store durable memories only in the daily note… APPEND new content only"), so compaction can never erase unwritten facts.
2. *Session-end capture* (`src/hooks/bundled/session-memory/`): last N messages persisted at reset/idle/daily-rollover boundaries.
3. *Transcript ingestion*: every ended session becomes searchable corpus regardless — lossless episodic evidence by default, curation left to the consolidator.

**When to recall** — a two-lane design (`extensions/active-memory/`):
- *Lane 1, every turn, zero model calls:* lexical-only trigger matching against the **curated tier only** (trigger phrases stored as HTML comments on entries; threshold 0.65 with the calibration reasoning written in a comment). Daily notes/transcripts never auto-inject regardless of match strength — "a security property, not a tuning choice."
- *Lane 2, escalation only:* a battery of recall-intent regexes ("~15 English + CJK patterns with future-vs-retrospective disambiguation") decides when a real retrieval subagent is worth the latency. The subagent must reply with a compact note "about the user, not a reply to the user," or `NONE`.

**What earns durability** — the distinctive piece: recall-driven promotion (`extensions/memory-core/src/short-term-promotion*.ts`). Every recall records signals (count, query-hash diversity, multi-day recurrence, scores, a content-hash `claimHash` so the same claim converges). A deterministic ranker promotes only chunks that kept being *useful*. **Memory graduates because it was useful, not because it was written confidently.** This is the missing wire between Halbert's recall, decay, and consolidator: run the consolidator over the top-ranked claims, not "everything." Decayed-but-repeatedly-recalled items re-earn prominence — decay gets a second life.

**How to consolidate safely** (`extensions/memory-core/src/dreaming-consolidation.ts`): the model never rewrites the file. It returns a strict JSON *plan* — `{action: added|merged|superseded, priorEntries: exact text}` — the host supplies new entry text deterministically, a validator checks every prior entry exists exactly once / merges are between normalized-identical facts / supersessions have lineage keys, and any failure falls back to **append-only for that sweep** (never data loss). This makes hallucinated deletions structurally impossible.

**Recall-loop hygiene** (adopt from day one, retrofit is impossible): strip previously injected memory blocks from recall queries; mark recalled-derived entries and exclude them from promotion ("a fact recalled a hundred times stays one fact"); classify provenance (owner/agent/untrusted/system) in SQLite columns at write time, never in prose; untrusted origins are blocked from promotion *before scoring* — "no amount of recall frequency promotes untrusted content."

**Presentation** — recalled memory is injected as a hidden prepended context block, never chat items; per-session structured status lines feed any UI affordance. And when recall *fails*, it still injects "memory could not be retrieved this turn — do not assume no relevant memory exists" (negated-abstention). Halbert's dashboard gets memory visibility from a small append-only event journal (`recall.recorded`, `promotion.applied`) it can tail — no chat-history UI needed.

Also worth stealing: the **decay refinements** — decay is a *ranking* multiplier that never deletes; evergreen paths (curated core, undated files) are exempt; timestamps derive from artifact naming/mtime. And the whole "vector KNN in a killable read-only subprocess" pattern (`PRAGMA query_only`, stdin/stdout JSON, hard timeout) for the crashiest dependency in Halbert's stack.

Fast path if the full design is too much: `extensions/memory-lancedb/auto-recall.ts` is the minimal version — "a weekend of Python" to get Halbert from ~9% to ~60% wired, with the promotion machinery as the upgrade path.

### 2. Continuous conversation / hidden topic threads

The transcript is an **append-only tree**; context is a projection of a path (`packages/agent-core/src/harness/`). Node types: message, custom_message, model_change, compaction, reset, branch_summary, label…; a `leaf` entry points at the current position. This is the exact data model for "one continuous conversation, hidden topic threads, recall by relevance, no conversation list":
- Each topic thread is a branch; switching topics moves the leaf.
- Returning to a topic generates a **branch summary once**, persisted as an entry (free on subsequent visits): "The user explored a different conversation branch before returning here."
- `excludeFromContext` on messages separates "what the dashboard shows" from "what the model sees."
- Nothing is destroyed; history is append-only, context derived.

Compaction (`packages/agent-core/src/harness/compaction/`) is the most complete portable subsystem in the repo, and Halbert's single continuous conversation hits this wall first: cut points only at turn boundaries (never between an assistant message and its tool results), iterative structured summaries (Goal / Constraints / Progress / Decisions / Next Steps, "preserve exact file paths and error text"), file-operations extracted from tool results and carried across compaction *generations*, the `latestUnresolvedUserRequest` carried forward so mid-request compaction can resume the ask, and a binary-searched summary size that fits the remaining budget. Pure functions, directly portable to Python.

Steering: the two-queue system (`PendingMessageQueue` in `packages/agent-core/src/agent.ts`) — steering messages inject mid-run before the next unstarted tool (unstarted tools get a synthetic "skipped due to queued user message"), follow-up messages drain only when the run would otherwise stop, and drained-but-uncommitted messages have `inFlight → commit → restore` tri-state so a failed run puts them back at the queue head. This is the mechanism for "user typed while the agent was mid-plan" without forking the conversation. (OpenClaw also has a live-stream injection layer; Halbert needs only the checkpoint level.)

Crash-proofing the conversation: interruption is persisted as transcript *facts* (a canonical aborted-assistant record + a guidance custom-message "tools may have partially executed"), not runtime state — so the next run, possibly a new process, knows the turn was cut short. A typed `turnHandoff` abort reason skips the scary guidance for intentional state transitions (Halbert's PLAN→AWAIT_APPROVAL should use exactly this). Stranded tool calls get synthetic missing results via a pure occurrence-queue pairing classifier — no reordering, no rewriting persisted bytes. Schema versioning: one `PRAGMA user_version` integer per SQLite file, an idempotent gated migration ladder, and **hard refusal on future-version files** (critical for a Tauri app where the app can downgrade but data stays) — an afternoon of work, permanent payoff.

### 3. Guest persona / permission-and-consent system

Multiple directly liftable mechanisms, in rough priority:

- **The two-axis lattice** (`src/infra/exec-approvals-core.ts`): every policy is `security: deny|allowlist|full` (capability) × `ask: off|on-miss|always` (consultation). Layers merge with `min()` over capability and `max()` over ask — strictest capability and most prompting always win; "full/off" (YOLO) requires every layer to agree. **Guest becomes `minSecurity(guest, anything) == deny` — a capability floor, not a special-cased persona**, so guest + any session override still equals deny. Halbert's `has_capability()` registry should expose exactly this lattice merge.
- **Admission as a named-gate decision graph** (`src/channels/message-access/decision.ts`): ordered gates (route → sender → command → event → activation), each producing a record with `effect`, `reasonCode`; the final decision names its `decisiveGate`. Halbert should have one `decide_ingress()` returning `(admission, decisive_gate, reason_code, graph)` — "execute-level deny" becomes a gate with a reason code, and every deny is explainable after the fact.
- **Identifier-authentication strength ladder** (`identifier-authentication.ts`): `verified(3) > asserted(2) > unverified(1) > mutable(0)`, with a per-channel minimum floor. This directly answers the "no name tiers in `resolve_entity_name`" hazard: free-text names are mutable, dashboard tokens asserted, device certs verified. Capability grants declare a minimum floor; execute-deny becomes "this persona's identifier claim is below the required floor."
- **Access groups as indirection** (`src/plugin-sdk/access-groups.ts`): allowlist entries reference named groups (`accessGroup:<name>`); resolution returns a structured state — `{referenced, matched, missing, unsupported, failed}` — so deny reasons distinguish "not in group" from "group config vanished." Groups grant nothing by themselves. Halbert personas become declarative named bundles with auditable resolution.
- **Pairing = challenge codes with bounded pending state** (`src/pairing/`): 8-char code from an ambiguity-free alphabet (no 0O1I), pending requests TTL 1h, max 3 per account with LRU eviction, approve by code *or* by opaque hash id (blocks "approve everything visible"), first-ever approval bootstraps the command owner. The middle admission state `pairing-required` makes deny → onboarding one state machine — the right shape for enrolling a new guest persona.
- **Sender-scoped tool policy** (`src/agents/sender-tool-policy.ts`): a policy object resolved from `(channel, sender identity)` at tool-surface construction time, deny globs always win. Rather than `if persona == guest` sprinkled through tools, filter the whole tool registry through a resolved policy.
- **Durable, one-shot consents** (`src/gateway/exec-approval-manager.ts`): pending rows persisted *before* the waiter exists; resolution is CAS first-answer-wins across surfaces; `runtimeEpoch` stamping means decisions from a previous process lifetime never match; allow-once is single-spend CAS; **allow-always only mints when the grant is mechanically re-verifiable later** (pinned executable, enforceable pattern), otherwise silently downgraded to allow-once. "The DB record is not the grant" — audit history and executable authority are separate.
- **Byte-exact approval bindings** (`src/infra/system-run-approval-binding.ts`): an approval binds canonical argv + cwd + pinned executable path + env digest (+ sha256 of a mutable script operand); recomputed at execution; drift → deny. "Refuse to mint an approval rather than pretend coverage" when the effect can't be pinned — applies directly to Halbert's MCP tool gating.
- **Fail-closed as a checklist**: timeout → recorded terminal deny; no delivery route → deny; storage corrupt → deny with reason; authority closed → deny; malformed decision sets always re-include "deny". Post-186-finding-audit, Halbert should codify this: every permission-state failure is a recorded terminal deny, never "unknown → proceed."
- **Standing grants for scheduled work** (`operator-approval-standing-grants.ts`): minted in the same transaction as the consent, pinned to a config-revision hash, consumed atomically at spawn-time with revalidation, cascade-deleted with the approving consent. The template for Halbert's "standing consent" for cron/automation.
- **Admission evidence** (`src/channels/message-access/admission-evidence.ts`): ingress decisions are branded into opaque frozen objects with payloads in a WeakMap, consumed exactly once at execution, producing audit receipts. Guest-initiated actions should carry unforgeable receipts (persona, channel, identity strength, gate graph) into the audit trail.

One anti-pattern to refuse: OpenClaw has an *implicit same-chat approval fallback* (empty approver config → anyone in the chat can approve). Halbert's guest persona must have no analog — approvers are explicit or approval is denied.

### 4. Scheduler / heartbeat

Halbert's heartbeat design exists here fully worked out, including the failure modes:

- **Heartbeat IS a cron job**, declaratively reconciled: config projects into a plan of create/update/remove changes that converge the job table (`src/cron/heartbeat-monitor.ts`). System jobs carry `declarationKey`s and are `systemOwned` — user/agent tooling cannot edit or re-enable them. Per-agent phase offset staggers firing.
- **Silent protocol** (`src/auto-reply/`): heartbeat replies that are only `HEARTBEAT_OK`/`NO_REPLY` tokens are suppressed; the token matcher documents every way models get this wrong (punctuation-wrapped, JSON-string-wrapped, trailing-token-after-substantive-reply). A `heartbeat_respond` tool lets the model explicitly choose `notify: false|true` — it decides whether to interrupt the user.
- **The zero-token idle trick**: if the persisted scratch content is effectively empty (only headers/stubs), **the LLM call is skipped entirely**. Idle heartbeats cost nothing.
- **Scheduler mechanics**: one re-armed timer across all jobs (never N intervals), a minute-cadence safety wake to absorb sleep/clock jumps, a refire-gap floor (fixes the zero-delay hot-loop bug Halbert would otherwise re-encounter), run reservations persisted *before* execution, outcome persistence decoupled from execution slots, startup catch-up bounded + staggered + deferrable, and `pacing.ts` lets the *agent propose* its next-run delay clamped to configured bounds.
- **Wake plumbing**: coalesced wake classes (task/scheduled/event), per-target serial turns, named busy-skip reasons (`requests-in-flight`, `preempted`, `channel-not-ready`…), and **settlements** — a cron job can await its wake's terminal result, so scheduled work knows whether the agent actually processed it. That's the answer to "did the heartbeat do the work or do I escalate to the indicator light."
- **Watchdog discipline**: phase-aware timeouts (setup budget vs execution budget; queue-wait doesn't burn execution budget); crash-loop budgeting (max 10 restarts/hour sliding window, cooldown cycles, 60s startup grace); restart policy in a pure, table-tested module — including a clock-rollback test (desktop machines suspend).
- **Simplified run-receipts**: Halbert is single-instance — take "marker + owner pid + on startup treat all running markers as interrupted unless the pid is alive," not OpenClaw's full multi-instance invariant matrix (I1–I4, foreign-receipt monitors). 10% of the complexity, 90% of the value.

### 5. Terminal direction (watched terminals, agent-owned terminal)

- **Command lanes** (`src/process/command-queue.ts`): all concurrent work goes through named lanes (`maxConcurrent` default 1 = serialization), with generation counters so cancelling a batch invalidates stale completions, typed timeout causes (`task-budget | owner-deadline | progress-idle | abort-grace`), and explicit `blockedBy` diagnostics. One lane per terminal; a lane for agent turns so a user message can't interleave mid-turn.
- **Global background budget of 3** (`src/process/background-work.ts`): every subsystem registers a background-work owner against one process-wide capacity group. Prevents the agent spawning 12 watchers and melting the laptop. The encoded rule — *only leaf work belongs here; a coordinator holding capacity must not await another background task* — is worth copying verbatim.
- **`ManagedRun` / supervisor** (`src/process/supervisor/`): the distinction between "the command exited" and "every descendant is provably gone" (`waitForExtinction`, stdin-EOF → SIGTERM → SIGKILL escalation on owned stdio); activity tracking (`lastOutputAtMs`); `no-output-timeout` as a first-class termination reason. This is the safe-handoff primitive for terminal reuse: idle = no output for N ms; only a provably extinct process tree hands back.
- **Status vs delivery-status split** (`src/tasks/task-registry.types.ts`): "the task finished" and "the user has been told" are different state machines — exactly right for indicator lights. Plus a cheap regex **progress-only completion detector**: a "completed" report ending in "I'll now check…" is forced to `blocked`. Port to Python verbatim; it guards against the most common agent self-deception. And "lost" as a first-class terminal status (worker died without reporting) instead of lying "failed."
- **OSC 9;4 progress** (`packages/terminal-core/src/osc-progress.ts`): a native busy indicator in the *terminal's own chrome* (Ghostty, WezTerm, Windows Terminal), feature-detected, clean no-op controller elsewhere, injection-sanitized. Zero scrollback pollution — the subtle "agent is using this terminal" light.

### 6. Voice mode

- **Speech reaches the agent only via a consult tool** (`src/talk/agent-consult-runtime.ts`): the realtime voice model owns audio/VAD/turn-taking but never answers from its own knowledge; it calls `openclaw_agent_consult` with the question, which launches a real agent run with delivery context inherited. **There is no implicit transcript→agent side channel to forget to wire** — this makes Halbert's past "spoken input never reached the agent" defect structurally impossible. Route Halbert's local STT path through the same consult entrypoint so voice and text share one ingress contract.
- **Durable voice sessions** (`src/talk/client-voice-session*.ts`): every call is a persisted record with status and effects; transcripts are persisted with retry so spoken turns survive restarts; tool executions during a call produce a **mutation digest** — evidence for "what did you just do to my files?"
- **Fast-context shortcut**: consult-shaped questions first hit a bounded memory/session search (sub-second); full agent only on miss/timeout. Direct lift for spoken "what/when" queries.
- **Forced-consult coordinator**: if the realtime model hesitates, synthesize the consult after a grace window and dedupe against a late native call (fuzzy question match). Turns "did the agent hear me?" into a solved dedup problem.
- **Untrusted-boundary discipline**: exact-speech replay is authorized by a *host-owned retained set of delivered answers*, never by a marker in model output ("the marker alone must never select the privileged replay path"). Generalize: whenever model output can select a privileged path, validate against host state.
- **TTS quality rules**: code-heavy replies (>50% fenced code) speak a deterministic fallback line instead of garbage; captioned-final defers speech so captions and audio never diverge; long replies summarized by the utility model first. Their transitional `[[tts …]]` prose-DSL is self-admittedly being retired for structured fields — start with fields.
- **Local TTS helper framing** (`apps/macos-mlx-tts`): stdout dup'd to a private FD so only binary frames ride the real stdout, all logs/crashes go to stderr; byte-bounded both directions. The pattern for any local speech/STT subprocess.

### 7. Skills & prompt assembly

- **The SKILL.md format is Claude-Code-compatible by design** — the catalog renderer is kept "byte-for-byte aligned with the upstream Agent Skills formatter." Match the format (`name`/`description` frontmatter, `<available_skills>` XML catalog with `<location>` pointers, model reads the file on demand) and Halbert ingests ecosystem skill packs directly. Progressive disclosure is structural: the loader only parses frontmatter, so a 100KB skill costs ~200 prompt bytes until invoked.
- **Token-budget ladder** (`src/skills/loading/skill-prompt-limits.ts`): over budget → compact (drop descriptions) → binary-search skill count → binary-search description length; names/locations are an "identity floor" never cut; degradation appends an honest truncation notice telling the operator how to audit. ~100 lines of Python.
- **Capability gating** (`metadata requires: {bins, anyBins, env, config, os}` evaluated against the live host): the catalog is always an honest set of things runnable *right now*. Maps directly onto Halbert's capability registry; `bins` (all-of) vs `anyBins` (any-of) is worth copying verbatim. Also: a skill whose secret was quarantined vanishes from the catalog instead of appearing with unusable prerequisites.
- **Stable-prefix prompt assembly** (`src/agents/system-prompt.ts`): fixed section order with everything volatile (date, channel guidance) below a literal `CACHE_BOUNDARY` marker; the stable prefix is sha256-keyed over *all* its inputs and LRU-memoized — structurally stale-proof and prompt-cache-friendly. Slots into Halbert's tiered XML assembly directly.
- **Custodian skills** (`custodian-skills/`): dangerous ops runbooks load **only** for the configured system-custodian agent — hidden from user-facing agents by *discovery scoping*, not prompt policing. All four follow a **Gather → Mutate → Repair → Prove → Report** contract ending in one live end-to-end proof. The template for Halbert's maintenance/diagnostics persona and for any state-changing skill.
- **Skill security**: content scanning for prompt-injection phrasing in *markdown bodies* (not just code for malware), boundary-safe file reads (symlink escape, hardlink, byte caps), frontmatter treated as untrusted input, reserved slash-command names rejected at spec-build time.
- **Usage telemetry from day one**: every tool call is matched against known SKILL.md paths → per-run skill-activation receipts. "The model demonstrably consulted skill X" is what makes curation and self-modification safety possible; retrofitting is impossible.
- Keep snapshots **structured**, render late: OpenClaw regex-parses its own rendered prompt in two places and pays for it with parity tests and fallback ladders — the clearest avoidable anti-pattern in the area.

### 8. Daemon / watchdog / process lifecycle

- **Close code 1013 "gateway starting"** with a server-hinted `retryAfterMs`: booting is a first-class protocol state; clients back off on the daemon's own numbers instead of guessing. Paired with **watchdog alignment**: the client's watchdog is clamped to never fire before the server's own declared deadline. This kills the double-timeout race and the restart storm — the medicine for Halbert's watchdog pain.
- **Event-loop readiness probe** before trusting the process: sample responsiveness (timer drift), not just pid/socket. Python equivalent: time a scheduler round-trip before declaring the daemon healthy.
- **Restart-from-inside**: a detached helper writes to a durable restart log, *waits for the caller's PID to exit*, then relaunches. Updates become transaction boundaries: in-flight work is journaled with a boot-revision stamp; the new daemon resumes safe-retry or explicitly dead-letters. Lightweight version: a JSON sentinel file with a revision counter.
- **Staged shutdown** as a protocol: fixed ordered checklist (drain turns → notify subprocesses → close transports → flush state), per-stage deadlines, parallel-then-race hook emission so one slow consumer can't block the rest, and an open-work registry so SIGTERM mid-turn emits the right lifecycle events instead of leaving a phantom in-flight turn in the dashboard.
- **Entry discipline**: double-execution guard when the entry module can be imported twice; cheap queries (`--version`, status) answered without importing the core; a named boot-phase trace.
- **Respawn plan** for process-level flags that can't change post-start (env, TLS roots): build a plan → exec child with a one-way marker env var (provably loop-free) → parent becomes a transparent signal bridge with a three-stage kill ladder. Directly liftable to Python where needed.

### 9. MCP client boundary

- **One policy pipeline, many surfaces**: the MCP server OpenClaw *exposes* routes through the same allow/deny collection as internal tools — there is no second, weaker path. Halbert's redaction/policy choke point must be the identical code for MCP-invoked and internal tools.
- **Guest-value ownership transfer** (`src/agents/mcp-content.ts`): sensitive values ride in a WeakMap keyed by result object identity, transferred through pipeline stages, consumed destructively at the one sanctioned bridge. Prevents "someone later JSON-dumps the result and leaks the redacted field" — the classic choke-point bypass. Natural companion to Halbert's deterministic redaction.
- **Order-stable tool naming**: sanitize to `[A-Za-z0-9_-]`, `server__tool` with caps and collision suffixes, assignment in **declaration order** (sorting "would silently swap safe names between colliding servers"), checked against a reserved-name set so MCP servers can never shadow built-ins.
- **Lifecycle lease**: per-server state-DB lease (5min TTL, assert-owned before *and after* the critical section) so daemon and dashboard can't race on server config.
- **Secret sentinels + egress proxy** (`src/secrets/`): rather than scrubbing text, secrets are sealed into opaque tokens at resolution (AES-256-GCM, process-global key) and substituted only at a loopback proxy with a **per-secret destination allowlist**; an unresolved sentinel reaching the wire is refusal, never a leak; the redaction registry registers the exact value *plus URL-encoded and JSON-escaped forms* (the leak Halbert's own audit would find). Even if Halbert doesn't build the proxy, the registered-variant triple is a must-copy.
- **Echo guard** as second layer on any redaction choke point: strip exact markers cheaply, plus rolling-window n-gram matching of recently injected sensitive content against outbound deliveries (catches paraphrase; catches long verbatim chunks) — with delimiter escaping so content can't forge markers.
- **Host-armed approvals for self-management** (`src/system-agent/`): the self-repair agent gets exactly one admin tool with a typed operation union; `approvalArmed` is set only when the *host judged the user's actual message* to be an approval — "the model-supplied `approved` argument alone must never authorize a mutation"; approvals are scoped to one exact operation via canonical hash, one-shot. For untrusted harnesses, tool restriction is enforced by *what the MCP server exposes*, not by trusting the harness.

### 10. Model picker / providers

- **Slot trio**: Primary / Utility ("small model for short internal utility tasks", with an Automatic pseudo-value) / Fallback. The **utility slot** is the missing piece in Halbert's chat/specialist/vision lineup — cheap internal work (summarization, card generation, auto-review) shouldn't burn the chat slot.
- **Model-agnostic quality dials**: thinking-level and fast-mode tiers remapped per-model behind the scenes (`thinkingLevelMap`); a mid-conversation model switch transparently remaps the user's tier and reports `{from,to}`. This gives the founder's "providers only, no model names" directive its concrete shape — capability-tier control, zero model names surfaced.
- **Catalog as declarative manifest data**: models live in provider plugin manifests with `contextWindow`, cost, modalities, compat flags, `status: available|preview|deprecated|disabled` + `replacedBy` — retirement without breaking old refs. Merge conflicts are *dropped and recorded*, never silently won. Aliases ("opus" → canonical id) keep config stable across renames. Remote catalog overlays can only change text metadata — **never** endpoints/headers/transport. Route-bound capabilities are atomic: changing `baseUrl` clears all route metadata rather than merging stale capability facts.
- **Model selection as a transaction**: policy gate → prepare → post-await re-validate → atomic persist with touched-field verification → notify pending replies. Result is a discriminated union incl. `conflict` ("session changed, retry") — worth copying verbatim for Halbert's slot changes.
- **Provider vs protocol as orthogonal axes**: `api` enum (openai-completions, anthropic-messages, ollama…) with an adapter registry — any OpenAI-compatible endpoint is one catalog row, not an integration. The ~30 compat flags (`maxTokensField`, `requiresToolResultName`, …) show the realistic surface; budget for it now instead of `if provider == "x"` later.
- **Failover**: tri-state cooldown decisions (`skip | attempt | suspend_session`), throttled recovery probes, provider-reported rate-limit windows authoritative. Keep it in *one* module — OpenClaw's ~10-file fan-out is the anti-pattern.

### 11. Testing patterns (cross-cutting, cheap, high-value)

- **Golden wire traces** (`src/channels/plugins/contracts/trace/delivery-trace.ts`): channel delivery tested as recorded JSONL — IN events scripted (including wire faults like rate-limit-with-retryAfter), OUT events observed at a mocked SDK boundary; canonical JSON with sorted keys → byte-stable goldens; env-var golden refresh; a shared scenario library (streaming-happy, cancel-mid-stream, rate-limit-during-preview…) every channel runs. Extremely liftable for Halbert's TTS/dashboard-websocket streaming.
- **Coverage-ID test profiles** (`taxonomy.yaml`): test profiles defined as semantic coverage IDs (`security.redaction-personal-redaction`, `agent-runtime.progress-visibility-no-fake-progress`, `session-memory.personal-memory-recall`) resolved to owning tests — profiles like "smoke-ci" and "personal-agent" select by *semantic target*, not path. With Halbert's order-sensitivity and red-seam problems, this is a pattern worth stealing outright.
- **Contract suites as installers**: `installChannelPluginContractSuite(...)` parameterizes the identical scenarios per implementation. Python: pytest fixture factories running the same ingress/approval/mention scenarios against dashboard/voice/terminal adapters.
- **Policy/mechanism split**: every decision function pure and table-tested separately from the timer/poll machinery (incl. the clock-rollback test).
- **Boundary tests**: a test that fails if core startup eagerly imports any extension module; tests that drive a *real* MCP client through the surface and assert exactly what reached `execute`.

---

## Anti-patterns — what NOT to copy

1. **Size-budget decomposition.** Module boundaries follow a linter line-count rule, not domain boundaries (`oxlint-disable max-lines -- TODO: split` on an 872-line resolver; a 1,667-line "grandfathered" loop file; cron split across ~40 files "to keep within size budget"). Halbert's Python core should keep state machines in one cohesive module with a single exported decision type.
2. **Regex-parsing your own rendered prompt.** Two subsystems parse the prompt string they rendered (skill catalog filtering, code-mode skill recovery), paying parity-test + multi-fallback tax. Keep snapshots structured; render late.
3. **The multi-instance receipt invariant matrix.** Rigorous, and mostly irrelevant to a single-user single-instance assistant. Take "persist marker before side effects + on-boot treat running markers as interrupted unless pid alive."
4. **Layer sprawl.** Five exec-policy merge layers and a 1,669-line gate file; seven skill roots with precedence collision warnings; the *lattices and invariants* are right — the *number of layers* is the cost. Halbert: one capability registry, one policy lattice, three skill roots.
5. **Convenience-over-strictness holes.** The implicit same-chat approval fallback (empty approver config = anyone in chat may approve) is tagged and intentional — Halbert's guest persona must have no analog.
6. **LLM in the decision loop.** OpenClaw constrains its exec auto-reviewer well (deterministic pre-gates, allow-once-only, untrusted-input fencing, input-side directive detection, every failure → ask), but the whole injection-defense class exists only because a model reads attacker-influenced text. Halbert's deterministic stance avoids the class; if model triage is ever added, copy every one of those constraints.
7. **Prose-embedded control DSLs.** The `[[tts …]]` directive tags are transitional and being retired for structured fields. Never parse control flow out of assistant prose.
8. **Dual dist/source artifact resolution** and Windows-schtasks-as-supervisor: both are large complexity taxes Halbert's single-artifact, single-platform-privileged design avoids for free.
9. **Timeout constants scattered** across layers, mitigated only by cross-reference comments. Halbert: one budgets module with derivations.

---

## Top 10 lifts, overall

1. **Memory: two-tier + recall-driven promotion + plan-based consolidation** — the complete blueprint for wiring memory_v2 (when to write, when to recall, what earns durability, how to consolidate without hallucinated deletion, and how it never becomes a chat UI).
2. **Session tree with branch summaries + the compaction machinery** — the exact data model for hidden topic threads in one continuous conversation.
3. **The `security × ask` lattice with guest-as-capability-floor** — guest persona as `minSecurity(guest, x) == deny`, plus named-gate ingress decisions with reason codes and the identifier-authentication ladder.
4. **Silent heartbeat protocol + zero-token idle short-circuit** — Halbert's heartbeat, with every failure mode already solved.
5. **Close-code 1013 + watchdog alignment + crash-loop budgets** — the daemon/watchdog treatment plan.
6. **Consult-tool-only voice ingress + durable voice sessions** — makes "spoken input never reached the agent" structurally impossible.
7. **Command lanes + background budget + status/delivery-status split + progress-only detector** — the watched-terminal substrate and correct indicator lights.
8. **Claude-compatible SKILL.md format + `<available_skills>` catalog + capability gating + cache-boundary prompt assembly** — the skills system, ingestible ecosystem and all.
9. **One policy pipeline across MCP and internal surfaces + guest-value ownership transfer + secret sentinel variant registration** — reinforcements for the MCP trust boundary.
10. **`PRAGMA user_version` migration ladder with downgrade refusal** — one afternoon, permanent payoff, fits the "no legacy support" posture while keeping data honest.

---

## Follow-ups this review suggests (not scheduled, just recorded)

- The memory findings deserve a design pass against `halbert_core` memory_v2 (ledger → episodic tier, consolidator input = promotion store, decay as ranking multiplier).
- The guest-persona workstream (`feat/guest-persona`, unmerged) should ingest §3 before it merges — several findings (identifier ladder, admission gates, pairing-as-onboarding) read like the missing pieces of PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.
- The voice findings slot into the open voice-mode items (spoken input path, VOICE modality resolution).
- The scheduler findings pair with the existing scheduler/heartbeat alignment work on main.
- Security remediation branch (worktree-sec-1) may want the echo-guard and secret-variant-registration items added to its held-back list review.