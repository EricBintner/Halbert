# Halbert MCP — The Most Challenging Question

**Date:** 2026-08-28
**Status:** Open problem — the one that decides whether the trust boundary works
**Worktree:** `feat/halbert-mcp`
**Prerequisite docs:**
- `HALBERT-MCP-DESIGN-RESEARCH-2026-08-28.md` (architecture)
- `HALBERT-MCP-TRUST-BOUNDARY-RESULTS-2026-08-28.md` (trust boundary answers)

---

## The Question

**Once a secret enters the conversation, how do you prevent it from reaching a cloud model on a subsequent turn — without permanently locking the conversation to local models, and without redacting the conversation history (which is lossy and fragile)?**

---

## Why This Is The Hard One

The trust boundary results doc identified "cloud model escalation with secure content" as the one real risk and proposed a fix: flag turns whose context includes `host/` scope chunks, force those turns to a local model. That fix works for **turn 1**. It does not work for **turn 2**.

### The propagation scenario

```
Turn 1:
  User: "What port is sshd listening on?"
  Intake: routes to guide (simple question)
  Context assembler: pulls host/etc/ssh/sshd_config from SourcePrep
  Secure flag: TRUE (host/ scope content present)
  Model: forced to local ollama (correct)
  Response: "sshd is on port 2222, with password auth disabled..."
  → Response is stored in conversation history

Turn 2:
  User: "Why did my SSH connection stop working after the update?"
  Intake: routes to specialist (diagnostic keywords: "why", "not working")
  Complexity score: 0.9 (diagnostic + multi-step)
  Context assembler: pulls RAG docs about SSH, plus conversation history
  Secure flag: ??? (no host/ scope chunks this turn, but history has the secret)
  Model: escalated to cloud specialist (WRONG — history contains "port 2222")
```

The secure routing rule from the results doc checks "does this turn's newly-assembled context include host/ scope chunks?" Turn 2 doesn't — it's pulling RAG docs and conversation history. But the conversation history from turn 1 contains the sshd port, auth settings, and any other config values that were in the response. The cloud specialist sees all of it.

### Why the obvious fixes don't work

**Fix A: "Check conversation history for secrets too"**

You'd need to scan every message in the conversation history for secret patterns before each turn. This is the redaction layer applied at response time — the thing the results doc said we don't need. And it has the same problem `redact_text()` has: it's pattern-based. A config value like "port 2222" is not a recognizable secret pattern. It's just a number. You can't know it's sensitive without knowing it came from a config file.

You could tag messages: "this assistant response contains content derived from host/ scope." But then you need to track provenance through the LLM's response — which parts of the response came from which source. The LLM doesn't tell you that. It synthesizes.

**Fix B: "Once any turn touches secure content, lock the whole conversation to local models"**

This works but it's terrible UX. One "what's my sshd config?" question permanently locks the entire conversation to the local model, even for turn 20 where the user is asking about a completely unrelated topic. If the local model is a 7B or 4B (as the user mentioned), the conversation degrades to the capability of that model for everything that follows.

You could unlock after N turns of no secure content, but the secret is still in the history window. `build_conversation_window` in `state_machine.py:822` keeps up to 12 history rows (`HISTORY_ROWS`). A secret from turn 1 could persist in the window for 12 turns.

**Fix C: "Redact secrets from history before sending to cloud"**

Run `redact_text()` on conversation history before sending to a cloud model. This is lossy: "sshd is on port 2222" becomes "sshd is on port <ip>" (2222 matches IPV4_RE... no, 2222 is a single number, not a dotted quad). Actually it wouldn't be redacted at all because `redact_text()` looks for `key=value` patterns, not prose. A sentence like "your sshd port is 2222" has no `key=value` structure. The redaction layer is designed for config files, not conversation.

You'd need a different redactor for conversation — one that understands which parts of a sentence are secret. That's an NLP problem, not a regex problem. And it's the LLM summarization gate the results doc dismissed, just applied at a different point.

**Fix D: "Don't store secrets in conversation history at all"**

When the assistant responds with content derived from secure sources, redact the response before storing it in the thread. The user sees the full response in the UI, but the stored version has secrets replaced with references: "sshd is on port [host:etc/ssh/sshd_config:Port]".

This is clean but requires the LLM to emit references instead of values, or a post-processing step that identifies which parts of the response came from which source. The provenance tracking from Phase 8 (`proactive/provenance.py`) is close to this — it already extracts `path:line` citations from responses. But it's for display, not for redaction.

**Fix E: "Separate secure conversations from general conversations"**

When a user asks about config, spin up (or switch to) a "secure session" that is always local-only. General questions go to the normal session. The secure session never touches cloud models. The general session never sees config values.

This is architecturally clean but breaks the conversational flow. The user's turn 2 ("why did SSH stop working?") is a follow-up to turn 1, but it's also a diagnostic question that the specialist tier handles better. Forcing it into the secure session means it gets the local model. Forcing it into the general session means the cloud model sees the history.

---

## What Makes This Genuinely Hard

### 1. Secrets are context-dependent, not pattern-matchable

"2222" is not a secret. "Port 2222" is not a secret. "Your sshd is on port 2222" IS a secret — but only because we know it came from `/etc/ssh/sshd_config`. The sensitivity is a property of the **source**, not the **content**. Once the LLM synthesizes a response, the source information is lost.

### 2. Conversation history is a single blob

The model API takes a flat `messages[]` array. You can't send "these messages are OK for cloud, but redact these other ones." It's all or nothing. If any message in the array contains a secret, the whole array is sensitive.

### 3. The complexity router only sees the prompt

`_score_query_complexity()` in `model/client.py:1257` scores the **current prompt** — a 50-word string. It does not see the conversation history. The escalation decision is made before the full message array is assembled. So even if you could detect secrets in history, the routing decision has already been made.

### 4. The history window is large

`HISTORY_ROWS = 12` and the token budget for conversation history is dynamically sized. A secret from turn 1 can stay in the window for a long time. There's no mechanism to evict a specific message from the window — it's a sliding window by token budget, not by content sensitivity.

### 5. The local model might not be good enough

If the user has a 4B or 7B local model, forcing all secure-content-adjacent turns to that model means Halbert gives worse answers about its own config than about random topics. The being knows itself less well than it knows the outside world. That's backwards.

---

## The Design Space (What We Actually Need to Decide)

### Option 1: Session-level secure flag (simple, bad UX)

Track a boolean on the thread: `touched_secure_content`. Once true, all subsequent turns in that thread use local models. Never reset.

- **Pro:** Dead simple. One boolean. No content scanning.
- **Con:** One config question poisons the entire thread. User has to start a new conversation to get cloud model capability back.
- **When it's acceptable:** If the local model is good enough (13B+), this is fine. If it's a 4B, it's not.

### Option 2: Per-turn provenance tracking (complex, correct)

When the context assembler pulls from `host/` scope, it tags those chunks with a `secure: true` flag. The LLM response is post-processed: any content that can be traced back to a secure chunk is replaced with a reference (`[host:etc/ssh/sshd_config:Port]`) before being stored in conversation history. The user sees the full response; the stored version is safe to send to any model.

- **Pro:** Secrets never persist in conversation history. Cloud models can be used freely. The reference is useful to the model ("I can see you previously discussed sshd port, which is at [host:...]"). 
- **Con:** Requires provenance tracking through the LLM's synthesis. The LLM might paraphrase, combine multiple sources, or invent content. You can't reliably map "port 2222" in the response back to the specific chunk it came from. This is the same problem search engines have with citation attribution — hard, not solved.
- **Partial implementation:** The Phase 8 provenance system (`proactive/provenance.py`) already extracts `path:line` patterns from responses. It could be extended to redact those specific values before storage. But it's best-effort — if the LLM says "your SSH port" without citing the file, the value isn't tagged.

### Option 3: Two-channel history (clean, requires infrastructure)

Store two versions of each assistant response:
- **Full version:** what the user sees (includes secrets). Stored locally, never sent to cloud.
- **Safe version:** secrets replaced with references. This is what goes into the `messages[]` array for cloud models.

The safe version is generated by running the response through a redactor that knows which source chunks were used. The full version is what the UI displays.

- **Pro:** Cloud models never see secrets. Local models can see the full version. The user experience is seamless.
- **Con:** Requires a redactor that knows what to redact. Same provenance problem as Option 2. Also doubles storage. And the safe version might lose context the cloud model needs ("your SSH port is [redacted]" is less useful than "your SSH port is 2222").
- **Key insight:** The safe version doesn't need to be perfect. It needs to be **useful enough** for the cloud model to reason, while not containing the actual secret. "Your SSH port is [ref:host:etc/ssh/sshd_config:Port]" tells the cloud model "there is a port, it's in this file" without revealing the value.

### Option 4: Secure channel separation (architectural, breaks flow)

Two conversation channels:
- **Secure channel:** always local-only. Config questions route here. History is isolated.
- **General channel:** normal routing. No config values ever enter this channel's history.

When the user asks a config question, it goes to the secure channel. When they ask a general question, it goes to the general channel. Cross-references are by citation, not by shared history.

- **Pro:** Clean separation. No contamination possible. Each channel uses the appropriate model.
- **Con:** Breaks conversational continuity. The user's "why did SSH stop working?" is both a config question (needs to know the port) and a diagnostic question (benefits from the specialist tier). Which channel does it go to? If both, the cloud model still needs the port value.
- **This is essentially what the dashboard's "Analyze" button does today** — it runs a separate LLM call scoped to a specific knowledgebase, not the main conversation. The user's previous session explored redesigning this to use the agent infrastructure. This option would formalize that separation.

### Option 5: Accept the leak for local-only deployments, solve it for remote (pragmatic)

For the same-machine case (the 90% focus), the user is the admin. If the local model is the guide model (ollama), there's no cloud escalation anyway — the complexity router can only escalate if a specialist is configured, and if the specialist is also local, there's no leak. The problem only exists when:
1. A cloud specialist is configured, AND
2. The user asks a config question, AND
3. A follow-up question triggers escalation

If we just... don't configure a cloud specialist, the problem doesn't exist. The secure routing rule from the results doc handles the direct case (turn 1). Turn 2+ is only a problem if there's a cloud specialist to escalate to.

- **Pro:** No code needed. The problem is a configuration concern, not a code concern.
- **Con:** Doesn't scale. If the user wants cloud specialist capability for non-secure topics (which is the whole point of having a specialist tier), they need to either accept the risk or get the UX penalty of Option 1.
- **When it works:** Default config: specialist tier = local model or unset. Cloud models are opt-in for specific use cases, not the default escalation target.

---

## The Question We Need to Answer

**Which option do we build?**

The answer depends on one thing we don't know yet:

**What local model will the user actually run, and is it good enough for config analysis?**

- If the local model is a 13B+ (qwen2.5:14b, llama3.1:8b, etc.), Option 1 (session-level lock) is fine. The UX penalty of locking to local is small because the local model is capable.
- If the local model is a 4B-7B, we need Option 2 or 3 (provenance-based redaction of history). The local model can't handle complex config analysis alone, so we need cloud models in the loop, which means we need to keep secrets out of the history they see.
- If the user doesn't configure a cloud specialist at all, Option 5 (pragmatic) works and we build nothing.

This is a research question about model capability, not architecture. We need to test: can a 7B local model correctly analyze a multi-file sshd configuration with drop-in overrides and give accurate advice? If yes, Option 1. If no, Option 3.

---

## Proposed Research Task

### The test

1. Take a real config scenario from this machine: `sshd_config` + `sshd_config.d/100-macos.conf` (the drop-in that overrides it)
2. Ask three models the same question: "What port is sshd on, and is password auth enabled? Which file takes precedence?"
   - 4B model (e.g., qwen2.5:3b or llama3.2:3b)
   - 7B model (e.g., qwen2.5:7b or llama3.1:8b)
   - 13B+ model (e.g., qwen2.5:14b) or cloud model (for baseline)
3. Score: does the model correctly identify the drop-in override? Does it get the port right? Does it understand Include directive precedence?

### The decision

- If 7B gets it right → Option 1 (session-level lock). Ship it. Simple.
- If 7B gets it wrong but 13B gets it right → Option 3 (two-channel history). The user needs cloud capability for secure topics, so we need to keep secrets out of cloud-visible history.
- If even 13B struggles → the problem is harder than model routing; we need structured config analysis, not LLM reasoning over raw config text.

### What to build during the test

A minimal prototype:
```python
# secure_session.py
def should_force_local(thread_history, current_context):
    """Returns True if any message in history or context contains secure content."""
    # Option 1: check if thread ever touched host/ scope
    if thread_history.any(touched_secure=True):
        return True
    # Check current turn
    if current_context.has_host_scope():
        return True
    return False
```

This is Option 1. Build it first. If the model capability test shows 7B is good enough, we're done. If not, we upgrade to Option 3 on top of it.

---

## What This Is NOT

- Not a reason to block the MCP server. The MCP server (Phase 1, read-only tools) doesn't expose config file reads. The secure routing problem only matters when the agent is reasoning over config content, which is the reactive slice / agent path — not the MCP tool surface.
- Not a problem for SourcePrep queries. SourcePrep runs on localhost. `prep_search` results never leave the machine. The problem is only about which LLM sees the assembled context that includes those results.
- Not solved by encryption. Encrypting the SourcePrep index at rest protects against disk theft, not against a cloud LLM seeing values in a prompt.

---

## References

- Complexity router (scores prompt only): `halbert_core/halbert_core/model/client.py:1257` (`_score_query_complexity`)
- Model resolution (escalation decision): `halbert_core/halbert_core/dashboard/routes/agent.py:466-477`
- Conversation history window: `halbert_core/halbert_core/agents/state_machine.py:728-822` (HISTORY_ROWS=12, token-budgeted window)
- Context assembler (pulls from multiple sources): `halbert_core/halbert_core/context/assembler.py:129`
- Provenance system (Phase 8, path:line extraction): `halbert_core/halbert_core/proactive/provenance.py`
- Redaction layer (pattern-based, config files not prose): `halbert_core/halbert_core/ingestion/redaction.py:1221` (`redact_text`)
- LOCAL_GPU_PROVIDERS: `halbert_core/halbert_core/model/client.py:76`
- Analyze button (existing secure-channel precedent): `dashboard/routes/discovery.py:analyze_discoveries`
