# Halbert MCP — Tiered Sensitivity & Cloud Power Plan

**Date:** 2026-08-28
**Status:** Design update — replaces the "force local for all secure content" approach
**Worktree:** `feat/halbert-mcp`
**Updates:** `HALBERT-MCP-CONSOLIDATED-PLAN-2026-08-28.md` §4, §5, §9

---

## 0. What Changed

The consolidated plan's trust boundary section said "force local model
when context contains secure content." That throws away the entire reason
for having cloud models. The user plans to run DeepSeek V4 Flash as
orchestrator and DeepSeek V4 Pro or GLM-5.2 as the thinking tier —
powerful cloud models that a 7B local model can't match.

The new approach: **tiered sensitivity with user-configurable guardrails.**
Most config data is not sensitive. The sensitive parts are already
classified by the redaction layer. Route based on tier, not on a binary
"contains config content" flag.

---

## 1. The Three Tiers

### Tier 0 — Public (no restrictions)

Config data that identifies the machine's structure but carries no
secrets and no identifying values that a remote observer could exploit.

Examples:
- `/etc/hosts` structure (localhost mappings)
- `/etc/hostname` (the machine's name — the user already knows this)
- `fstab` mount points and filesystem types (not options with creds)
- Service names, unit names, which services are loaded
- Package lists (what's installed)
- Disk partition layout, filesystem types
- Network interface names, routes (not IPs — those are Tier 1)

**Routing:** Cloud models see this freely. No flag, no gate.

### Tier 1 — Operational (user-configurable)

Config data that describes how the machine is configured — specific
values that could identify the machine to an outside observer or reveal
security-relevant settings, but are not credentials.

Examples:
- SSH port number, `PermitRootLogin` setting, `PasswordAuthentication` setting
- Network addresses (routable IPs, not RFC1918)
- Firewall rules (which ports are open)
- Launchd program paths, KeepAlive settings
- TimeMachine destination, backup schedule
- Homebrew tap URLs, package sources
- Any config value that is not a credential but reveals machine specifics

**Routing:** User choice. Three settings:
- `cloud_ok` (default for most users) — cloud models can see this. The
  convenience of powerful cloud reasoning outweighs the privacy cost.
- `local_only` — route through the local secure LLM. For users who don't
  want their machine's configuration details on any cloud server.
- `redact` — strip the value, return only the structure ("Port is set but
  value redacted"). For the most paranoid setting.

### Tier 2 — Secrets (local-only by default, override with explicit consent)

Credentials, keys, tokens, passwords — anything the redaction layer's
`_is_secret_key()` already identifies.

Examples:
- API keys, tokens, bearer tokens
- Passwords, passphrases, PSKs
- Private keys (already excluded by glob, but if one slips through)
- OAuth credentials
- JWT tokens
- PEM blocks
- URL-embedded credentials (`user:pass@host`)

**Routing:** Local-only by default. The value never leaves the machine.
User can override to `cloud_ok` with an explicit acknowledgment
("I understand secrets will be sent to cloud models") — this is the
escape hatch for users who trust their cloud provider's ZDR policy and
want maximum reasoning power even over credentials.

---

## 2. How the Tiers Map to the Existing Redaction Layer

The redaction layer (`ingestion/redaction.py`) already has the
classification logic. `_is_secret_key()` is the one predicate that
determines whether a value is a credential. We extend it with a tier
assignment:

```python
def classify_sensitivity(key: str, value: Any, file_path: str) -> int:
    """Return sensitivity tier: 0 (public), 1 (operational), 2 (secret)."""
    # Tier 2: the redaction layer already knows
    if _is_secret_key(key):
        return 2

    # Tier 0: files that are inherently public
    PUBLIC_FILES = {
        "/etc/hosts", "/etc/hostname", "/etc/fstab",
        "/etc/machine-id", "/etc/os-release",
    }
    if file_path in PUBLIC_FILES:
        return 0

    # Tier 0: structural keys (booleans, paths, counts)
    if isinstance(value, bool):
        return 0
    if key.lower() in {"include", "enabled", "type", "kind", "version"}:
        return 0

    # Tier 1: everything else with a real value
    return 1
```

This is a ~30-line function that sits next to the redaction layer. It
reuses `_is_secret_key()` — no new keyword lists, no duplicate
classification.

---

## 3. The Local Secure LLM

Instead of forcing the entire conversation to a local model when any
sensitive content appears, the local LLM acts as a **secure reasoning
specialist** — it handles only the Tier 2 (and optionally Tier 1) values.

### How it works

```
User: "Is my SSH config secure?"

Cloud orchestrator (DeepSeek V4 Flash):
  1. Calls halbert.get_config_structure("/etc/ssh/sshd_config")
     → Returns Tier 0 + Tier 1 structure (directive names, booleans)
     → Tier 0/1 returned directly to cloud model

  2. Calls halbert.get_config_value("/etc/ssh/sshd_config", "Port")
     → Tier 1 (operational). User setting: cloud_ok
     → Returns 2222 directly to cloud model

  3. Calls halbert.get_config_value("/etc/ssh/sshd_config.d/100-macos.conf", "PasswordAuthentication")
     → Tier 0 (boolean). Returns "no" directly.

  4. Cloud model reasons: "Port 2222, password auth disabled, root login
     prohibited. This is a reasonably secure SSH config."

  5. Response stored in history: "Your SSH is on port 2222 with password
     auth disabled. That's a good security posture."
```

Now a turn that needs a Tier 2 value:

```
User: "What's the API key in my launchd plist for the updater service?"

Cloud orchestrator (DeepSeek V4 Flash):
  1. Calls halbert.get_config_value("com.google.keystone.daemon.plist", "APIKey")
     → Tier 2 (secret). Default routing: local-only.
     → Value is NOT returned to the cloud model.
     → Instead, the local secure LLM is invoked:

     Local LLM (Ollama, 7B+):
       Input: "The user asked about the APIKey in com.google.keystone.daemon.plist.
               The value is [REDACTED-FROM-CLOUD]. Question: what is the API key?"
       System: "You are a secure reasoning specialist. You can see sensitive
                values. Answer the user's question. If they just need to know
                the value, tell them where to find it locally rather than
                repeating the value."

       Output: "The Google Keystone updater daemon has an API key configured
                in /Library/LaunchDaemons/com.google.keystone.daemon.plist.
                You can view it with: plutil -p that file. I can see it's
                set but I'd recommend not sharing it in this conversation
                since it's going to a cloud model."

  2. Cloud model receives the local LLM's answer (not the raw value)
  3. Cloud model relays to user with its own framing
```

### Why this is different from the summarization gate I dismissed earlier

I dismissed the "LLM summarization gate" because:
1. On the same machine, the client already has filesystem access
2. It adds latency
3. The local LLM could be manipulated by prompt injection in file contents

The user's framing changes the calculus:
- The point is not to hide secrets from the local user — it's to keep
  them off cloud servers. The local LLM is the boundary between "on the
  machine" and "going to the cloud."
- Latency only applies to Tier 2 queries, which are rare. Tier 0 and
  Tier 1 (cloud_ok) go directly to the cloud model with no local LLM hop.
- Prompt injection in file contents is a risk, but the local LLM's job
  is narrow: answer a specific question about a specific value. The
  system prompt constrains it to "describe, don't transcribe."

### What the local LLM needs to be good at

Not general reasoning. Not config analysis. Just: "here's a value, here's
a question about it, give a safe answer." A 7B model is fine for this
because the task is narrow:
- "Is this password strong?" → "Yes, it's 16 characters with mixed case
  and symbols."
- "What's the API key?" → "It's set in [file]. You can view it locally
  with [command]. I'd rather not repeat it here since this conversation
  uses a cloud model."
- "Is this port safe?" → "Port 2222 is non-standard, which is good."

The local LLM doesn't need to understand multi-file drop-in precedence
or systemd dependency chains. That's the cloud model's job. The local
LLM just needs to look at a value and describe it safely.

---

## 4. User Settings (Being Config Extension)

Add a `security` section to `being.yml`:

```yaml
security:
  # Tier 1 (operational config values): user choice
  operational_tier: cloud_ok  # cloud_ok | local_only | redact

  # Tier 2 (secrets): default local-only, user can override
  secret_tier: local_only  # local_only | cloud_ok_acknowledged

  # The local model to use for secure reasoning
  secure_model: "qwen2.5:7b"  # any local model
  secure_endpoint: "http://localhost:11434"  # ollama

  # Files to always treat as Tier 0 (public)
  public_files:
    - "/etc/hosts"
    - "/etc/hostname"
    - "/etc/fstab"

  # Keys to always treat as Tier 2 (secret), even if _is_secret_key misses them
  extra_secret_keys:
    - "serial"
    - "license"
    - "activation"
```

Defaults are conservative:
- `operational_tier: cloud_ok` — most users want the power of cloud
  reasoning over their config. The values are machine-specific but not
  credentials.
- `secret_tier: local_only` — secrets stay on the machine. The escape
  hatch (`cloud_ok_acknowledged`) requires an explicit setting change,
  not just a default.

---

## 5. How This Solves the Hardest Problem

The hardest problem was: "once a secret enters conversation history, how
do you prevent it from reaching a cloud model on a subsequent turn?"

With tiered sensitivity, the answer is: **secrets never enter conversation
history in the first place.**

- Tier 0 values: enter history freely. Cloud models see them. No problem.
- Tier 1 values (cloud_ok): enter history. Cloud models see them. This is
  the user's choice — they decided the power of cloud reasoning is worth
  revealing their SSH port.
- Tier 1 values (local_only): the local LLM's answer enters history, not
  the raw value. "Your SSH port is on a non-standard port" not "port 2222."
- Tier 2 values: the local LLM's safe description enters history, not the
  value. "Your API key is set in [file]" not the actual key.

The conversation history is safe for cloud models by construction. The
tier routing happens at the tool level, before the value reaches the LLM.
There's no need for a session-level lock, two-channel history, or
provenance-based redaction of stored messages.

### What about Tier 1 values the user chose to expose?

If the user sets `operational_tier: cloud_ok` and asks "what port is
sshd on?", the value 2222 enters the conversation history. A subsequent
turn that escalates to a cloud specialist will see it.

This is **the user's explicit choice.** They decided cloud reasoning is
worth revealing their SSH port. If they later want to discuss something
sensitive, they can change the setting. Or they can set
`operational_tier: local_only` from the start and all operational values
go through the local LLM too.

The system provides the guardrails and the choice. It doesn't make the
decision for them.

---

## 6. Updated Implementation Plan

### Phase 1: Populate the config DB (unchanged from consolidated plan)

Same as before: run snapshot on real manifest, lift redaction for local
copies, set PREP_DAEMON_TOKEN.

### Phase 2: Config query layer + sensitivity classification (updated)

| Task | File | Change | Effort |
|------|------|--------|--------|
| T2.1 Config query functions | NEW `config/queries.py` | `get_config_value`, `get_config_structure`, `get_config_diff`, `get_config_dependencies` | ~100 lines |
| T2.2 Sensitivity classifier | NEW `config/sensitivity.py` | `classify_sensitivity(key, value, file_path) -> int` (0/1/2). Reuses `_is_secret_key()`. | ~30 lines |
| T2.3 Tier-aware query response | `config/queries.py` | `get_config_value` returns `{value, tier}`. Caller decides routing based on tier + user settings. | ~20 lines |
| T2.4 Being config security section | `config/being_config.py` | Add `SecurityConfig` dataclass with `operational_tier`, `secret_tier`, `secure_model`, `secure_endpoint`, `public_files`, `extra_secret_keys` | ~40 lines |
| T2.5 Settings UI | `dashboard/frontend/src/pages/Settings.tsx` | Security tab: tier pickers, secure model selector, public files list | ~80 lines |

### Phase 3: Secure reasoning specialist (new)

| Task | File | Change | Effort |
|------|------|--------|--------|
| T3.1 Secure LLM caller | NEW `config/secure_llm.py` | `reason_secure(value, question, context) -> str`. Calls local Ollama with constrained system prompt. Returns safe description. | ~60 lines |
| T3.2 Tool-level tier routing | `config/queries.py` | When `get_config_value` hits a Tier 2 value (or Tier 1 with `local_only`), call `reason_secure()` instead of returning the raw value. | ~25 lines |
| T3.3 Agent context assembler integration | `context/assembler.py` | When assembling context, use tier-aware config queries. Tier 0/1 (cloud_ok) values go into context directly. Tier 2 / Tier 1 (local_only) values go through `reason_secure()`. | ~30 lines |
| T3.4 Model routing — no change needed | — | The complexity router can escalate freely. The conversation history is safe by construction (tier routing happened at tool level). | 0 lines |

### Phase 4: MCP server (updated tool surface)

| Tool | Tier handling |
|------|---------------|
| `get_config_value` | Returns `{value, tier}`. For Tier 2, returns local LLM's safe description, not raw value. For Tier 1, checks user setting. |
| `get_config_structure` | Returns structure only (Tier 0). No values. Always cloud-safe. |
| `get_config_diff` | Returns key names and change types (added/modified/removed). No values. Always cloud-safe. |
| `get_config_dependencies` | Returns edge relationships. No values. Always cloud-safe. |

The `get_config_value` tool is the only one that can return sensitive
data, and it handles tier routing internally. The client (WarpCLI) never
needs to know about tiers — it calls the tool and gets back either a
value (Tier 0/1 cloud_ok) or a safe description (Tier 2 / Tier 1
local_only).

### Phase 5: Remote hardening (unchanged, deferred)

---

## 7. Updated Open Questions for Review

1. **Is the three-tier model the right granularity?** Too few tiers and
   we're back to the binary lock. Too many and users can't configure them.
   Three (public / operational / secret) maps cleanly to the existing
   `_is_secret_key()` predicate plus a file-level public list.

2. **Should the secure LLM's system prompt be customizable?** Some users
   might want the local LLM to be more or less verbose about sensitive
   values. Default: constrained ("describe, don't transcribe"). Override:
   user can provide their own secure-LLM system prompt in being config.

3. **Should Tier 1 default to `cloud_ok` or `local_only`?** `cloud_ok`
   maximizes power (the user's stated goal). `local_only` is more
   conservative. Proposal: `cloud_ok` as default, with a first-run
   prompt explaining the tradeoff and letting the user choose.

4. **What happens when the local secure LLM is not running?** If Ollama
   is down, Tier 2 queries can't be routed through it. Options: (a)
   refuse the query ("secure model unavailable, can't answer"), (b) fall
   back to redaction ("value is set but can't be described — start
   Ollama"), (c) fall back to cloud with a warning. Proposal: (a) for
   Tier 2, (b) for Tier 1 local_only.

5. **Should the MCP tool result include the tier?** If `get_config_value`
   returns `{"value": "safe description here", "tier": 2, "routed_through": "local"}`,
   the client (WarpCLI) can display this to the user. Transparency about
   routing is good. But it also tells the client "this was sensitive,"
   which might be metadata the user doesn't want to share. Proposal:
   include tier in the result, let the client decide whether to display it.

6. **Does this work with WarpCLI's server-mediated AI?** Yes. The MCP
   tool returns either a safe value (Tier 0/1) or a safe description
   (Tier 2). Whatever WarpCLI's AI pipeline does with the result, the
   sensitive value is already gone. Warp's ZDR + Halbert's tier routing
   = defense in depth.

---

## 8. What This Replaces in the Consolidated Plan

| Consolidated plan section | Old approach | New approach |
|---------------------------|-------------|--------------|
| §4 Trust boundary | "Force local model when secure flag is True" | Tiered routing at tool level. Cloud models run freely. Only Tier 2 values go through local LLM. |
| §5 Hardest problem | "Session-level lock or two-channel history" | Solved by construction. Tier routing at tool level means secrets never enter history. |
| §9 Open question 1 | "Is session-level secure flag acceptable UX?" | Moot. No session-level lock. User configures tier settings once. |
| §9 Open question 3 | "Raw values or references?" | Both, depending on tier. Tier 0/1: raw values. Tier 2: local LLM description (which may include references). |
| Phase 3 tasks | Secure flag, force local model, session lock, two-channel history | Sensitivity classifier, secure LLM caller, tool-level tier routing. Simpler. |

---

## 9. The Model Setup This Enables

```
User's planned configuration:
  Orchestrator: DeepSeek V4 Flash (cloud) — fast, cheap, handles conversation
  Thinking: DeepSeek V4 Pro or GLM-5.2 (cloud) — powerful, for complex reasoning
  Secure specialist: qwen2.5:7b (local Ollama) — narrow task, looks at secrets

Data flow:
  User asks question
    → DeepSeek V4 Flash orchestrates
    → Calls halbert.get_config_value for needed values
    → Tier 0/1 values come back directly → Flash reasons about them
    → Tier 2 values go through qwen2.5:7b locally → safe description comes back
    → Flash combines everything, responds to user
    → If Flash needs deeper reasoning, escalates to V4 Pro / GLM-5.2
    → V4 Pro sees only safe content (Tier 0/1 + safe descriptions)
    → Full cloud power for reasoning, zero secrets on cloud servers
```

This is the architecture the user wants: maximum cloud power, user
control over what's shared, common-sense guardrails that don't require
sacrificing capability.

---

## 10. References

- Redaction layer (has `_is_secret_key`): `halbert_core/halbert_core/ingestion/redaction.py:126`
- Being config (where security settings will live): `halbert_core/halbert_core/config/being_config.py`
- Config parser (produces canonical JSON): `halbert_core/halbert_core/config/parser.py`
- Config snapshot (stores canon DB): `halbert_core/halbert_core/config/snapshot.py`
- Model client (LOCAL_GPU_PROVIDERS): `halbert_core/halbert_core/model/client.py:76`
- Complexity router (can escalate freely now): `halbert_core/halbert_core/model/client.py:1257`
- Warp ZDR: https://docs.warp.dev/enterprise/security-and-compliance/security-overview/
- Warp local LLM (not yet supported): https://github.com/warpdotdev/warp/issues/4339
