# REVIEW: Config-Centric Continuity & Streamlined CLI Feedback

**Date**: 2026-09-04
**Reviews**: `.handoff/HANDOFF-CONFIG-CONTINUITY-AND-CLI-STREAMLINING-2026-09-04.md`
**Reviewer**: Halbert build session (Claude Code, Opus 5)
**Repository root**: `/Volumes/4TB-BAD/Halbert`
**Method**: every claim in the handoff was checked against the tree at `e98ce544`,
against the live `state_ledger.db` on this host, and against the cited OSS repo at
`/Volumes/Thunderbolt/AI/OSS/open-claude-code`. Nothing below is inferred from the
handoff's own prose.

---

## 0. How to read this

The handoff's **thesis is right** and its **reverse-engineering of Halbert's backend
is mostly accurate**. The problems are not in the idea; they are in a layer of
specifics that were written from a reading of the code rather than a run of it, plus
one citation to an external repo that does not survive inspection.

Findings are numbered `F1`–`F16` and carry a severity:

- **BLOCKER** — the phase cannot be built correctly, or would ship a lie, until this
  is resolved.
- **WRONG** — a factual claim in the handoff that is false. Building on it produces
  incorrect work.
- **GAP** — something true and important that the handoff omits.
- **HAZARD** — a pre-existing defect found while checking the plan. Not the
  handoff's fault, but it sits directly under the proposed work.

---

## 1. Verdict

**Proceed, with a resequenced plan.**

The founder's core paradigm — *config files, not chat sessions, are the continuity
anchors for a host steward* — is sound, and the claim that Halbert already owns the
backend is true. `StateStore`, `recall_state`, the provenance write paths, the
editor backup store, and `Timeline`'s `anchored` mode all exist and work as
described.

But four things must change before implementation:

1. Phase 1's design is **mis-attributed** to an OSS repo that does the opposite (F1).
   The design is still good; the citation must go, and the specific styling in the
   handoff would regress Halbert's design system.
2. The "Recent & Managed Configs" dock **would render empty on this machine**, and
   the reason is structural, not incidental (F6, F7). It reshapes Phases 2–3.
3. `backupCount` in the proposed payload **would report 0 for every file the agent
   changed**, because Halbert has two incompatible backup stores (F8).
4. The single most valuable pattern in the handoff — read-before-write — appears in
   "Lessons" and in **no phase of the roadmap** (F5). For a steward that edits `/etc`
   on the only host it has, this is the item with the highest safety return in the
   entire document.

---

## 2. What checks out

Verified directly. These claims are accurate and the plan may rest on them.

| Handoff claim | Verified at |
|---|---|
| `StateStore` exposes `current_state()`, `state_history()`, `why()` | `continuity/state_store.py:674`, `:709`, `:731` |
| `reason` and `actor` are keyword-only with no defaults; empty raises | `_require`, `state_store.py:180` |
| `UNRECORDED` is a real sentinel, never model-filled | `state_store.py:77`, and the docstring at `:45-47` |
| `recall_state(path=...)` answers deterministically | `continuity/recall.py:67` |
| `recorded_subjects()` returns every recorded subject | `continuity/recall.py:135` |
| `recall_memory` is a live, deterministic agent tool | `tools/recall_memory.py:212`, `:233`, `:240` |
| Editor saves snapshot to `~/.config/halbert/backups/<encoded>/<ts>.bak` | `routes/editor.py:91-95` |
| Editor saves call `_record_editor_change()` → `record_file_change()` | `routes/editor.py:289-311` |
| `Timeline` has an `anchored` prop and a "Back to latest" control | `Timeline.tsx:55`, `:673-681` |
| No recent-configs surface or route exists anywhere | repo-wide grep for `recent-configs`/`recent_configs`: 0 hits |
| `ToolExecutionCard` renders `JSON.stringify(execution.args)` | `ToolExecutionCard.tsx:140-141` |
| The card header shows the raw internal tool name | `ToolExecutionCard.tsx:110` |

Four live write paths feed `file:` subjects into the ledger, so the "foundation
already exists" claim is genuinely true:

- `tools/write_config.py:85`, `:113` (agent)
- `config/watcher.py:164` (system, on external change)
- `dashboard/routes/agent.py:1902` (agent, via the diff-apply route)
- `dashboard/routes/editor.py:304` (user, via the editor)

---

## 3. The OSS repo audit

The handoff draws three lessons from `/Volumes/Thunderbolt/AI/OSS/open-claude-code`.
All three were checked line by line.

### F1 — §3.1 "Clean Command Presentation" is fabricated · **WRONG**

The handoff states:

> **Clean Command Presentation** (`open-claude-code/v2/src/tools/bash.mjs`):
> Never prints JSON schemas. Extracts `command` and displays `$ <command>` with exit
> status code and elapsed time.

`bash.mjs` is 148 lines and **renders nothing**. It is a tool implementation. Its
output is a string handed back to the model:

```js
// v2/src/tools/bash.mjs:100-104
const output = (stdout + (stderr ? '\n' + stderr : '')).trim();
if (code !== 0) {
    resolve(`Exit code: ${code}\n${output}`.trim());
} else {
    resolve(output || '(no output)');
}
```

The actual presentation lives in the UI layer, and it does the opposite of what the
handoff describes:

```js
// v2/src/ui/components.mjs:114-116  (ToolMessage)
h(Text, { color: 'yellow', key: 'label' }, '[', name, '] '),

// v2/src/ui/ink-app.mjs:210-215  (formatToolResult)
return `${c('cyan', `[${toolName}]`)} ${display}`;
```

That renders `[Bash] running…` and `[Bash] <first 200 chars of result>`: **the raw
tool name, no command text, no exit code, no elapsed time.** A repo-wide grep for a
`$ `-prefix rendering returns zero hits. `renderToolProgress` (`ink-app.mjs:144`) is
`>> <toolName> <status>` — again the raw name.

The handoff's own comparison table in §3 gets this right (`• Single-line spinner
(>> [Bash] running)`) and then contradicts itself one paragraph later.

**Why it matters.** Phase 1 is currently justified by an external precedent that does
not exist. Worse, the reference implementation is *behind* Halbert: Halbert already
shows `exit N · 1.2s` (`ToolExecutionCard.tsx:108-111`) and a `$ <cmd> · exit N`
one-liner for short blocks (`:127`). Building Phase 1 "to match open-claude-code"
risks someone later reading the source and reverting toward `[run_command]`.

**Action.** Keep the design; delete the citation. Phase 1 is a locally invented
improvement over both Halbert's current card *and* the cited repo, and should be
described that way.

### F2 — §3.2 "Pre-Read Verification" is accurate · **CONFIRMED**

```js
// v2/src/tools/read.mjs:19-27
const readFiles = new Set();
export function hasBeenRead(filePath) {
    return readFiles.has(path.resolve(filePath));
}
export function markRead(filePath) {
    readFiles.add(path.resolve(filePath));
}
```

Enforced at both write sites: `tools/edit.mjs:43` and `tools/write.mjs:34` reject a
write to a file that has not been read, and `markRead` after a successful write
(`edit.mjs:76`, `write.mjs:49`).

Cited line range in the handoff (`#L21-L27`) is correct. See F5 for why this is the
most important line in the document.

### F3 — §3.3 "Micro-Compaction" is accurate, and cleaner than described · **CONFIRMED**

```js
// v2/src/core/context-manager.mjs:14
const STALE_TOOL_RESULT_TURNS = 5;
```

`microCompact` (`:70-112`) walks backwards to find the Nth-most-recent `user`
message, treats that index as a boundary, and for every message *before* it truncates
only `tool_result` blocks longer than 200 chars down to 100 chars + `...[truncated]`.
`text` and `thinking` blocks are never touched. `compact()` (`:122+`) tries
micro-compaction first and only falls through to summarisation if still over
threshold.

The handoff describes this correctly. See F11 for why it should still not be built as
a new system.

### F4 — Tool-name vocabulary comes from neither source · **WRONG**

The handoff's tier lists name `grep_search`, `list_dir`, `check_drift`, `apply_diff`,
`systemctl_action`, `write_config`.

**Halbert's actual registered tool names** (from `tools/`):
`read_file`, `list_directory`, `run_command`, `recall_memory`, `write_file`,
`read_log_tail`, `get_service_status`, `list_running_services`, `check_disk_space`,
`check_process`, `get_system_load`, `get_network_info`, `recall_thread`,
`new_thread`, `resume_thread`, `web_search`, `terminal_blocks`, and the vision/GPU
families.

**The OSS repo's tool names**:
`Agent, AskUser, Bash, CronCreate, CronDelete, CronList, Edit, EnterWorktree,
ExitWorktree, Glob, Grep, LS, LSP, MultiEdit, NotebookEdit, Read, ReadMcpResource,
RemoteTrigger, SendMessage, Skill, TodoWrite, ToolSearch, WebFetch, WebSearch, Write`.

So `grep_search`/`list_dir`/`check_drift`/`systemctl_action` appear in **neither**.
They are Cursor/Antigravity's tool vocabulary, carried in by the authoring tool.
`apply_diff` is not a tool at all in Halbert — it is a route endpoint
(`routes/agent.py:1917`) and a string in a write-tool name list
(`agents/receipt.py:50`).

**Why it matters.** Implemented verbatim, roughly half the tier map never matches a
real execution. `list_directory` — one of the noisiest inspection calls — would keep
rendering as a full card, and the InspectionGroup would appear to "not work" for
reasons that look like a React bug and are actually a typo'd registry.

**Action.** Rewrite both tiers against the real registry before writing the
component. Suggested:

- Tier 1 (ephemeral): `read_file`, `list_directory`, `recall_memory`,
  `recall_thread`, `get_service_status`, `check_process`, `check_disk_space`,
  `get_system_load`, `get_network_info`, `read_log_tail`, `web_search`.
- Tier 2 (persistent): `run_command`, `write_file`, `write_config`, `new_thread`,
  and anything with `side_effects = True` on its `BaseTool` subclass.

The `side_effects` flag already exists (`tools/write_config.py:20`) and is a better
discriminator than a hand-maintained list — it cannot drift out of sync with the
registry.

---

## 4. The buried lede

### F5 — Read-before-write is in "Lessons" and in no phase · **GAP, highest value**

§3.2 records `hasBeenRead` as a lesson and the roadmap never mentions it again.

For a coding agent, a blind write clobbers a file. For **a host steward that edits
`/etc` on the only machine it has**, a blind write to `fstab`, `sshd_config` or a
systemd unit can cost the boot, the network, or the remote session Halbert is being
used through. This is the highest-consequence gap in the plan.

**Halbert currently has no guard of any kind on either write path.**

`tools/write_config.py` reads the file before writing, but only to compute a digest —
it never compares it to anything:

```python
# tools/write_config.py:95
before_txt = self._read(path)
# ... apply ...
# :108  record_file_change(before_text=before_txt, after_text=...)
```

`routes/editor.py`'s request model has no conditional field at all:

```python
# routes/editor.py:38-45
class FileWriteRequest(BaseModel):
    path: str
    content: str
    create_backup: bool = True
    backup_label: str = "Manual save"
    reason: Optional[str] = None
```

No `expected_sha256`, no `If-Match`. Both paths silently clobber a change made by
anything else since the content was read.

**Halbert can do materially better than `hasBeenRead`, nearly for free.**

`hasBeenRead` is a process-local `Set`. It is lost on restart, it cannot see a change
made by another process, and it produces no explanation when it refuses.

The ledger **already stores `content_sha256` as the open triple for every recorded
file**. So a compare-and-swap is available:

1. Before applying, read the file and compute its digest.
2. Fetch the ledger's current open triple for `file:<path>` / `content_sha256`.
3. If the ledger has a record and the digests differ, the file changed outside
   Halbert. Refuse the apply and surface *what* changed and *when the ledger last saw
   it* — an answer, not just a rejection.
4. If the ledger has no record, fall back to a read-before-write requirement, and
   record the digest so the next write has a baseline.

This is strictly stronger than the OSS pattern: it survives restart, catches
third-party edits, and yields a human-readable reason.

**This is also the correct home for `continuity/freshness.decide()`.**

Commit `82f25ff2` left `continuity/freshness` unwired and argued, correctly:

> continuity/freshness stays unwired, and the obvious repair is wrong. `recall_memory`
> answers what was recorded and why — a historical question. `decide()` answers
> whether to trust something as current. A recall that silently probed the filesystem
> would stop being a ledger read while still answering like one.

That reasoning is about **recall**. It does not apply to **writes**, where probing the
host is the entire point of the operation. `decide(subject, predicate, store,
fresh_seconds)` (`continuity/freshness.py:116`) returns `PROBE` when the ledger has
never seen a subject and `PROBE` when its reading is stale — exactly the two cases a
write path must handle differently. The backlog item marked "the obvious repair is
wrong" has a non-obvious repair that is right.

**Action.** Promote this to Phase 0. It has no dependency on the dock, the API, or
any frontend work, and it retires a standing backlog item correctly.

---

## 5. Why the dock would ship empty

### F6 — The ledger holds zero `file:` subjects on this host · **BLOCKER**

Queried live at `~/.local/share/halbert/state_ledger.db`:

```
tables:                 state_triples, state_triples_pre_provenance, sqlite_sequence
total rows:             442
by subject prefix:      thread:  442  (221 open)
distinct file subjects: 0
predicates:             entity  442
```

Every row is a `thread:`/`entity` row. The proposed route —

> Queries `StateStore` for distinct `subject` entries starting with `file:` ordered by
> `valid_from DESC`

— returns `[]`. The "Recent & Managed Configs" dock, the "Jump to Conversation"
affordance, and the AI prompt hydration all have nothing to operate on.

This is consistent with `82f25ff2`'s own aside ("needs open `file:` rows, of which
there are now zero"), which the handoff did not pick up.

### F7 — Root cause: the ConfigWatcher cannot run on this machine · **BLOCKER**

The only component that populates `file:` rows *passively* — without a human editing
something through Halbert — is the ConfigWatcher, which records external changes with
`actor=system` and a self-naming reason (`config/watcher.py:143-173`).

It cannot start here, for two independent reasons.

**Reason 1 — it is gated to Linux.**

```python
# dashboard/app.py:813-816
from ..utils.platform import is_linux
if not is_linux():
    logger.info("Config watcher not started (Linux hosts only)")
    return
```

This host is darwin.

**Reason 2 — the capability probe fails anyway.**

```python
# capabilities.py:155-173
def _probe_config_watcher() -> bool:
    """Does a config-registry.yml exist (something to watch)?"""
    candidates = [
        get_config_dir() / "config-registry.yml",
        Path("/etc/halbert/config-registry.yml"),
    ]
    return any(p.exists() for p in candidates)
```

`config/config-registry.yml` exists **in the repo** but is not installed to either
candidate location on this host, so `CAP_CONFIG_WATCHER` probes false and
`start_config_watcher` is never even called (`app.py:807-808`).

**And the registry itself is Linux-shaped:**

```yaml
include:
  - /etc/**/*.conf
  - /etc/systemd/*.service
  - /etc/default/*
exclude:
  - /etc/ssl/**
  - /etc/shadow
```

**Why it matters — this reshapes the plan, not just a test.**

The entire feature narrative is Linux: `/etc/fstab`, `bcachefs` mount flags,
`/etc/samba/smb.conf`, `systemd` restart policy for `sshd`. The development host is
macOS. §6.4's verification step — *"Edit `/etc/samba/smb.conf` via chat. Verify it
appears in the Recent Configs dock"* — **cannot be executed on this machine.**

The plan silently assumes a host it does not have. That assumption needs to become an
explicit decision before Phase 2 starts. Three viable options:

| Option | Cost | What it buys |
|---|---|---|
| **A. Target a Linux host** for Phases 2–3 (the N150 box, a VM, or a container) | Setup time; a second environment in the loop | Real rows, real verification, matches the product narrative |
| **B. Author a macOS registry** and lift the `is_linux()` gate | Must decide what macOS "config" means: `/etc/`, `/Library/LaunchDaemons`, `/opt/homebrew/etc`, `~/Library/Preferences` | Dogfooding on the dev machine; broadens the product |
| **C. Seed fixtures** for development, verify for real on Linux later | Cheapest now | Ships a surface nobody has seen carry real data — the exact failure mode this review is trying to prevent |

Recommendation: **A for verification, B as a follow-on product decision.** C only as a
supplement, never as the acceptance criterion.

**Regardless of which is chosen, the dock needs an honest empty state.** "Nothing
recorded yet" is a legitimate answer and must not render as "no configs are managed",
which is a different and false claim. This is the same distinction `routes/state.py`
already draws in its module docstring and its 503-vs-`found:false` handling — the
dock must inherit it.

---

## 6. Two incompatible backup stores

### F8 — `backupCount` would report 0 for every agent-made change · **BLOCKER**

The handoff treats backups as a single store. There are two, and they do not know
about each other.

| Path | Location | Generations kept |
|---|---|---|
| `routes/editor.py` (user) | `~/.config/halbert/backups/<encoded_path>/<timestamp>.bak` + metadata JSON with hash and label | many, timestamped |
| `tools/write_config.py` (agent) | `shutil.copy2(path, f"{path}.bak")` — a **sibling file** | **exactly one, overwritten every write** |

```python
# tools/write_config.py:156-157, :180-181, :216-217  (yaml / json / ini branches)
if backup and os.path.exists(path):
    shutil.copy2(path, f"{path}.bak")

# tools/write_config.py:62-67  (rollback branch reads the sibling)
bak = f"{path}.bak"
if not os.path.exists(bak):
    return ToolResponse(..., error=f"backup not found: {bak}", ...)
```

**Three consequences.**

1. **The agent's second write destroys the rollback point for its first.** Only one
   generation ever exists. The user-facing editor keeps a full history; the agent —
   the actor more likely to make an unattended change — keeps one.
2. **`.bak` files land inside system config directories.** `/etc/samba/smb.conf.bak`
   is written to `/etc/samba/`, outside any store Halbert tracks, prunes, or lists.
   Several config systems glob their directories; a stray sibling file in a `*.d/`
   tree is at best litter and at worst parsed.
3. **The proposed payload lies.** `backupCount` reads
   `~/.config/halbert/backups/<encoded>/` only. Every file the *agent* changed
   reports `0`. The dock would tell the founder that Halbert's own changes cannot be
   rolled back — both false and precisely backwards from the surface's purpose.

**Action.** Phase 4's "connect `editor.py` automatic backups to all agent file
writes" is right in direction but understates the work. It is a **reconciliation**:
`write_config`'s rollback branch reads `<path>.bak` and must be migrated with the
writer, or rollback breaks. Sequence it as: (1) move `write_config` onto the editor
backup store, (2) repoint its rollback branch at that store, (3) leave existing
`<path>.bak` files on disk unread — per the standing "no users, no legacy support"
rule, do not build a migration and do not delete them.

### F9 — The backup path encoding is ambiguous · **HAZARD**

```python
# routes/editor.py:91-95
encoded = file_path.replace("/", "_").replace("\\", "_")
backup_dir = get_config_dir() / "backups" / encoded
```

`/etc/foo_bar` and `/etc/foo/bar` both encode to `_etc_foo_bar` and share a backup
directory. Two consequences for the proposed route: `backupCount` can over-report,
and the encoding cannot be reversed, so a future "also list files that have backups
but no ledger row" enhancement is impossible without a stored path in the metadata.

The metadata JSON alongside each `.bak` is the natural place to record the true path.
Worth doing now, while the store is being reconciled anyway (F8).

---

## 7. Three config-dir resolvers that disagree

### F10 — `config_dir` has three implementations, two answers on macOS · **HAZARD**

| Resolver | Honours `HALBERT_CONFIG_DIR`? | macOS result |
|---|---|---|
| `utils/platform.py:302` `get_config_dir()` — used by `_probe_config_watcher` | yes | `~/Library/Application Support/Halbert` |
| `utils/paths.py:39` `config_dir()` — the CFG-1 resolver, XDG + root aware | yes | `~/.config/halbert` |
| `routes/editor.py:82` `get_config_dir()` — hardcoded | **no** | `~/.config/halbert` |

`routes/editor.py`'s copy hardcodes `Path.home() / ".config" / "halbert"`, so it
ignores `HALBERT_CONFIG_DIR`, ignores `XDG_CONFIG_HOME`, and ignores the root case
(`utils/paths.config_dir()` returns `/etc/halbert` when running as root). The state
ledger honours its equivalent override (`state_store.py:164-178`, explicitly citing
CFG-1); the editor's backups and sessions do not.

**Observed effect.** `~/.config/halbert/backups/` on this machine currently contains
four directories, all four of them named `_var_folders_..._T_ledger-probe-..._sshd_config_*` —
temp-path debris from an out-of-tree probe script, and zero real backups. The
committed suite's `_isolated` fixture (`tests/test_provenance_wiring.py:30-33`) sets
`HALBERT_DATA_DIR` and `HALBERT_LOG_DIR` but not `HALBERT_CONFIG_DIR` — and setting it
would not have helped, because `editor.py` never reads it. Any test that exercises
`POST /file` writes into the founder's real home.

This is the same class of defect as commit `20af0165` ("stop the suite writing the
real ledger and audit chain"), unfixed for the editor's stores.

**Why it blocks Phase 2.** The recent-configs route must correlate ledger rows
(`~/.local/share/halbert/`) with backup directories (`~/.config/halbert/backups/`)
while the capability probe looks somewhere else entirely on macOS
(`~/Library/Application Support/Halbert/`). Pick one resolver — `utils/paths.config_dir()`,
the CFG-1 one — and route the other two through it before building anything that
joins these stores.

---

## 8. The remaining plan-level findings

### F11 — Micro-compaction is already owned · **WRONG (duplicate work)**

`compact_boundaries` exists in the conversation schema
(`agents/conversation_sqlite.py:370-386`) with the comment *"compaction stays
default-off until a later plan"*, and there is a separate 3-tier context compression
system with its own routes (`dashboard/routes/compression.py`). Building a second
micro-compaction path would give Halbert two systems answering the same question.

**Action.** If micro-compaction is wanted, it is ~30 lines written into the existing
seam — a writer for `compact_boundaries` using the truncation rule from F3 — not a
new subsystem. Otherwise cut §3.3 from the plan entirely.

### F12 — "Jump to Conversation" has no join key · **BLOCKER**

```ts
// hooks/useTimeline.ts:41
loadAround: (turnId: string) => Promise<void>;
```

It needs a **turn id**. The ledger's columns are:

```
id, subject, predicate, object, source, confidence, valid_from, valid_to,
thread_id, reason, actor, request_id, closed_reason, closed_by, closed_by_request
```

There is no `turn_id`. And the conversation store's `messages`/`conversations` tables
carry no `request_id`, so there is no indirect join either. (`terminal_blocks` *does*
carry `turn_id` at `conversation_sqlite.py:396` — but only terminal blocks do.)

The proposed payload returns `threadId`, which can anchor a *thread*, not the turn
where the config was touched.

**Three ways out**, in order of preference:

1. **Record `turn_id` on the ledger row.** `record_file_change` already accepts an
   optional `thread_id` (`continuity/provenance.py:128`); adding `turn_id` alongside
   it is symmetric. The store already has `_ADDITIVE_COLUMNS` machinery
   (`state_store.py:161`, `_add_missing_columns` at `:416`) for exactly this kind of
   additive schema change. Cost: one column, one parameter, four call sites.
2. **Anchor by thread + timestamp** — load the thread and scroll to the turn nearest
   `valid_from`. Cheap, approximate, and will occasionally land a turn or two off.
3. **Anchor at the thread only** — honest, much less useful than what §4.1 promises.

Option 1 is the only one that delivers the described behaviour. It must land *before*
Phase 3, and ideally at the same time as Phase 0 (F5), since both touch
`record_file_change`.

### F13 — Grouping has two render sites, and a redaction invariant · **GAP**

The handoff names `ToolExecutionCard.tsx` and a new `InspectionGroup.tsx`. Tool cards
are rendered in **two** places:

- `AgentChat.tsx:1132` — the live stream, from `session.toolExecutions`.
- `Timeline.tsx:405` — persisted history, from `turn.blocks` via `executionFromBlock`.

Both need the grouping, or history and the live feed will disagree about what the same
turn looked like.

More importantly, `Timeline.tsx` carries an invariant the grouping must not break:

```ts
// Timeline.tsx:104-108
* A redacted block never reaches any of this: `isRedactedBlock` answers it at
* the render site first. The marker the store leaves behind for a forgotten
* row carries neither an exit code nor a status, so it would land on that
* same default and paint a green ✓ Success on a turn an admin asked to
* forget — the one thing this whole ordering exists to prevent.
```

An `InspectionGroup` that folds consecutive blocks into `⚡ Inspected 3 files` must
answer `isRedactedBlock` **before** counting, and must keep `RedactedToolCard` visible
as its own element. A forgotten tool call silently becoming an anonymous increment in
a summary count is a quieter version of the same bug that comment exists to prevent.

### F14 — §4.1's hydration block re-introduces a rejected conflation · **WRONG**

The proposed prompt block ends:

```
Current sha256: 8f1a2b... (verified intact on disk)
```

`recall_state` does not verify anything on disk, deliberately — see the quotation in
F5. As written, the hydration block would either (a) print a claim that is not true,
or (b) be implemented by wiring a filesystem probe into recall, which is the exact
change `82f25ff2` declined.

**Action.** Either drop the parenthetical, or make drift an explicit, separately
labelled line sourced from a probe that says it is a probe:

```
[Context: /etc/samba/smb.conf]
Last recorded: 2026-09-01 by agent
Reason: "Added [backups] share with path /mnt/storage/backups"
Recorded sha256: 8f1a2b…
Drift check (probed just now): matches / DIFFERS — the file changed outside Halbert
```

Two further notes on §4.1:

- **There is already a tested `continuity=` slot in the prompt builder.**
  `AgentPromptBuilder.build_planning_prompt(..., continuity=...)` places the block
  immediately before `## Current Task`, with a per-voice preamble and a
  `tools_supported=False` variant — all covered by
  `tests/test_agent_prompts_continuity.py`. It currently carries *thread* continuity
  ("Thread: 'Scanner share' · 2 turns"). Config continuity should extend that seam,
  not invent a new injection point.
- **Push-hydration partially duplicates `recall_memory`.** The ledger already answers
  on demand through a deterministic tool. Injecting a block on every file mention
  spends tokens on every turn to save a tool call on some turns. That may well be the
  right trade for a steward, but it is a trade, and the handoff does not acknowledge
  it. Decide it explicitly.

### F15 — Route placement splits the ledger read surface · **WRONG (minor)**

The handoff puts `GET /api/continuity/recent-configs` in `routes/editor.py`.

`routes/state.py` already **is** the ledger read surface — `/why`, `/history`,
`/by-request` — mounted at `/api/state` (`app.py:555`, tagged *"LEDGER-1: why is X
configured this way"*). Nothing in the codebase uses an `/api/continuity` prefix.

Putting a fourth ledger read behind a new prefix, in the Phase-18 config-editor
module, splits one surface across two files and three prefixes for no benefit.

**Action.** `GET /api/state/recent-configs` in `routes/state.py`. It should also
inherit that module's established error contract: 503 when the ledger cannot be read,
never a 200 with an empty list — because "I could not look" and "there is nothing
recorded" are different answers, and the module's docstring already says so.

### F16 — Phase 1's styling would regress the design system · **WRONG (minor)**

The proposed snippet:

```tsx
<span className="text-emerald-400 font-bold">$</span>
<Badge variant={exitCode === 0 ? "success" : "destructive"}>
  {exitCode === 0 ? "✓ 0" : `✗ ${exitCode}`}
</Badge>
```

Three problems:

1. **`text-emerald-400` hardcodes a colour.** No component under `components/agent/`
   hardcodes one — a grep for `emerald-`/`text-green-`/`bg-red-` across that directory
   returns zero hits. They use semantic tokens: `text-status-nominal`,
   `text-status-critical`, `text-status-telemetry`, `bg-status-*-bg`,
   `border-status-*-line`. The canonical palette lives at `/shared-tokens/tokens.css`.
2. **`Badge variant="success"` is `bg-green-500` hardcoded** (`ui/badge.tsx:18-19`),
   so it launders a hardcoded colour through a component name.
3. **"Success"/"Error" naming contradicts a decision recorded in the file being
   edited.** `ToolExecutionCard.tsx:111` reads: *"Plan B: labels are measurements, not
   'Success'/'Error'"*, and the card renders `exit 0 · 1.2s` accordingly.

**Action.** Keep the `$ <command>` header. Render status with the existing
`StatusLight` and the measurement label the file already uses. The genuinely new parts
of Phase 1 — removing the Arguments `<pre>`, the >6-line output drawer, the copy
button — stand on their own.

---

## 9. What to take from the OSS repo, and what to reject

### Take

| Pattern | Source | Halbert application |
|---|---|---|
| Read-before-write, **upgraded to digest CAS** | `read.mjs:21-27`, enforced `edit.mjs:43`, `write.mjs:34` | Phase 0. See F5. The ledger's `content_sha256` makes the strong form nearly free. |
| Micro-compaction truncation rule | `context-manager.mjs:70-112` | Write into the existing `compact_boundaries` seam, not a new system. See F11. |
| Explicit truncation marker | `bash.mjs:19, 84-88` — `[output truncated at 1MB]` | Halbert's `terminal_blocks` already stores `output_head`/`output_tail`, which is better — but the *visible* marker telling the reader output was cut is worth copying. |

### Reject

**`CheckpointManager`** (`core/checkpoints.mjs`) — the handoff's comparison table
lists it as a v2 strength. It is weaker than what Halbert already has:

```js
this.history = [];          // :20  in-memory only — lost on restart
this.maxCheckpoints = 50;   // :21
// undo() at :70 deletes the checkpoint file after restoring
```

No reason, no actor, no digest, no persistence of the stack, and restoring destroys
the restore point. Halbert's editor backups already beat this on every axis.

**The one thing worth borrowing from it**: a *global* undo stack across files.
Halbert's backups are per-file directories, so "roll back the last thing Halbert did"
currently requires scanning every directory and comparing timestamps. Phase 4's
"1-click Rollback Change" needs an ordered index — and the ledger already is one:
`state_triples` ordered by `valid_from DESC` with `request_id` is exactly the global
undo stack, provided F8's backup reconciliation gives every entry a restorable
artefact.

**`SessionManager`** (`core/session.mjs`) — one `session.json` per project hash,
whole-file rewrite on save, resumes by replacing the message array. Strictly weaker
than Halbert's SQLite thread store with turns, terminal blocks, open loops, FTS and
compaction boundaries. It confirms §1.1's premise about session-based tools; there is
nothing to lift.

**`ui/app.mjs:152-156`'s result matching** — an anti-pattern to avoid:

```js
const idx = prev.findLastIndex(
    m => m.role === 'tool' && m.toolName === event.tool && m.toolStatus === 'running'
);
```

It matches a completed result to a running card **by tool name**, so two concurrent
`Read` calls resolve into the wrong slot. Halbert already keys on `executionId`
(`AgentChat.tsx:1132`, `Timeline.tsx:406-407`). When building the
`InspectionGroup`, keep keying on `executionId` — grouping must not become a reason to
match by name.

---

## 10. Revised sequencing

| Phase | Work | Blocked by |
|---|---|---|
| **0** | **Read-before-write / digest CAS** on `write_config` and `POST /file`; wire `freshness.decide()` into the write path; add `expected_sha256` to `FileWriteRequest` | nothing |
| **0b** | Add `turn_id` to `record_file_change` + ledger column (additive) — same call sites as Phase 0 | nothing |
| **0c** | Collapse the three `config_dir` resolvers onto `utils/paths.config_dir()` | nothing |
| **1** | Card cleanup: drop the Arguments `<pre>`, `$ <command>` header **in tokens**, >6-line output drawer, copy button | 0c is not required but avoids rework |
| **1b** | `InspectionGroup`, tiers keyed off `side_effects` / the real registry, applied at **both** render sites, redaction answered first | F4, F13 |
| **2a** | **Decide the target host** (Linux target / macOS registry / fixtures) | founder decision |
| **2b** | Reconcile the two backup stores; record the true path in backup metadata | F8, F9 |
| **2c** | `GET /api/state/recent-configs` in `routes/state.py`, with the 503-vs-empty contract and an honest empty state | 2a, 2b |
| **3** | `RecentConfigsDock.tsx`; "Edit in Monaco"; "Jump to Chat" via `loadAround(turn_id)` | 0b, 2c |
| **4** | Global rollback index off the ledger; "Rollback Change" on `DiffBlock.tsx` | 2b |
| **—** | §3.3 micro-compaction: fold into `compact_boundaries` or cut | F11 |
| **—** | §4.1 hydration: extend the existing `continuity=` slot; drop "verified intact on disk" | F14 |

---

## 11. Corrections to the verification plan

§6 as written cannot be executed. Replacements:

1. **CLI rendering** — unchanged and valid. Add: assert no `text-emerald-*` or
   `Badge variant="success"` appears in the diff.
2. **Inspection grouping** — must be verified in **both** `AgentChat` and a reloaded
   `Timeline`, and must include a turn containing a redacted block, asserting the
   `RedactedToolCard` still renders separately and is not counted into the pill.
3. **Recent Configs route** — `curl` is valid, but the *precondition* is missing:
   state which host, and how `file:` rows got there. On this machine today the
   correct expected result is `[]`, and the test should assert the empty state
   renders as "nothing recorded yet" rather than as an absence of managed configs.
   Add a 503 case: make the ledger unreadable, assert the route does not answer `[]`.
4. **Dock & anchored jump** — `/etc/samba/smb.conf` does not exist on the dev host.
   Either run this on the Linux target, or substitute a real macOS path once the
   registry decision (F7) is made. Assert the jump lands on the *turn*, which
   requires Phase 0b.

Add a fifth:

5. **Write guard** — modify a tracked file outside Halbert, then ask Halbert to edit
   it. Assert the write is refused, that the refusal names the drift, and that the
   ledger's recorded digest is quoted in the message.

---

## 12. Open questions for the founder

1. **Target host for Phases 2–3?** (F7) Linux target, macOS registry, or fixtures.
   This is the single decision that most changes the shape of the work.
2. **Should the ConfigWatcher's `is_linux()` gate be lifted?** If Halbert is to be a
   steward of *this* Mac, something has to watch this Mac's configs. If it is not,
   the product narrative should stop using this machine as the example.
3. **Push-hydration vs. pull-recall** (F14): spend tokens on every turn, or trust the
   agent to call `recall_memory`? Or hydrate only when the user's message contains a
   path the ledger knows?
4. **On a CAS refusal, what does Halbert do?** Hard refuse, or show the drift and
   offer to proceed? For `/etc/fstab` the answer is probably "refuse". For a dotfile
   it is probably "show and offer".
5. **Does the dock list files with backups but no ledger rows?** If yes, F9's path
   encoding must be fixed first, because the path cannot be recovered from the
   directory name.

---

## 13. Reproduction

Every finding above is reproducible from the repo root.

```bash
# F6 — the ledger has no file: subjects
python3 - <<'PY'
import sqlite3, os
db = os.path.expanduser('~/.local/share/halbert/state_ledger.db')
c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
print('total:', c.execute("select count(*) from state_triples").fetchone()[0])
print('file subjects:', c.execute(
    "select count(distinct subject) from state_triples where subject like 'file:%'"
).fetchone()[0])
PY

# F1 — the OSS repo never renders "$ <command>"
grep -rn "'\$ '" /Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/   # 0 hits
sed -n '114,120p' /Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/ui/components.mjs
sed -n '210,216p' /Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/ui/ink-app.mjs

# F4 — the OSS tool registry
grep -h "^    name: '" /Volumes/Thunderbolt/AI/OSS/open-claude-code/v2/src/tools/*.mjs | sort

# F7 — the watcher gate and the capability probe
sed -n '803,820p' halbert_core/halbert_core/dashboard/app.py
sed -n '155,173p' halbert_core/halbert_core/capabilities.py
ls ~/.config/halbert/config-registry.yml   # No such file

# F8 — two backup stores
grep -n 'copy2(path, f"{path}.bak")' halbert_core/halbert_core/tools/write_config.py
sed -n '91,95p' halbert_core/halbert_core/dashboard/routes/editor.py

# F10 — three config_dir resolvers
grep -n "def get_config_dir" -A 3 halbert_core/halbert_core/utils/platform.py
grep -n "def config_dir" -A 3 halbert_core/halbert_core/utils/paths.py
sed -n '82,87p' halbert_core/halbert_core/dashboard/routes/editor.py
ls ~/.config/halbert/backups/   # 4 dirs, all ledger-probe test debris

# F12 — no turn_id on the ledger
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.local/share/halbert/state_ledger.db')
c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
print([r[1] for r in c.execute('PRAGMA table_info(state_triples)')])"
```

---

## 14. Process note

Neither `ROADMAP.md` nor `DECISIONS.md` mentions "Recent & Managed Configs", the
two-tier tool split, or the CLI streamlining work. Per the 2026-09-02 alignment
review, those two documents are the planning spine. If this work is going ahead, the
phases above should land as ROADMAP rows and the F7 host decision as a DECISIONS
entry — otherwise the plan lives only in `.handoff/`, which is where the previous
round of drift started.

---

## 15. Phase 0 done, and two corrections to this document

Branch `feat/write-guard`, 2026-09-04. Phases **0**, **0b** and **0c** are
implemented; 1 and 1b landed earlier on `feat/cli-in-conversation`.

### Correction 1 — F5 named two write paths. There are three, and it missed
### the one that matters

F5 said Halbert has no read-before-write guard on "either write path",
meaning `write_config` and `POST /file`. **`write_file` is the tool the agent
actually writes files with** — it is in the schema list handed to the model —
and it wrote to any path on the machine while recording *nothing*: no audit
row, no ledger triple, no reason, no actor, no backup, and no check that the
file was still what Halbert last saw.

Four write paths called `record_file_change`. That was the fifth, and it was
the agent's. LEDGER-1's premise — that the ledger answers why any config is
the way it is — had a hole the size of the tool that changes them.

It now records on both planes and looks first, and the tool schema gains a
`reason` field so the model has somewhere to state why.

### Correction 2 — F10 named the wrong resolver as canonical

F10 recommended collapsing onto `utils/paths.config_dir()`, on the strength
of its XDG and root handling. Following that would have been a serious
mistake: **fourteen call sites hold Halbert's actual config behind
`utils/platform.get_config_dir()`** — `being.yml`, `preferences.yml`,
`models.yml`, `gpu_config.yml`, `web_search.yml`, `vision_config.yml`, the
config-registry probe — while *nothing* imported `paths.config_dir` for a
config file at all. Moving to it would have left Halbert unable to find its
own `being.yml` on macOS.

The collapse went the other way. `paths.config_dir` and the editor's
hardcoded copy now delegate to the platform resolver, and the root branch —
the only thing `paths.config_dir` had that the platform one did not — moved
across rather than dying.

F10 also understated the damage. Both directories were live on the dev
machine, and `being.yml.lock` existed in **both**. The advisory lock is
derived from the config path, so two callers resolving `being.yml`
differently take out two different locks and neither sees the other: the
one-writer guarantee on the file holding the machine's own settings was void,
silently, on every macOS install.

### What Phase 0 shipped

| | |
|---|---|
| `continuity/write_guard.py` | digest compare-and-swap against the ledger; never fails closed |
| `write_file` | records on both planes, guarded, `reason` in the schema |
| `write_config` | guarded on apply only — a dry run has nothing to protect |
| `POST /file` | `expected_sha256` from the client, ledger check when absent, **409** not 500 |
| `GET /file` | returns `sha256`, so the client can say what it is editing |
| `ConfigEditor.tsx` | round-trips the digest; recomputes after a save |
| ledger `turn_id` | via a ContextVar, set by the state machine at `begin_turn` |
| one `config_dir` | three resolvers become one |

Suites: backend **5349 passed, 14 skipped**; frontend **936 passed**, tsc
clean.

### Still open

- **2a, the host decision, is still yours** (§12 Q1). Linux target, macOS
  registry, or fixtures — it blocks 2c and 3, and no amount of implementation
  moves it.
- **2b** backup-store reconciliation, **2c** the recent-configs route, **3**
  the dock, **4** the rollback index.
- §12 Q4 — *what should a CAS refusal do?* — is now live rather than
  hypothetical. Today every path refuses and explains. For `/etc/fstab` that
  is almost certainly right; for a dotfile an "overwrite anyway" affordance
  may be wanted. It has not been built, deliberately: the safe default is
  cheap to loosen and expensive to have skipped.
- `tools/safety.py` read-only defaults (from the CLI strategy doc §17).
