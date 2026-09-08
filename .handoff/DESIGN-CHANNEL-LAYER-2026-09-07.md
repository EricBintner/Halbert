# D-4 Design: The Channel Layer — Halbert's surfaces as first-class channels

**Date:** 2026-09-07
**Pass:** D-4 (design only — no code, no commits). Produces the C-series packets (§7).
**Source reviews:**
- `.handoff/OSS-REVIEW-HERMES-2026-09-07.md` §7 (per-platform session keys, transcript-owner turn lease, delivery-obligation ledger, two-axis permissions, TeeTransport, busy-mode tree) and §2 (the interrupt algebra)
- `.handoff/OSS-REVIEW-OPENCLAW-2026-09-07.md` §5 (channel-plugin capability bundles, named-gate ingress, access groups) and §9 (the claims ladder)
**Must reconcile with:**
- `.handoff/DESIGN-SESSION-TREE-AND-COMPACTION-2026-09-07.md` — thread id is the lineage root (§3.3); the lease question is pre-decided there and this design inherits it
- `.handoff/RECONCILIATION-OSS-RESEARCH-PROGRAM-2026-09-07.md` §2 — the engine's `AttunementContext.subject_confidence` is the recorded claims-ladder slot (R-EN-11); channels stay app-side (one consumer)
**Merged surfaces this design builds on:** `persona/admission.py` (named-gate decisions), `persona/claims.py` (the strength ladder), PACKET-07 Phase B (`request_stop`/`request_steer`/`handle_midturn_arrival`/`_drain_pending_steer`), PACKET-04 A1 (typed voice ingress: modality/speaker/claim fields on the turn).

**Verified current state (re-verified in repo 2026-09-07):**
- `dashboard/routes/agent.py` — `SendMessageRequest` (:38-83) carries `modality`, `speaker_name`, `speaker_role`, `claim_source` as **client-supplied** optional fields; `send_message` (:1552) runs the 07-B mid-turn interception (:1590-1608: non-image arrivals route through `handle_midturn_arrival`; image arrivals queue as whole turns), then `agent.process(...)` under SSE (:1637-1681). `/stop/{session_id}` (:1777) and `/cancel/{session_id}` (:1764) are distinct endpoints with distinct semantics.
- `agents/state_machine.py` — `_turn_lock` is one per-event-loop `asyncio.Lock` (:342-376; Wyoming voice is handed the main loop precisely because of this, `dashboard/app.py:1511-1520`); `TurnActivity` generation claims race-proof stops (:501-507, `turn_activity.py`); `_pending_steer` is the single replace-not-grow slot (:323); `handle_midturn_arrival` (:1631) normalizes any arrival's command/text against the *running* turn (`self.ctx`), not the arrival's own session; `process()` applies the modality/role defaults (:509-518: typed→"admin", voice→"unknown"); `_forward_guest_turn` (:3320) ships a fronting guest's turn to its sibling home; `_echo_guard_egress` (:3448) is the display-side scrub seam ahead of TTS/egress.
- `agents/steering.py` — `decide_midturn` (:57): STOP/STEER/REDIRECT/NORMAL_TURN, demotion of interrupt to steer while a tool batch is in flight (:81-89), REDIRECT dormant (`in_model_request=False` at the call site, state_machine.py:1666 — no cancellable provider client exists yet).
- `agents/threads.py` — `ThreadManager.begin_turn` (:308) resolves the hidden thread server-side; a session id names one turn, the thread id the conversation (agent.py:43-45). Thread identity is channel-blind today.
- `dashboard/app.py` — `_relay_voice_turn` (:1403-1439): transcribe-once, the observation is the single STT result, the transcript rides the mic uplink back to the browser, which submits the turn through the typed ingress with the speaker claim. TTS egress hub (`routes/tts_egress.py:53-127`): subscriber-gated, dead sockets dropped, never retried.
- `dashboard/routes/guest.py` — `_ROUTE_GATES` (:298-318) is the ordered named-gate list per route; `_admit` (:256-291) fails closed on unwritten policy (`no_gate_list_configured`).
- `persona/guest_tools.py` — `GUEST_ALLOWED_TOOLS`/`GUEST_DENIED_TOOLS` (:138-206) with the import-time self-check (:225); the allowlist is enforced at schema mint and at dispatch.
- `federation/fleet_proxy.py` — entirely `NotImplementedError`; outbound peer-token custody is an acknowledged undecided design (:157-176). The satellite/MCP ingress is a tool surface, not a talk channel.

---

## 1. The channel abstraction: `ChannelDeclaration`

**Placement:** a new module `halbert_core/halbert_core/agents/channels.py` — a frozen dataclass, a registry dict, and one resolver. Beside `threads.py` and `steering.py`, not in `persona/`: a channel is an ingress/egress fact that feeds the *turn*; persona claims and gates consume it downstream. The whole module should stay under ~150 lines. OpenClaw's channel layer is a 25-adapter plugin SDK because it fronts Telegram/Discord/Slack/WhatsApp; Halbert fronts three surfaces from one process, one event loop, one transcript store. **Lift the contract, not the surface area** (OpenClaw review, framing note).

```python
@dataclass(frozen=True)
class ChannelDeclaration:
    id: str                          # "dashboard" | "voice" | "terminal"
    claim_ceiling: ClaimStrength     # max strength a claim arriving here may carry
    default_role: str                # speaker_role when the channel cannot identify
    busy_verbs: frozenset[str]       # subset of {"stop", "steer", "queue"}
    delivery: frozenset[str]         # subset of {"sse", "tts", "event_bus"}
    transcribe_before_command: bool  # voice rule: commands arrive as transcript
```

Field-by-field justification — each earns its place against a seam that exists or is being built in this series, or it is cut:

- **`id`.** Needed the moment more than one ingress exists. First use: stamped into `messages` row metadata (`metadata.channel`) as provenance — recording, never gating. Cheap now, load-bearing in §6 and for the audit trail's "how did this turn arrive."
- **`claim_ceiling`.** The security field. `SendMessageRequest.claim_source` is client-supplied today: any dashboard browser can declare itself `device_cert`. The channel layer makes the **server** stamp the claim source from the resolved channel, clamped to the channel's ceiling, before `claims.claim_from_source` ever sees it (`claims.py:44-57` already fails closed on unknown sources — the clamp keeps that property end to end). This is the packet-04 residency the A1 plumbing left behind.
- **`default_role`.** Moves the `process()` inline default (:509-518) out of the state machine into data, so "typed turns are admin, voice turns are unknown" stops being code only the state machine knows and becomes a property the route, the gate list, and a test can all read.
- **`busy_verbs`.** PACKET-07's out-of-scope guard deferred per-channel busy modes to "Phase C records the decision." This is that record: busy behavior is a **capability of the channel, not a user setting** (§4).
- **`delivery`.** What the channel can honestly receive. Drives the delivery semantics of §3: a channel not in a turn's `delivery` set is a channel that was never owed a delivery — which is what replaces the ledger.
- **`transcribe_before_command`.** One bool because it is a real behavioral fork (Hermes: voice notes are transcribed *before* interrupting, so the interrupt text is the transcript, not a placeholder). Halbert already transcribes-once (`_relay_voice_turn`); the flag declares the invariant on the channel so the browser-relay seam can't regress it.

**Cut, with reasons:** platform metadata blocks and plugin manifests (no plugins); rate limits and media caps (single-user; the request model's own bounds already cover the pathological case — agent.py:52-60); mention/activation patterns (no group chats); message edit/delete semantics (the transcript is append-only, D-1 §1.4); per-channel allowlists (the command axis already lives in `GUEST_ALLOWED_TOOLS`/RoleGate — §5). If a future channel needs a cut field, that is a new design pass, not a config key.

**Fail-closed rule:** an ingress that resolves to no registered channel is refused with the admission module's existing shape (`decisive_gate="channel_registry", reason_code="no_channel_configured"`), mirroring `guest.py`'s `no_gate_list_configured` posture. Unwritten policy denies.

## 2. Session identity: keys, the lease, and cross-channel resume

**The lease question is already answered.** D-1 §3.3 fixed marker compaction, which makes the thread id the lineage root permanently — there is no walk. `_turn_lock` serializes one turn at a time for the whole process, and `TurnContext.thread_id` is the transcript owner. Hermes keys the lease by transcript-owner *rather than route* because its routes multiplex onto sessions; in Halbert the route was never the key and the owner was always the thread. **The channel layer adds exactly one rule: the channel id is never a lease key, never a queue key, never a scope key.** Channels are ingress provenance; the thread is the conversation. A dashboard turn and a voice turn that resolve to the same open thread are one conversation by construction — the tree gives cross-surface continuity for free.

**Session keys per channel: deliberately none.** Halbert's `session_id` names one *turn*, not a conversation (agent.py:43-45; generated per request, :1578). Hermes needs per-platform session keys because each platform owns a message store it must address back into. Halbert owns all the stores; the browser holds no state the server needs addressed. So the declaration carries no session-key-derivation field, and this absence is the design.

**Cross-channel resume — deferred, with the real-case analysis.** The IDOR-proof `/resume` (persisted row must prove platform+thread+chat+user match; NULL rows fail closed) exists in Hermes to move *a chat's delivery binding* between platforms. Enumerating Halbert's actual cases:

- **Owner, dashboard → voice** ("I asked at my desk, answer in the kitchen"): served today by thread-tree recall — the voice turn lands on the same open thread or auto-recalls it (threads.py begin_turn). Nothing needs resuming; there is nothing binding the conversation to a surface except the TTS subscriber check, which is delivery, not identity.
- **Guest fronting, visitor talks at dashboard then voice** (the nearest real case): the guest session is one persona fronting on the machine (`guest.current_guest()`), the visitor speaks to the *machine*, and both channels feed the same turn path. Again continuity is thread-scoped, not session-scoped. No resume.
- **Owner, dashboard → a future terminal client**: the terminal opens its own turns; the one hidden-thread conversation means it sees the same subject state. Resume would only matter if the terminal needed to *take over* a turn's SSE stream — which is §6's tee, not identity transfer.

**Deferred, not declined:** record the IDOR-proof shape for the day a second *display* session must share a binding: the resuming channel presents the thread id, the server requires (a) the thread exists and is in the caller's persona scope, (b) the caller's claim strength ≥ the channel's floor, (c) the original binding's channel consents via `delivery` set membership. All three checks exist as mechanisms by C2; the endpoint does not get built until a case does.

## 3. The delivery-obligation ledger — declined, with the substitutes named

Hermes's ledger (pending → attempting → delivered/failed, honest "may be a duplicate" markers per crash state) answers a question its channels ask: *Telegram acknowledged the API call, but did the message survive the reconnect?* Halbert's channels don't ask it:

- **Dashboard SSE is fire-and-forget over a request-scoped stream**, and the durable record of every turn is the transcript itself — `ThreadManager.end_turn` writes the assistant row regardless of whether any client is attached. A browser that lost its stream rejoins by reading the thread; the store is the receipt. There is no re-send path, so there are no duplicates to mark honestly.
- **Voice TTS is subscriber-gated by design** (`TtsEgressHub`: no subscriber → no synthesis → the turn row still records the reply). Dropped-dead-socket is the honest policy already: never retried, never claimed.
- **Scheduled/proactive work**, the one place "the user was told" genuinely diverges from "the work completed," is already spoken for: packet-03's closed `last_status` taxonomy (`ok / error / delivery_failed / blocked_config` — BrightestMinds co-signed from scar tissue) plus the findings chain feeding the indicator bell.

So: **no ledger, and one honesty rule in exchange** — channel declarations and turn statuses never claim "delivered." The vocabulary is `persisted` (the transcript row exists — provable from the store) and `streamed` (an SSE write or TTS publish returned without error — a best-effort observation, logged). If a channel with real acknowledgment semantics ever appears (satellite push, mobile), the ledger gets its own design pass with the differentiated-duplicate markers intact; building it now would be the multi-instance receipt-matrix anti-pattern (OpenClaw §4: take 10% of the complexity) at one channel instead of five.

## 4. Busy modes per channel — the unification

Today two truths coexist: the **backend algebra** (`handle_midturn_arrival`: text steers, `/stop` claims the generation, both verdicts streamed on the arrival's own response) and the **client-side queue** (the dashboard holds pending sends and submits them in order). The backend is already authoritative — the client's queue is a polite fiction that delays a `steer_accepted` verdict the server would have given immediately. **Unification: the backend owns semantics; the client queue demotes to presentation.** A typed-while-busy send goes to the server immediately, gets its honest verdict (`steer_accepted` with `replaced:`/`demoted:` flags — the event exists, 07-B, state_machine.py:1688-1699), and the client renders that instead of pretending to hold a queue. The frontend's queue UI becomes a rendering of server truth, which also fixes the awkward case it silently has today (a queued-behind message that arrives *after* the turn ended was never steering anything).

Per-channel declarations, fixed (this is PACKET-07's Phase C record):

| Channel | busy_verbs | Why |
|---|---|---|
| dashboard | `{stop, steer}` | Text steers free; `/stop` claims the generation. Whole-turn queue only for image arrivals (no mid-turn seam for images yet — agent.py:1587-1589), which needs one honest addition: a `turn_queued` event so the lock wait isn't just a "waiting" badge. |
| voice | `{steer}` (+ barge-in) | A spoken follow-up while the agent works is corrective, not a new turn — steer is the natural verb. `/stop` has no spoken form worth parsing; TTS *playback* interruption is barge-in's existing job (coordinator tokens, app.py:1467-1471), a transport concern below the state machine. `transcribe_before_command=true` keeps the Hermes voice rule explicit. |
| terminal (future, C5) | `{queue, steer}` | A CLI user accepts whole-turn queuing as the first-class mode; steer rides the same slot when a turn is live. |

REDIRECT stays dormant until a cancellable provider client exists (state_machine.py:1662-1666) — no channel declares it.

## 5. Identity: channels → claims ladder → existing gates (reconciled, not duplicated)

The mapping, stamped server-side by the resolved channel:

| Channel | Claim source stamped | Strength | Role default |
|---|---|---|---|
| dashboard | `dashboard_token` | ASSERTED | `admin` (dashboard sessions are authenticated; process()'s existing convention) |
| voice, speaker identified | `voice_speaker_verification` | ASSERTED | identified speaker's role |
| voice, unidentified | (none) | UNVERIFIED | `unknown` — never silent admin (the packet-04 fix) |
| terminal | see Q1 | founder ruling | founder ruling |
| guest peer channel (`/api/guest/*`) | peer bearer token via `require_peer_auth` | ASSERTED | n/a (session envelope, not a talker) |

The free-text path stays MUTABLE and gates nothing, per `claims.py`'s documented intent ("recording only — nothing here gates an action").

**The two-axis split maps onto what already exists — add no third list.** OpenClaw's "who may talk" × "who may run which commands" lands in Halbert as: the **talk axis** is the channel declaration itself (which channels may open turns, with what claim floor) plus guest fronting state (one guest session at a time, enforced by `_session_free_gate`); the **command axis** is `GUEST_ALLOWED_TOOLS` enforced at schema mint and dispatch, RoleGate risk classification fed by the speaker role, and the `_ROUTE_GATES` named-gate lists on the guest/peer routes. The reconciliation is a *wiring rule*, not new machinery: admission gates and the tool filter read the turn's channel + claim as **facts in their gate graph** (`Gate.facts` exists for exactly this), and the gate list stays the single enforcement point. A channel that mints its own permissions would create the drift Hermes's alias-canonicalization item warns about ("authz and session keys fed by one canonicalization so the two never drift") — here the shared canonicalization is the channel registry.

**Engine boundary:** `AttunementContext.subject_confidence` is the recorded slot if claim strength ever gains a second consumer (R-EN-11, reconciliation §2). One consumer today = app-side, per the two-instance rule.

## 6. TeeTransport — yes, and thin

Hermes's point stands for Halbert with different physics: not "a second client gets the TUI's stream," but **today a turn's events reach exactly one HTTP response** — the SSE of whoever posted it. Everything else that should be able to *see* a turn — the voice HUD showing what the dashboard just typed, a second screen in the room, the guest home's pull channel, the future terminal client — currently cannot. The substrate half-exists (the dashboard's `ConnectionManager` WS fan-out, app.py:840; the findings event bus).

The design: one process-wide **turn-event tee** the state machine publishes a *reduced* event set to (state transitions, statuses, terminal-block starts/ends, tool-call markers, the verdict events) — not the token stream, which is bandwidth and privacy the tee consumers don't need. Two hard rules, both from existing seams: (1) tee payloads pass through `_echo_guard_egress`/the packet-05 display-redact seam before fan-out — a subscriber in the room sees only what the answer stream was cleared to show; (2) tee is observe-only — subscribing confers no steer/stop rights, which stay behind the channel declarations. Cost is small (the state machine already mints every event); benefit is real and immediate the day the voice HUD wants to reflect a dashboard turn — the most common two-surface moment in the house.

## 7. The C-series packets

| Packet | Contents | Lands independently? | Buildable now? |
|---|---|---|---|
| **C1 — declaration + registry** | `agents/channels.py`: frozen `ChannelDeclaration`, registry, resolver; dashboard + voice declared; server stamps `claim_source` from the channel (ceiling-clamped) and `default_role` from data — `process()`'s inline default and the route's pass-through of client-supplied claim fields become dead on purpose. `metadata.channel` provenance on turn rows. Unknown channel → `no_channel_configured` refuse. | Yes. Zero behavior change for honest clients. | **Yes** — small-model-friendly, one new module + clamp in `send_message`/`process`. |
| **C2 — voice channel wired honest** | `_relay_voice_turn` and the Wyoming path resolve the voice channel; `transcribe_before_command` asserted by test (the transcript IS the command text); the browser's `claim_source` field is ignored in favor of the server stamp; speaker-unknown turns pinned to UNVERIFIED/unknown role by test. Closes the last packet-04 A2 residue on the ingress side. | Yes, after C1. | **Yes.** |
| **C3 — busy-mode unification** | `busy_verbs` per declaration enforced in `handle_midturn_arrival` (verbs a channel doesn't declare degrade: stop→steer); dashboard client queue demoted to presentation of server verdicts; `turn_queued` honest event for image arrivals; dashboard frontend renders `steer_accepted`/`stop_declined` (existing events, currently backend-only). | Yes, after C1; frontend half can trail. | **Yes** — backend now, frontend small. |
| **C4 — turn-event tee** | Process-wide reduced-event fan-out from the state machine through the echo-guard seam; observe-only subscribers; first consumer: the voice HUD reflecting dashboard turns. | Yes, after C1. | **Yes** — thin, but touch the egress seam with care (packet-05 territory; the guard function exists). |
| **C5 — terminal talk channel** | Localhost CLI/TUI client as a declared channel: queue+steer verbs, event-tee consumer (C4), claim ruling per Q1. The existing terminal subsystem (pty spawn/exec/stage, `routes/terminal.py`) is a *tool* surface and stays one. | After C4; gated by Q1's ruling and the founder's answer to Q3. | **Gated.** |
| **C6 — deferred ledger & resume** | Nothing built. This section of this document (§2, §3) is the record; each item names its trigger condition. | — | **Deferred by design.** |

## 8. Open questions for the founder

1. **Terminal claim strength.** A local CLI on the owner's machine: dashboard token (ASSERTED, same as any local client), or OS-account proof (peer-uid over a Unix socket → a new `local_console` source at VERIFIED)? My recommendation: ASSERTED via the existing dashboard token for v1 — VERIFIED should mean a cryptographic device credential per `claims.py`'s own docstring, and an OS uid is not one. The peer-uid mechanism is real and cheap if you want it anyway.
2. **Unidentified-voice talk floor.** Today an unknown speaker may talk (Role clamps tools). Keep that, or require speaker enrollment before voice opens a turn at all? The current posture matches the guest-friendly house; tightening is a one-line floor change once C2 exists.
3. **Is the terminal a talk channel at all?** The terminal direction (2026-08-26 memory: user shells watched, agent reuses idle ones, subtle indicator lights) never required typing *to* Halbert in a shell. If terminal stays a tool surface permanently, C5 shrinks to nothing and the channel set is two. Is there a case for talking to Halbert from a TTY?
4. **Tee scope.** Reduced event set (statuses, markers, verdicts) or the full turn stream (tokens included) for second-screen rendering? Reduced is my recommendation — privacy by construction, bandwidth trivial; full stream only behind a second opt-in. (Pairs with packet-05's `no_gate_list`-style discipline: subscribers enumerated, none implicit.)
5. **Channel provenance in the timeline.** Should a turn row's channel ever be *visible* (a subtle glyph on a message — "said aloud in the kitchen")? The data ships with C1; rendering is a toggle. The hidden-thread directive bans lists, not glyphs.

**Deviations logged** (all deliberate; rationale in section bodies):
- vs **OpenClaw**: no channel-plugin surface, no capability bundles, no access groups for channels — six fields, three channels, one process (§1 cut list).
- vs **Hermes**: no per-platform session keys (§2), no delivery-obligation ledger (§3), no cross-channel resume built (§2 deferred with shape). Each mechanism is named-with-trigger rather than built-against-imaginary-scale.
- vs **both**: `claim_source` moves from client-supplied to server-stamped-and-channel-clamped — a fix to merged packet-04 plumbing (§1, C1/C2).
- vs **PACKET-07's record**: per-channel busy modes land as channel *capabilities*, not user settings (§4) — this document is the Phase C decision the packet reserved.

*Design complete; no code changed. Next gate: founder review of §8 Q1–Q5, then C1 dispatch.*
