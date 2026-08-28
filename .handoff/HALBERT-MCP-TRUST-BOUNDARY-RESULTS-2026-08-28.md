# Halbert MCP Trust Boundary — Research Results

**Date:** 2026-08-28
**Status:** Results — answers, not questions
**Worktree:** `feat/halbert-mcp`
**Supersedes:** `HALBERT-MCP-TRUST-BOUNDARY-RESEARCH-2026-08-28.md` (that doc asked questions; this one answers them)

---

## 0. What We Got Wrong in the First Doc

The first research doc framed this as a prompt-injection problem: "a
compromised MCP client exfiltrates secrets through Halbert's tool surface."
That's the wrong threat model for Halbert's primary use case.

**The actual situation:**

- The user IS the system administrator. The user and Halbert both can know
  system secrets. There is no untrusted caller on the same computer.
- The real threat is **cloud LLMs**. If Halbert sends raw config values to a
  cloud model (OpenAI, Anthropic), those values leave the machine. That's the
  leak.
- The fix is not an LLM summarization gate or tiered file access. The fix is:
  (1) let Halbert see its own unredacted config, (2) never send secure content
  to cloud models.

The first doc also proposed "can a local LLM summarize config without leaking"
as the go/no-go research question. That question is now irrelevant — we don't
need a summarization gate. We need a local-only routing rule for secure
content.

---

## 1. What the Redaction Layer Actually Does

`halbert_core/halbert_core/ingestion/redaction.py` is 1377 lines of
battle-tested credential stripping. Here's what it covers:

### Credential patterns (the `_is_secret_key` predicate)

Two tiers of keyword matching against config keys:

**Tier 1 — substring match** (fires anywhere in the key name):
`api`, `authorization`, `bearer`, `credential`, `key`, `oauth`, `passcode`,
`passcommand`, `passphrase`, `passwd`, `password`, `psk`, `secret`, `token`

**Tier 2 — last-word match** (fires only when the key's final word is one of
these): `auth`, `cred`, `mfa`, `otp`, `pass`, `pin`, `pw`, `pwd`, `seed`,
`totp`

**Exemptions** (keys that contain tier-1 substrings but are NOT secrets):
`apiversion`, `key-mgmt`, `key_mgmt`, `keyboard`, `keymap`,
`securesocketwithkey`, `shauthorizationright`

### Format-aware line pass

`redact_structured_values()` classifies every line by format:
- **plist XML**: `<key>Password</key>` → `<key>Password</key><string>[redacted]</string>`
- **YAML**: `password: hunter2` → `password: <secret>`, block scalars handled
- **ini/systemd/keyfiles**: `password=hunter2` → `password=<secret>`
- **fstab option lists**: space-separated flags parsed individually
- **NSS database lines**: exempt (values are service names, not credentials)

### Token backstop patterns

After the line pass, regex substitutions catch anything the line pass missed:
- `TOKEN_RE`: `keyword=value` or `keyword: value` for any tier-1 keyword
- `HOME_RE`: `/home/username` → `/home/<user>`
- `EMAIL_RE`: email addresses → `<email>`
- `IPV4_RE` / `IPV6_RE`: routable IPs → `<ip>` / `<ip6>` (but RFC1918
  private ranges, loopback, link-local are EXEMPT — Halbert needs its own
  LAN addressing)
- `MAC_RE`: MAC addresses → `<mac>`
- `JWT_RE`: JWT tokens → `<jwt>`
- `PEM_RE`: PEM blocks → `<pem_block>`
- `LKDC_RE`: macOS Kerberos realm identifiers → `<lkdc_realm>`
- URL credentials: `scheme://user:pass@host` → credentials stripped

### What it does NOT redact

- **Non-routable IPs** (10.x, 172.16-31.x, 192.168.x, fc00::/7, loopback,
  link-local) — these are operational data, not secrets. Halbert needs to know
  its own LAN addresses.
- **Netmasks** (255.255.255.0 etc.) — pure configuration, not identifying.
- **Bool values under secret keys** — `PasswordAuthentication yes` is a
  setting, not a credential.
- **None values under secret keys** — a key with no value has nothing to leak.
- **Key names themselves** — `password` the key name is not a credential, only
  its value is.

### Assessment

This is a thorough, well-engineered redaction layer. It's not configurable —
there's no "disable redaction" flag. `redact_text()` always runs all passes.
To get unredacted content into a SourcePrep index, we'd need to either skip
the `redact_text()` call in `register_host_project.py:165` or add a bypass
parameter.

---

## 2. What SourcePrep Already Has for Access Control

### Daemon-level auth: `PREP_DAEMON_TOKEN`

SourcePrep's server (`src/prep/server.py:223-236`) already supports bearer
token authentication:

```python
expected_token = os.environ.get("PREP_DAEMON_TOKEN")
if expected_token:
    auth_header = request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        return 403
    token = auth_header[7:]
    if not hmac.compare_digest(token, expected_token):
        return 403
```

If `PREP_DAEMON_TOKEN` is set, every request must carry it as a bearer token.
If it's not set, the daemon is open (development mode). This is
constant-time comparison (`hmac.compare_digest`) — done right.

### CORS: locked to localhost

```python
allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
allow_origins=["tauri://localhost", "https://tauri.localhost"]
```

Only localhost origins are allowed. `PREP_CORS_ALLOW_ALL=1` opens it up for
development. This means the daemon is already not reachable from other
machines by default.

### What it does NOT have

- **Per-project access control.** Any client with the daemon token can query
  any project. There's no "this token only works for project X."
- **Encryption at rest.** The index files (`knowledge_embeddings.npy`,
  `knowledge_documents.json`, `trace_*.jsonl`) are plain files on disk. Anyone
  with filesystem access can read them.
- **Project-level secrets.** The project config has no `redaction` or
  `sensitivity` field. Redaction happens at staging time (Halbert's
  `register_host_project.py`), not at the SourcePrep level.

---

## 3. What Halbert's Model Layer Already Has

### Local vs cloud provider classification

`halbert_core/halbert_core/model/client.py:76`:
```python
LOCAL_GPU_PROVIDERS = frozenset({"ollama", "llamacpp", "mlx", "lm-studio"})
```

```python
CHAT_CAPABLE_PROVIDERS = frozenset(
    {"ollama", "llamacpp", "mlx", "anthropic"} | OPENAI_COMPATIBLE_PROVIDERS
)
```

The model layer already knows which providers are local (ollama, llamacpp,
mlx, lm-studio) vs cloud (anthropic, openai, openai-compatible). The
`provider_for()` function classifies an endpoint URL into one of these.

### Locked Mode (model pinning)

`agent.py:375-376`:
> "A user who pins a local model must never discover afterwards that a cloud
> specialist answered and billed them."

The model resolution code (`_resolve_turn_model`) already has the concept of
a "pinned" model that bypasses the complexity router. If the user pins a
local model, it stays local. The infrastructure for "this content must only
go to a local model" partially exists — it's per-user-preference, not
per-content-sensitivity.

### What it does NOT have

- **No content-sensitivity routing.** There's no "if the context contains
  secrets, force local model" rule. The complexity router can escalate to a
  cloud specialist regardless of content sensitivity.
- **No "secure tier" concept.** The tiers are `guide`, `specialist`, `vision`
  — all about capability, not security.

---

## 4. The Actual Answer

### The problem is simpler than we thought

The trust boundary is not "MCP client vs Halbert." On the same computer, the
user and Halbert are the same trust principal. The boundary is:

```
LOCAL (Halbert + local LLM + SourcePrep on localhost)
    vs
CLOUD (OpenAI, Anthropic, any remote endpoint)
```

### The architecture

```
SourcePrep daemon (:8400, localhost-only, PREP_DAEMON_TOKEN)
    |
    +-- Project: "halbert" (735a592e)
    |       host/ scope = UNREDACTED config files
    |       knowledge/ scope = docs (no secrets anyway)
    |
    +-- Access: localhost-only + bearer token
        (one machine, one Halbert, one token)

Halbert
    |
    +-- Secure content path (config values, secrets):
    |       FORCED to local LLM (ollama/mlx/llamacpp)
    |       Never sent to cloud providers
    |       Enforced by model routing layer
    |
    +-- General content path (conversation, docs, reasoning):
    |       Normal tier routing (guide/specialist/vision)
    |       Cloud models OK
    |
    +-- SourcePrep queries:
            Always local (HTTP to :8400, never leaves machine)
```

### What changes

**1. Lift redaction for Halbert's own SourcePrep project**

`register_host_project.py:165` currently does:
```python
dest_file.write_text(redact_text(text), encoding="utf-8")
```

Change to: stage raw text when the project is Halbert's private host project.
The project is already localhost-only + token-gated. The staging directory is
already under `~/.local/share/halbert/sourceprep/host/` (user-owned, not
world-readable).

The exclude_globs already strip `*.key`, `*.pem`, `shadow`, `gshadow`,
`ssl/`, `letsencrypt/` — so private keys and system shadow files are still
excluded. What we'd un-redact is: config values like the sshd port, API keys
in plist files, passwords in NetworkManager configs. These are the values
Halbert needs to reason about its own state.

**2. Add a "secure content" routing rule in the model layer**

In `_resolve_turn_model()` (or earlier, in the intake pipeline), detect when
the context being sent to the LLM contains raw config values (from the
unredacted host/ scope). When it does, force the model to a local provider:

```python
if context_contains_secrets and provider not in LOCAL_GPU_PROVIDERS:
    # Fall back to guide model (which is local ollama by default)
    model, endpoint, provider = guide_model, guide_endpoint, guide_provider
    reason = "Secure content — forced to local model"
```

This is a small change. The classification is already there
(`LOCAL_GPU_PROVIDERS`). The model resolution function is already there. We
just need a flag that says "this turn has secrets, don't escalate to cloud."

**3. Set `PREP_DAEMON_TOKEN` for the Halbert project**

The daemon already supports it. We just need to actually set the env var and
have Halbert's SourcePrep client use it. This prevents any other process on
the machine from querying Halbert's unredacted index.

**4. For the Home Assistant / remote case (later): encrypt at rest**

When Halbert runs on a remote server (N150 home automation box), the
unredacted index on disk is a risk if the machine is physically stolen or
compromised. Solution: encrypt the SourcePrep data directory with a
key that's unlocked at boot (LUKS on Linux, FileVault on macOS). This is an
OS-level concern, not a SourcePrep code change. Defer to the home-automation
deployment work.

**5. For cloud model disallowance (later): policy layer**

Add a being config or models.yml flag: `allow_cloud_for_secure_content:
false`. When false, any turn that includes raw config values is forced to a
local model. When true (advanced users who accept the risk), cloud models
can see secrets. Default: false.

---

## 5. What We Do NOT Need

- **No LLM summarization gate.** The first doc proposed having a local LLM
  summarize config files before returning them to MCP clients. This is
  unnecessary — on the same machine, the client (WarpCLI, Claude Code) is
  running as the same user who already has filesystem access to these files.
  The MCP server doesn't create a new attack surface; `cat /etc/ssh/sshd_config`
  already works.

- **No tiered file classification (public/structural/sensitive).** The
  exclude_globs already handle the "never index" tier (private keys, shadow
  files). Everything else is fair game for Halbert to know about itself.

- **No per-MCP-client permissions.** The MCP server runs on localhost. If
  you're on the machine, you're trusted. Per-client permissions are for the
  multi-machine case, which is the home-automation deployment's problem.

- **No "raw" SourcePrep project alongside a "redacted" one.** One project,
  unredacted, localhost-only, token-gated. Simpler.

---

## 6. Concrete Implementation Tasks

### Task 1: Unredacted staging for Halbert's host project
- **File:** `halbert_core/halbert_core/tools/register_host_project.py`
- **Change:** Add a `redact: bool = True` parameter to `register()` and
  `_stage_one_file()`. When `redact=False`, write raw text instead of
  `redact_text(text)`.
- **Caller:** Halbert's own registration call passes `redact=False`. Any
  other use case (shared index, multi-machine) keeps `redact=True`.
- **Risk:** Low. The staging dir is user-owned. The daemon is localhost-only.
- **Effort:** ~20 lines.

### Task 2: Set PREP_DAEMON_TOKEN
- **Files:** Halbert's SourcePrep client config, daemon startup
- **Change:** Generate a token on first run, store it in Halbert's config,
  pass it as `Authorization: Bearer <token>` on all SourcePrep API calls.
- **Risk:** Low. The daemon already supports this.
- **Effort:** ~30 lines + config plumbing.

### Task 3: Secure content routing in model layer
- **File:** `halbert_core/halbert_core/dashboard/routes/agent.py`
  (`_resolve_turn_model`) or `halbert_core/halbert_core/model/client.py`
- **Change:** Add a `secure: bool` flag to the turn context. When true and
  the resolved provider is not in `LOCAL_GPU_PROVIDERS`, fall back to the
  guide model (local ollama). Log the fallback.
- **Detection:** The intake pipeline / context assembler sets `secure=True`
  when the assembled context includes chunks from the `host/` scope of the
  unredacted SourcePrep project.
- **Risk:** Medium. Need to make sure the flag propagates correctly through
  the intake → assembler → model resolution chain.
- **Effort:** ~50 lines across 2-3 files.

### Task 4: Rebuild the host SourcePrep index unredacted
- **Action:** Run `register_host_project(redact=False)` to re-stage files,
  then trigger a SourcePrep index rebuild.
- **Risk:** Low. Overwrites the currently-redacted staging dir.
- **Effort:** One command.

### Task 5 (deferred): Encryption at rest for remote deployments
- **Scope:** Home automation / multi-machine case only
- **Approach:** OS-level (LUKS / FileVault), not application code
- **Defer to:** Home automation deployment work

### Task 6 (deferred): Cloud disallowance policy
- **Scope:** Advanced configuration for users who want to be explicit
- **Change:** Add `allow_cloud_for_secure_content` to being config or
  models.yml
- **Defer until:** After Task 3 proves the routing rule works

---

## 7. Answers to the First Doc's Research Questions

| Question | Answer |
|----------|--------|
| RQ1: Can we separate structure from values? | Yes — SourcePrep gives structure, Halbert reads raw values directly. No need to separate them through different tools. |
| RQ2: Can we redact at the response boundary? | No need. Redact at the staging boundary (current behavior) for shared indexes, don't redact for Halbert's private index. |
| RQ3: Can we use OS-level isolation? | Yes, but not needed for the same-machine case. localhost + token is sufficient. Encryption at rest for the remote case. |
| RQ4: Can we use an LLM summarization gate? | Not needed. Same-machine clients already have filesystem access. The gate adds latency and complexity for no security gain. |
| RQ5: Can we classify files by sensitivity? | Already done via exclude_globs (*.key, *.pem, shadow, gshadow, ssl/). Everything else is Halbert knowing itself. |
| RQ6: What does existing redaction cover? | Cataloged in §1 above. Thorough. Covers credentials, tokens, PEM blocks, JWTs, routable IPs, emails, MAC addresses, URL creds, home paths. Does NOT redact private IPs, netmasks, bools, key names. |

---

## 8. The One Real Risk

**Cloud model escalation with secure content.** This is the only scenario
that matters:

1. Halbert assembles context that includes raw config values (sshd port, API
   keys) from the unredacted host/ scope
2. The complexity router decides this is a "hard" question and escalates to
   the specialist tier
3. The specialist tier is configured as a cloud model (e.g., Claude via
   Anthropic)
4. Raw config values are sent to the cloud

Task 3 (secure content routing) prevents this. It's the single most important
change. Everything else is infrastructure that supports it.

---

## 9. References

- Redaction layer: `halbert_core/halbert_core/ingestion/redaction.py` (1377 lines, cataloged in §1)
- Host project registrar (redaction call site): `halbert_core/halbert_core/tools/register_host_project.py:165`
- SourcePrep daemon auth: `src/prep/server.py:223-236` (PREP_DAEMON_TOKEN)
- SourcePrep CORS: `src/prep/server.py:199-218` (localhost-only)
- Model provider classification: `halbert_core/halbert_core/model/client.py:76` (LOCAL_GPU_PROVIDERS)
- Model resolution: `halbert_core/halbert_core/dashboard/routes/agent.py:363-449` (_resolve_turn_model)
- Locked Mode rationale: `agent.py:375-376`
- SourcePrep host project: ID `735a592e-a2da-499b-a614-854a5fc461f5`, path `~/.local/share/halbert/sourceprep`
- Existing exclude_globs: `*.key`, `*.pem`, `shadow`, `gshadow`, `ssl/`, `letsencrypt/`
