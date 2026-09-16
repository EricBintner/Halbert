# Research: how three agent hosts decide what may run — and what Halbert should take

> **Document:** `.handoff/RESEARCH-PERMISSION-MODELS-2026-09-16.md`
> **Status:** Research complete; recommendations ranked; four founder questions at the end.
> **Date:** 2026-09-16
> **Asked by:** the founder, on ruling B for the terminal ask: *"this is a whole scope of research and UI planning … we should really be looking deeply into how cdesktop, open-claude-code and warp handle permissions, then decide how this is different for us and find the best options."*
> **Read:** `/Volumes/Thunderbolt/AI/OSS/{cdesktop,open-claude-code,warp}` at their 2026-08-24 checkouts. Every claim below cites a file and, where it matters, a line. Nothing was run; this is a reading of source.
> **Licensing, stated first:** Warp is **AGPL v3** for everything except its two `warpui*` crates (README §Licensing). cdesktop and open-claude-code carry their own licences. Halbert is GPL-3.0-or-later. **Design is free to study; code is not free to lift.** Nothing in this document proposes copying code, and the licence policy engine (`corpus/license_policy.py`) would need a founder ruling before any AGPL file entered the tree.

---

## 1. The question, and the four axes

Ruling B made the terminal ask before running a HIGH-verdict command, the same as the agent path. That closed a gap. It also exposed that Halbert has no *design* for the ask — the dialog has two buttons, nothing persists, and the person cannot see or change what the machine will and won't do on its own. The founder's instinct was right that this is a permissions-and-UI problem, not a classifier problem.

The three projects were read on four axes, because those are the four things a permission system has to decide:

| Axis | The question |
|---|---|
| **A. Who decides** | When a command arrives, what judges it — a deterministic rule, the model's own claim, or a person? |
| **B. Unit of trust** | What is a rule *about* — a tool name, a command regex, the command's content, a capability? |
| **C. Persistence** | When a person says "yes", where does that go, and does it ever stop asking? |
| **D. The ask itself** | How is the person asked, what can they answer, and what happens if they don't? |

## 2. open-claude-code — Claude Code, reconstructed

`v2/src/permissions/{checker,prompt,injection-check}.mjs`. A reverse-engineered Claude Code; 70 `.mjs` files.

- **A.** Tool *name*. `requiresPermission(toolName)` is a `SAFE_TOOLS` set (`Read, Glob, Grep, LS, ToolSearch, AskUser, CronList, TodoWrite`); everything else asks in `default` mode. Bash gets an injection check (`checkInjection`) and file ops get `validatePath`. **There is no judgment of what a Bash command *does*** — `ls` and `rm -rf ~` are the same tool.
- **B.** Six modes × tool name: `default / acceptEdits / bypassPermissions / plan / dontAsk / auto`. `plan` admits only Read/Glob/Grep. `acceptEdits` admits file ops, asks for Bash/Agent.
- **C.** Not reconstructed here. Real Claude Code persists `allow`/`deny` rules in `settings.json` (`Bash(git status:*)` shapes) — the founder lives in that model daily and knows it better than this repo does.
- **D.** A readline `[y/N]`. And one thing worth naming: in `default` mode **"without a readline interface, allow"** (`checker.mjs:46`) — headless means yes. Halbert must never inherit that instinct; a surface with no one to ask is a surface that refuses.

**What it teaches:** the *mode vocabulary*, nothing more. Its permission layer is the thinnest of the three.

## 3. cdesktop — a host that owns the conversation, not the verdict

`crates/services/src/services/approvals.rs`, `approvals/executor_approvals.rs`, `crates/executors/src/executors/claude.rs`, `claude/client.rs`, `packages/web-core/.../PendingApprovalEntry.tsx`.

cdesktop runs *other* agents — Claude Code, Codex, OpenCode, ACP — and normalises their permission requests into one approvals layer. It **owns no classifier at all.**

- **A.** The *agent* decides what needs asking. For Claude Code, cdesktop launches it with `--permission-prompt-tool=stdio` and a `PreToolUse` hook (`claude.rs:171,237`); the hook's `ask` decision routes to `can_use_tool`, which becomes a cdesktop approval. "Auto-approve" is literally a hook that answers `permissionDecision: "allow"` to everything (`client.rs:359`).
- **B.** `PermissionPolicy {Supervised, AcceptEdits, Plan, Auto, Bypass}` (`model_selector.rs:53`) — Claude Code's modes, renamed. `Unknown` catch-all absent; it passes `--dangerously-skip-permissions` straight through.
- **C.** **None in cdesktop.** No "always allow", no store. Whatever persists is the agent's own (Claude Code's `settings.json`).
- **D.** This is what cdesktop is *for*, and it is the best of the three at it. `PendingApproval {tool_name, is_question, created_at, timeout_at, response_tx: oneshot}` (`approvals.rs:21`). **Approvals time out.** `is_question` separates a permission ask from an `AskUserQuestion` so the UI renders each correctly and `validate_approval_response` refuses a mismatched answer. The resolved outcome is **broadcast** (`patches_tx`) so every attached client sees the same pending/resolved state. The UI offers **Approve** and **Deny with a reason**, and the reason goes back to the model with a fixed prefix mirroring Claude Code's CLI (`client.rs:28`).

**What it teaches:** the ask is a first-class object with a lifetime, a kind, a reason, and an audience. Halbert's `ConfirmationRequest {actionId, tool, description, riskLevel}` and `{action_id, confirmed: bool}` round-trip has none of those.

## 4. Warp — the profile, the dial, and a judge that is the model

`app/src/ai/blocklist/permissions.rs`, `app/src/ai/execution_profiles/config.rs`, `crates/cloud_object_models/src/ai_execution_profile.rs`, `settings_view/agent_profiles_page.rs`. 3,994 Rust files; permissions are concentrated and coherent.

- **B first, because it is the centre.** `AIExecutionProfile` (`ai_execution_profile.rs:354`) is a **named, switchable, cloud-synced, team-shareable object**: per-capability `ActionPermission` for `apply_code_diffs`, `read_files`, `execute_commands`, `mcp_permissions`; own enums for `write_to_pty`, `ask_user_question`, `run_agents`, `computer_use`; `command_allowlist` and `command_denylist`; `directory_allowlist`; MCP allow/deny by UUID; models per role. There is a default profile; "always allow this" writes to it.
- **The dial.** `ActionPermission {AgentDecides, AlwaysAllow, AlwaysAsk}` — a **three-way, per capability**, with user-facing prose for each ("The Agent chooses the safest path…", "Give the Agent full autonomy…", "Require explicit approval…"). And `#[serde(other)] Unknown → AlwaysAsk`: an unrecognised variant from a newer client **fails closed**. Small, correct, worth copying as an idea.
- **A. Who decides — the decision order** (`can_autoexecute_command`, `permissions.rs:899–1016`), which is the most instructive thing in all three codebases:
  1. Normalise line continuations; **decompose into sub-commands** and note redirection; strip leading `VAR=` per sub-command.
  2. **Denylist first, always.** Two denylists with different authority: the **organisation's cannot be bypassed**; the **user's** can be bypassed by auto-approve, but only when the process is not sandboxed.
  3. Auto-approve → allow.
  4. By the capability's dial: `AgentDecides` → (feature-flagged) the **model's own `is_risky == false` claim allows** → redirection denies → **allowlist, where *every* sub-command must match** → `is_read_only` allows → else ask. `AlwaysAllow` → allow. `AlwaysAsk` → allowlist only.
- **And the finding that matters most:** **`is_read_only` is not computed by Warp.** It arrives as `Option<bool>` from the model's tool call (`shell_command.rs:134`, `block.rs:2775`) and is consumed `unwrap_or(false)` — fail-closed on absence, but **the read-only judgment is the model's self-report.** The `classify_command` in `warp_completer` is the autocomplete parser, not a safety judge. Warp's deterministic layer is the two regex lists; past them, the machine trusts the agent about the agent.
- **Rule shape.** Allow/deny entries are **anchored regexes only** (`AgentModeCommandExecutionPredicateType::AnchoredRegex`, `^…$` added unconditionally), matched against each decomposed sub-command. The user types a regex. Expressive; a footgun for anyone who is not a regex author.
- **C.** "Always allow" is a button → `add_command_to_autoexecution_allowlist` → the default profile's `command_allowlist` (`permissions.rs:1023`). Directory reads persist to `directory_allowlist`. **Speedbumps**: a one-time interstitial the first time a person enables auto-executing read-only commands (`set_should_autoexecute_readonly_commands`, `permissions.rs:1080`) — consent with an explanation, once.
- **D.** User vocabulary, verbatim from the settings UI: "Agent decides / Always allow / Always ask", "Command allowlist", "Command denylist", "Directory allowlist", "MCP allowlist/denylist".
- **Convergent with Halbert:** `check_protected_write_paths` refuses to auto-write any MCP config file "to prevent … injecting arbitrary context into the agent" (`permissions.rs:1233`). Halbert reached the same rule independently (A17-G3, `SENSITIVE_PATHS`).
- **False lead, closed:** `command-signatures-v2/` is a two-file example plugin for the *completions* API (`registerCommandSignature` for a toy `jack` command). It is not a permissions database.

## 5. Halbert today, on the same axes

- **A.** A **deterministic content classifier**, model-independent: `ToolSafetyFramework` — `READ_ONLY_COMMANDS` (three value shapes), `EFFECTFUL_ARGS`, `SUBVERBS`, `_remainder_vouched`, `SENSITIVE_PATHS` (resolved), the credential-read gate — then `RoleGate` (tightens by *speaker*: owner / guest / restricted), then the executor asks on HIGH, and since ruling B the terminal routes ask on the same verdict (428, resubmit with `force`). Measured: 36 of Halbert's own 262 commands prompt.
- **B.** Command *content* and path and credential shape; `capabilities.py` as **binary presence probes**; `autonomy_level ∈ {observe, suggest, act, orchestrate}` with per-HA-domain overrides and a **phrase ceremony** to raise it; `Lease`/`Scope` per capability (SEC-5, built, not yet the choke point).
- **C.** `<config_dir>/command-allowlist.json`, keyed `(binary, first operand)` — **exists, is read in one place, is written nowhere, and has no button.** The consent ledger records grants. The autonomy dial persists in `being.yml`.
- **D.** `ConfirmationDialog.tsx`: **Confirm / Reject.** `POST /api/agent/confirm/{session}` with `{action_id, confirmed: bool}`. No reason. No timeout. No "always allow". No broadcast to other attached clients. The terminal's ask (B) is a 428 the frontend does not yet render.

### The comparison

| | open-claude-code | cdesktop | Warp | **Halbert** |
|---|---|---|---|---|
| **A. Judge** | tool name | the agent | regex lists, then **the model's claim** | **deterministic content classifier** + speaker role |
| **B. Unit** | tool × mode | agent's mode | capability × three-way dial; regex per command | command content; capability presence; autonomy level; Lease |
| **C. Persists** | (real CC: settings.json) | none | profile allowlist, **by button** | store exists, **no writer, no button** |
| **D. The ask** | `[y/N]`; headless = yes | **timeout, kind, deny-reason, broadcast** | inline approve; speedbumps | Confirm/Reject, boolean |

## 6. How Halbert is different

Two things, and they point in opposite directions.

**We hold the piece none of them has.** A read-only judgment that does not consult the model. Warp, the most mature of the three, asks the agent whether the agent's command is safe. Halbert's invariants forbid exactly that — *"never a model where a template suffices"*, *"scrub deterministically before the model"* — and this week's work made the table the judge, to the second operand and beyond. That is not a gap to close; it is the thing to keep and to make visible.

**We lack the product layer every one of them has.** No object a person can look at that says what the machine will do on its own. No dial — capabilities are on/off, autonomy is one word, the allowlist is a JSON file nobody can write. No "always allow" button, so every HIGH prompt is forever. An ask that cannot carry a reason back, cannot expire, and cannot be seen from a second client.

**And one thing that is ours alone.** None of the three models *who is speaking*. Halbert is the machine, in a house, with an owner and guests and a restricted role; `RoleGate` tightens the verdict by speaker before anyone is asked. Warp's profile is per-team; ours has to be per-person-in-the-room. Any profile object we build inherits that axis — no borrowed design has it.

## 7. Options, ranked

Recommendations, not a survey. Cheap-and-certain first.

**Now — small, each pays immediately, none needs a design ruling.**
1. **Render the 428.** Frontend: `/check-safety` pre-flight → `ConfirmationDialog` → resubmit with `force`. B is landed on the backend and invisible until this exists.
2. **"Always allow this" as a button.** One owner-only route that appends `(binary, first operand)` to `command-allowlist.json`; the dialog gains a third action. The store, its keying, and the read path already exist — this is Warp's exact affordance on Halbert's safer key shape. *Founder's yes on the nine table entries becomes moot the day this ships: they retire themselves.*
3. **Deny with a reason.** `{action_id, confirmed, reason?}`; the reason reaches the model as the tool result, cdesktop's way. Costs a text field. Buys the model the one thing a boolean cannot say.
4. **A pending ask expires.** cdesktop's `timeout_at`. A confirmation nobody answers should resolve to *denied*, log, and free the session — never hang it.

**Next — one design, one being.yml section, one settings card.**
5. **A Profile that is Halbert-shaped.** Take Warp's *shape* — a named object with a **three-way dial per capability** — and put **Halbert's judge** in the middle position. Warp's middle is "agent decides" and means the model's self-report; **ours means the classifier decides**, and the dial is *Ask / Judge / Allow*. Fold in what already exists rather than adding beside it: `capabilities.py` presence becomes the row list; `autonomy_level` becomes the profile's name or a row; `command-allowlist.json` and the `SENSITIVE_PATHS` additions become fields; `RoleGate` gives each profile a *per-speaker* column that no borrowed design has. Two denylist authorities, as Warp: the machine's own (`BLOCKED_COMMANDS`, never bypassed) and the owner's. `Unknown → Ask`, fail-closed, as Warp.
6. **Speedbumps at the right moments.** The first time the owner switches a row to *Allow*, one interstitial explaining what that row now permits — then never again. This is SEC-6's first-run consent, applied per-row; the consent ledger is where the record goes.

**Keep, do not import.**
- Speaker-role gating. The autonomy phrase ceremony. The consent ledger. These are ahead of all three.
- **Do not** adopt user-typed regex allowlists. `(binary, first operand)` is less expressive and far harder to get catastrophically wrong.
- **Do not** let any surface trust the model's own `is_read_only`. The whole point of this week is that we do not have to.
- **Do not** inherit "headless means allow." A surface with no one to ask refuses.
- **Do not lift code.** AGPL. The ideas above are all reconstructible from first principles and this document.

## 8. For the founder

1. **The dial's middle word.** Warp says "Agent decides." Ours is the classifier. *Judge*? *Halbert decides*? The word matters because the machine speaks in first person.
2. **Is the Profile one object or two?** Autonomy (`observe…orchestrate`) and permissions could be one card or a dial-within-a-profile. Warp fused them; the phrase ceremony argues for keeping autonomy its own step.
3. **Does a guest ever see the dial?** `RoleGate` already answers what a guest may *do*; whether a guest may *see* what the owner permitted is a new question.
4. **Options 1–4 now, or wait for 5?** They are independent of it and each removes a real friction today. The recommendation is now.

## 9. Verification

Everything above is from reading these files at the checkout dates given; line numbers are as of that read.

- open-claude-code: `v2/src/permissions/checker.mjs`, `prompt.mjs`; `v2/README.md` ("Permission modes | 6").
- cdesktop: `crates/services/src/services/approvals.rs:21–70,125–180`; `approvals/executor_approvals.rs`; `crates/executors/src/executors/claude.rs:129–245`; `claude/client.rs:23–60,357–370`; `crates/executors/src/model_selector.rs:53–65`; `packages/web-core/src/shared/components/NormalizedConversation/PendingApprovalEntry.tsx:79–160`.
- Warp: `app/src/ai/blocklist/permissions.rs:899–1100,1224–1247`; `crates/cloud_object_models/src/ai_execution_profile.rs:19–54,205–260,346–391`; `app/src/ai/execution_profiles/config.rs:254–290`; `app/src/ai/blocklist/action_model/execute/shell_command.rs:134`; `app/src/ai/blocklist/block.rs:2759–2830`; `crates/warp_completer/src/parsers/mod.rs:100–135`; `README.md:54–58`; `command-signatures-v2/js/build/main.js`.
- Halbert: `tools/safety.py`; `tools/role_gate.py:271`; `tools/executor.py:491–700`; `dashboard/routes/terminal.py` (B); `config/being_config.py:38,299`; `mcp/server.py:764–840`; `consent/store.py`; `persona/permission/lease.py`; `dashboard/frontend/src/components/agent/ConfirmationDialog.tsx`; `hooks/useAgentStream.ts:88–96,1353–1378`.
