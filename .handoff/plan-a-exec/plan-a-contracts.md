# Plan A shared contracts (binding for every planner)

Worktree (read and cite code from HERE, not from /Volumes/4TB-BAD/Halbert):
`/Users/ericbintner/.config/superpowers/worktrees/Halbert/continuous-conversation`
Backend package: `halbert_core/halbert_core/` (BE). Frontend: `halbert_core/halbert_core/dashboard/frontend/src/` (FE).
Spec: `documentation/design/continuous-conversation-and-watched-terminals-2026-08-26.md` (read §3–§8, §11–§14).
Backend tests run as: `cd <worktree>/halbert_core && /Volumes/4TB-BAD/Halbert/.venv/bin/python -m pytest tests/<file> -q -p no:cacheprovider`
Frontend tests: `cd <worktree>/halbert_core/halbert_core/dashboard/frontend && npx vitest run src/<path>` ; typecheck `npx tsc --noEmit -p .`
Baseline: backend 1119 passed / 4 pre-existing failures (test_tool_calling_bridge, test_phase_d_integration — do not touch those unless the num_ctx task must; keep them at exactly the same failures); frontend 45/45; tsc clean.
Commits: pathspec adds only (`git add <files>`), message subject only + body, NO Co-Authored-By / bot trailers (project rule). Branch: feat/continuous-conversation.

## 1. Storage (BE/agents/conversation_sqlite.py — extend in place)

Physical column `conversation_id` IS the thread id everywhere (do not rename). Add a `schema_version` table; `_ensure_schema` applies idempotent `ALTER TABLE ... ADD COLUMN` when missing (check `PRAGMA table_info`). Set `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` at connect.

conversations (= threads) new columns:
  status TEXT NOT NULL DEFAULT 'open'          -- open|paused|closed|merged
  receipt TEXT NOT NULL DEFAULT ''
  receipt_updated_at REAL
  topic_domains TEXT NOT NULL DEFAULT '[]'      -- json list[str]
  entities_json TEXT NOT NULL DEFAULT '[]'      -- json list[str] canonical entities
  last_active REAL                              -- updated only for origin human|assistant
  stale INTEGER NOT NULL DEFAULT 0
  ephemeral INTEGER NOT NULL DEFAULT 0
  parent_thread_id TEXT
  merged_into TEXT
  recalled_json TEXT NOT NULL DEFAULT '[]'      -- json list[{thread_id, title, date, status: accepted|retracted, at}]
  unread INTEGER NOT NULL DEFAULT 0
  paused_at REAL
  turns_since_pause INTEGER NOT NULL DEFAULT 0  -- grace-window counter on the NEW thread (turns since the previous thread paused)
  title_source TEXT NOT NULL DEFAULT 'provisional'  -- provisional|model|receipt

messages new columns:
  turn_id TEXT                                  -- uuid shared by the user row and its assistant row
  session_id TEXT                               -- per-turn state-machine session id
  origin TEXT NOT NULL DEFAULT 'human'          -- human|assistant|terminal|task-notification|proactive|system
  status TEXT NOT NULL DEFAULT 'complete'       -- in_progress|complete|interrupted|cancelled
  blocks_json TEXT NOT NULL DEFAULT '[]'        -- tool blocks (list of {tool, args, result, exit, execution_id}) for assistant rows
  terminal_block_ids TEXT NOT NULL DEFAULT '[]' -- json list[str]  (Plan A stores terminal SESSION ids here; Plan B switches to block ids)
  diff_proposals_json TEXT NOT NULL DEFAULT '[]'
  visible_in_timeline INTEGER NOT NULL DEFAULT 1

FTS: `messages_fts` re-created with `tokenize='porter unicode61'` when schema_version < 2 (DROP + CREATE + rebuild from messages). New `receipts_fts USING fts5(thread_id UNINDEXED, title, receipt, tokenize='porter unicode61')`.

New/changed store methods (exact signatures):
  def append_message(self, thread_id: str, role: str, content: str, *, origin: str = "human", turn_id: str | None = None, session_id: str | None = None, status: str = "complete", blocks: list | None = None, terminal_block_ids: list[str] | None = None, diff_proposals: list | None = None, metadata: dict | None = None, timestamp: float | None = None) -> int | None   # returns message row id; single transaction incl. FTS; WARNING on failure; None on failure
  def update_message(self, message_id: int, **fields) -> bool   # allowed: content, status, blocks, terminal_block_ids, diff_proposals, metadata
  def update_thread(self, thread_id: str, **fields) -> bool      # any threads column above + title, updated_at
  def get_thread(self, thread_id: str) -> dict | None            # row as dict incl. json-decoded lists
  def list_threads(self, status: str | list[str] | None = None, limit: int = 50) -> list[dict]
  def current_open_thread(self) -> dict | None
  def list_turns(self, *, before_turn_id: str | None = None, around_turn_id: str | None = None, limit: int = 50) -> list[dict]   # grouped: [{turn_id, thread_id, timestamp, user: {message_id, content, timestamp, status}, assistant: {...}|None, blocks: [...], terminal_block_ids: [...], diff_proposals: [...], origin}] newest-last, only visible_in_timeline=1
  def recent_messages(self, thread_id: str, limit: int = 12) -> list[dict]   # oldest-first, origins human|assistant only, {role, content, timestamp, origin}
  def search_receipts(self, query: str, *, exclude_thread_id: str | None = None, limit: int = 5) -> list[dict]   # [{thread_id, title, score, snippet, last_active, status}] ; query tokenised: each token quoted, joined with OR; MATCH in its own try; LIKE over title outside it
  def upsert_receipt(self, thread_id: str, title: str, receipt: str) -> bool   # updates conversations.receipt/receipt_updated_at + receipts_fts row
  def search(...)  # existing; fix: tokenise+quote, MATCH in own try, LIKE outside
  save(conversation) stays but must NOT delete messages; it upserts the conversations row only (+ inserts messages that have no id? no — save() no longer touches messages at all; add_message paths must use append_message). Wrap every write in `with self._conn:`.
  Content serialisation: if content is not str, store `content_to_text(content)` (from agents/blocks.py) and put the raw blocks into blocks_json.

## 2. Receipt (new BE/agents/receipt.py)

  def build_receipt(thread: dict, messages: list[dict], *, max_chars: int = 1500) -> str
Deterministic sections, in this order, each a single line prefixed with a label:
  "Title:", "When:" (first..last timestamp, ISO date, turn count), "Domains:", "Entities:",
  "Started with:" (first human content, ≤160 chars), "Last said:" (last assistant content first sentence ≤200 chars),
  "Commands:" (from blocks_json tool=run_command: `cmd (exit N)` ≤8), "Files written:" (write_file/diff paths ≤8),
  "Open loop:" (heuristic: last assistant sentence containing next|try|check|verify|then|after|once, else "none recorded").
Sentence split regex: r'(?<=[.!?])\s+' — never split on '.' alone.
  def provisional_title(first_user_content: str) -> str   # ≤60 chars, first line, trailing punctuation stripped
  def refined_title(receipt_entities: list[str], first_user_content: str) -> str

## 3. Signals / segmenter (BE/intake/signals.py + new BE/agents/thread_signals.py)

intake/signals.py additions:
  ENTITY_ALIASES: dict[str, str] = {"smb": "samba", "cifs": "samba", "smbd": "samba", "nmbd": "samba", "file share": "samba", "windows share": "samba", "exports": "nfs", "wg": "wireguard", "vpn": "wireguard", "certbot": "tls", "letsencrypt": "tls", "acme": "tls", "zpool": "zfs", "smb.conf": "samba"}
  add to _DOMAIN_KEYWORDS: storage += ["zfs","zpool","smart","smartctl"], network += ["samba","smb","nfs","cups","wireguard","vpn","share"], service += ["cron","crontab","systemd","journalctl"]
  def canonical_entities(text: str) -> set[str]   # lowercased tokens/phrases mapped through ENTITY_ALIASES plus any domain keyword hit and file paths matched by the existing _FILE_PATH_RE
  MessageSignals gains: entities: set[str], past_reference: bool, anaphora: bool  (regexes:
    PAST_REF = r"\b(we (discussed|did|set ?up|talked about|configured)|last (week|month|time|tuesday|monday|wednesday|thursday|friday|saturday|sunday)|remember when|back when|earlier|the other day|(a )?(few )?(weeks?|days?|months?) ago|as we did|like (we did|before))\b"
    ANAPHORA = r"^\s*(so|ok|okay|and|well)?[,]?\s*(did (that|it) work|any luck|is (that|it) (done|working|fixed)|still (broken|failing|not working)|what happened with (that|it)|how did (that|it) go)\b|^\s*(that|it)\b")

thread_signals.py:
  TEMPORAL_GATE_SECONDS = 7200
  GRACE_MINUTES = 30 ; GRACE_TURNS = 5
  STRONG_MIN_OVERLAP = 2
  @dataclass class Candidate: thread_id: str; title: str; last_active: float | None; score: float; match_terms: list[str]; strong: bool; status: str
  @dataclass class ThreadDecision: action: str  # "stay"|"reopen"|"open_new" ; target_thread_id: str | None; stale: bool; strong: Candidate | None; candidates: list[Candidate]; cues: list[str]
  def decide(query: str, signals: MessageSignals, open_thread: dict | None, store, now: float) -> ThreadDecision
    rules: candidates = store.search_receipts(query, exclude_thread_id=open.id, limit=3) + overlap scoring on entities vs thread entities_json;
    strong := (signals.past_reference or signals.anaphora) and candidates and candidates[0].score >= 0.5  OR  overlap(entities, cand.entities) >= STRONG_MIN_OVERLAP;
    if open_thread is None -> open_new;
    if strong and strong.status == "paused" -> reopen(target=strong.thread_id);
    gap = now - (open.last_active or now); domain_shift = signals.detected_domains and open.topic_domains and not (set(signals.detected_domains) & set(open.topic_domains)) and not (signals.entities & set(open.entities_json));
    if gap > TEMPORAL_GATE_SECONDS and domain_shift and not signals.anaphora -> open_new;
    stale = gap > TEMPORAL_GATE_SECONDS;
    else stay.
  def build_hint(open_thread: dict, decision: ThreadDecision, recalled: list[dict], notifications: list[dict], voice: str = "first_person") -> str
    exact shape:
      <continuity>
      Thread: "{title}" · {n} turns · last active {relative}.{" (resuming after a gap)" if stale}
      [Pulled in: "{title}" ({date}, {relative}; matched {terms}) — {receipt one-liner: Started with … Last said … Open loop …}]   # one line per recalled
      [Earlier work that may matter: "{title}" ({date}; matched {terms}); ...]   # weak candidates, ≤2, omitted when a strong recall happened
      [Waiting for you: ...]   # notifications, Plan C, render if present
      </continuity>
    max 900 chars; empty string if nothing to say beyond a brand-new thread with no candidates.

## 4. Thread manager (new BE/agents/threads.py)

  @dataclass class TurnContext: thread_id: str; turn_id: str; user_message_id: int | None; history: list[dict]  # [{role, content}] oldest-first, ≤12 rows + optional leading {"role":"system","content":"[Earlier in this subject: <receipt>]"}; hint: str; recalled: list[dict]; decision: ThreadDecision
  class ThreadManager:
    def __init__(self, store: SqliteConversationStore, *, now=time.time)
    def begin_turn(self, query: str, signals: MessageSignals, session_id: str) -> TurnContext   # persists the user row status=in_progress; resolves thread; reopen/open_new as decided; on strong recall to a closed thread appends recalled_json entry status=accepted
    def new_thread(self, title: str, reason: str, *, from_thread_id: str) -> str   # pauses from_thread (status=paused, paused_at=now), creates new open thread with title_source=model; returns new id; idempotent within a turn via caller flag
    def resume_thread(self, thread_id: str, *, from_thread_id: str) -> bool   # reopen paused; pause from_thread
    def recall(self, query: str | None = None, thread_id: str | None = None, *, exclude_thread_id: str | None = None) -> list[dict]   # [{thread_id, title, date, receipt, matching_messages: [snippets ≤5], match_terms}] ≤3
    def end_turn(self, turn: TurnContext, *, assistant_text: str, blocks: list, terminal_session_ids: list[str], diff_proposals: list, status: str = "complete", thread_id_override: str | None = None) -> None   # marks user row complete (or moves it to the new thread if switched), appends assistant row, updates last_active/domains/entities/turns_since_pause, refreshes receipt via build_receipt + upsert_receipt
    def mark_interrupted(self) -> int   # boot: any in_progress -> interrupted
    def tick(self) -> list[str]   # close paused threads past the grace window (paused_at older than GRACE_MINUTES or turns_since_pause of the successor >= GRACE_TURNS); builds final receipt; returns closed ids. Haloysius line + opt-in LLM summary are NOT in Plan A (hooks left as no-op callbacks: on_thread_closed: list[Callable[[dict], None]])
    def retract_recall(self, thread_id: str, recalled_thread_id: str) -> bool
    def current(self) -> dict | None
  get_thread_manager() singleton in BE/agents/threads.py using SqliteConversationStore(_DEFAULT_DB).

## 5. State machine / prompts / tools

StateContext (BE/agents/states.py) new fields: thread_id: Optional[str] = None; continuity_hint: str = ""; thread_switched: bool = False; thread_manager: Optional[Any] = None; recalled_threads: List[Dict[str, Any]] = field(default_factory=list)
AgentStateMachine (BE/agents/state_machine.py): `self.turn_lock = asyncio.Lock()` created in __init__; process(...) gains kwargs `thread_id: str = None, continuity: str = "", thread_manager=None`; process acquires turn_lock for its whole body (async with) — confirm_action likewise; `_transition(AgentState.PLANNING)` moved inside the try. Meta-tools handled in _handle_planning BEFORE `_already_called`: if tool_name in ("new_thread","recall_thread","resume_thread"): run `_handle_meta_tool(tool_name, tool_args)` (async) which mutates ctx and yields thread_started/thread_recalled, then `yield await self._transition(AgentState.PLANNING)`; return. No loop_count increment. Hint placement: `build_planning_prompt(query, context, plan, continuity=ctx.continuity_hint)` and `build_response_prompt(query, context, observations, history=ctx.conversation_history, continuity=ctx.continuity_hint)`.
Remove the `memory.store_interaction` call in _handle_responding (replace with a comment referencing the spec §7).
Events (BE/agents/events.py) new factories:
  thread_started(session_id, thread_id, title, reason="", previous_thread_id=None) -> type "thread_started"
  thread_recalled(session_id, thread_id, title, date, match_terms: list, mode: str)  # mode auto|tool
  thread_store_error(session_id, message)
  turn_persisted(session_id, thread_id, turn_id)
Tools (BE/tools/executor.py get_schemas): three schemas with descriptions ≤60 chars:
  new_thread {title: string, reason: string} ; recall_thread {query?: string, thread_id?: string} ; resume_thread {thread_id: string}
  execute() for these names returns {"success": True, "result": "handled inline"} (never reached in practice).
Safety (BE/tools/safety.py classify): add the three names to the SAFE branch.
Prompts (BE/prompts/agent_prompts.py): build_planning_prompt(..., continuity: str = "") inserts `continuity + "\n\n"` immediately before the "## Current Task" heading (find the exact heading text in the file; if absent, append before the final query line); build_response_prompt(..., history: list | None = None, continuity: str = "") renders history as "## Earlier in this conversation\n" + "**user**/**assistant**: …" lines (each ≤500 chars) then continuity, both immediately before the query section. Voice: wrap the continuity via existing voice helper if one exists (agent_prompts.py:48-69); otherwise plain.
LLM client (BE/model/client.py Ollama payload options ~line 489-495 and BE/agents/llm_client.py stream): add options.num_ctx computed by `compute_num_ctx(prompt_tokens_estimate: int, num_predict: int, model_max: int | None) -> int` = clamp(round_up(prompt_tokens_estimate + 512 + num_predict, 1024), 4096, model_max or 32768); cache per model name in a module dict; PLANNING num_predict 1024.

## 6. Route (BE/dashboard/routes/agent.py)

/message: remove the force-reset block; `tm = get_thread_manager()`; signals = `analyze_message(request.message)` (intake); `turn = tm.begin_turn(...)` inside `async with agent.turn_lock`? — NO: process() takes the lock itself; begin_turn is called by process() via thread_manager param to keep one lock. So: pass `thread_manager=tm` into agent.process(...); process() calls `tm.begin_turn` after acquiring the lock and before building StateContext, sets ctx.thread_id/continuity_hint/conversation_history/recalled_threads, yields `turn_persisted`; on completion (in `finally` of process) calls `tm.end_turn(...)` with assistant text = "".join(ctx.response_chunks), blocks from ctx.tool_calls (name,args,result), terminal ids from the terminal bridge collected in ctx (add ctx.terminal_session_ids: List[str] appended in _run_tool_streaming when a spawn event passes), diff proposals from ctx.pending_diffs, status "complete"|"cancelled"|"interrupted".
New endpoints: GET /api/agent/timeline?before=&around=&limit=50 -> {turns: [...], has_more: bool, current_thread: {thread_id, title, status}|null}; GET /api/agent/thread/current -> thread dict; DELETE /api/agent/thread/{thread_id}/recall/{recalled_thread_id} -> {ok}. Diff apply/reject: read from store (messages.diff_proposals_json) by diff id if session no longer active.
Delete: /agent/conversations list/get/delete endpoints (routes/agent.py ~889-926) and their frontend api wrappers.

## 7. Frontend

FE/types/timeline.ts:
  export interface TimelineToolBlock { tool: string; args: Record<string, unknown>; result?: unknown; exit?: number | null; executionId?: string }
  export interface TimelineTurn { turnId: string; threadId: string; timestamp: number; origin: 'human'|'assistant'|'terminal'|'task-notification'|'proactive'|'system'; user: { messageId: number; content: string; timestamp: number; status: 'in_progress'|'complete'|'interrupted'|'cancelled' } | null; assistant: { messageId: number; content: string; timestamp: number; status: string } | null; blocks: TimelineToolBlock[]; terminalBlockIds: string[]; diffProposals: DiffProposal[] }
  export interface TimelinePage { turns: TimelineTurn[]; hasMore: boolean; currentThread: { threadId: string; title: string; status: string } | null }
FE/lib/api.ts: getTimeline(params: {before?: string; around?: string; limit?: number}): Promise<TimelinePage>; getCurrentThread(); retractRecall(threadId, recalledThreadId). Remove listAgentConversations/getAgentConversation/deleteAgentConversation.
FE/hooks/useTimeline.ts: returns { turns, hasMore, loadOlder(), appendLive(turn: TimelineTurn), currentThread, setCurrentThread, byDay: Array<{ dayKey: string; label: string; turns: TimelineTurn[] }> } — dayKey = local YYYY-MM-DD; label = 'Today' | 'Yesterday' | 'Thu, Jul 14' (with year when not current year).
FE/hooks/useAgentStream.ts: AgentSession gains `thread?: { threadId: string; title: string } | null; recalled?: { threadId: string; title: string; date: string; matchTerms: string[] } | null; turnId?: string | null`. Handle events: thread_started -> session.thread; thread_recalled -> session.recalled (also push a ContextLoadedItem {id:`thread:${thread_id}`, source:'thread', label:`pulled in: ${title} · ${date}`, count:1}); turn_persisted -> session.turnId; thread_store_error -> console.warn once + session.error unchanged. reset(): must NOT call terminalSessionStore.clearOrigin any more (no New Conversation); keep cancel + clear local state.
FE/components/agent/ContextBar.tsx: ContextType adds 'thread'; TYPE_CONFIG.thread uses telemetry tokens only (`bg-status-telemetry-bg text-status-telemetry border-status-telemetry-line`) — add the missing `status.*-line` aliases in tailwind.config.js colors.status; ContextPill becomes <button type="button" aria-label=...> with a sibling remove <button aria-label="Drop … from context">; min text 11px (`text-[11px]`).
FE/components/agent/Timeline.tsx (new): renders byDay groups: <header className="thread-divider"><h2>{label}</h2><time dateTime=…/></header> then <article role="article"> per turn: user bubble (right) + assistant block (left) rendered from stored content (markdown via the same renderer AgentChat uses today) + static ToolExecutionCard per block (status derived from exit) + terminal chips for terminalBlockIds not in the live store (TetherChip-like static chip "terminal · ended") + static DiffBlock (read-only). Container role="feed" aria-busy while paging; "Load earlier" button at top when hasMore. Live turn (the one in flight) is rendered by AgentChat's existing assistant block, keyed by session.turnId, and appended to the timeline on response_complete.
FE/components/agent/CurrentTopicLabel.tsx (new): sticky one-line label `text-xs text-ink-secondary` showing currentThread.title (or nothing); aria-live off.
FE/components/agent/AgentChat.tsx: delete conversations state, loadConversations/loadConversation/startNewConversation/deleteConversation, the dropdown + "New Conversation" header controls, the `Session: …` footer; mount <CurrentTopicLabel/> + <Timeline/>; keep HostGreeting only when timeline is empty AND no live turn; keep composer/confirm/diff flows; add one visually-hidden <div role="status" aria-live="polite" aria-atomic="true"> in HostShell (FE/components/shell/HostShell.tsx) fed by a tiny module FE/lib/announce.ts `announce(text: string)` (sets state via a subscriber) — used for `Pulled in earlier work: <title>` and `New subject` on thread events.
FE/components/agent/TerminalTile.tsx: after mount() creates the xterm, write the existing session.output and set writtenRef.current = session.droppedChars + session.output.length.
FE/components/agent/InlineTerminals.tsx: render a static chip for ids the store does not know (label "terminal · ended"), never drop them.
FE/hooks/useAgentStream.ts: applyTerminalEvent unchanged; `terminalSessions` per turn continues; the timeline turn carries terminalBlockIds from the server after persistence.
Tests (vitest): FE/hooks/useTimeline.test.ts (day grouping, loadOlder, appendLive); FE/components/agent/Timeline.test.tsx (renders day headers as h2 + time, roles, static chips); FE/hooks/useAgentStream.thread.test.ts (thread_started/thread_recalled/turn_persisted reducers); FE/components/agent/TerminalTile.test.tsx (replay on mount: mock @xterm/xterm and assert write called with existing output).

## 8. Migration and deletions (BE)

BE/agents/migrations.py (new): def migrate_legacy_conversations(store: SqliteConversationStore) -> dict  # {"agent_json": n, "legacy_json": m}; reads ~/.halbert/conversations/*.json (agents/conversation.py shape) and ~/.config/halbert/conversations/*.json (routes/conversations.py shape: id, name, persona, messages[{id, role, content, timestamp ISO, ...}]); appends via append_message; sets threads status=closed and receipt via build_receipt; idempotent via a `migrations_done` table row per source path. Called once from dashboard/app.py startup after the store exists; also `ThreadManager.mark_interrupted()` at startup.
Delete: BE/dashboard/routes/conversations.py + its include in dashboard/app.py (~line 243); BE/agents/conversation.py: keep Conversation/Message dataclasses + content helpers, delete ConversationStore/SessionStore/get_conversation_store/get_session_store (grep every importer first and repoint to threads/SQLite); BE/agents/handlers/ package (and its re-export in agents/__init__.py); BE/dashboard/routes/agent.py /agent/conversations endpoints. Tests that import deleted symbols are updated/removed in the same task.

## 9. Ordering (tasks must be numbered in this order across planners)
  A1 store schema+WAL+append/update (planner S)  A2 receipt (S)  A3 store search/receipts fts (S)  A4 signals aliases/regex (S)  A5 thread_signals decide/build_hint (S)  A6 ThreadManager (S)
  A7 events+StateContext+tools schemas+safety (planner M)  A8 prompts continuity/history (M)  A9 state machine: lock, meta-tools inline, begin/end turn wiring, terminal ids on ctx, store_interaction removal (M)  A10 num_ctx (M)  A11 route: /message wiring, timeline endpoints, diff persistence, remove force-reset + conversations endpoints (M)
  A12 migrations + startup + deletions (planner D)  A13 backend e2e test (two messages, second sees first; new_thread; recall) (D)
  A14 types/api/useTimeline (planner F)  A15 useAgentStream thread events (F)  A16 ContextBar thread chip + tailwind aliases (F)  A17 Timeline + CurrentTopicLabel + announce/live region (F)  A18 AgentChat rewire (F)  A19 TerminalTile replay + InlineTerminals static chip (F)  A20 Playwright smoke script (F; uses the existing browser-automation skill approach: a node script under frontend/e2e/ that hits the dev server; document how to run, not required to pass in CI)
