# Tier 2 Recalibration — Research Findings and Remediation Plan

**Date:** 2026-08-29
**Worktree:** `~/.config/superpowers/worktrees/Halbert/halbert-mcp` on branch `feat/halbert-mcp`
**Status:** Research complete. Remediation not yet started.

---

## The Problem

During the security review session, two modules were built that break
Tier 2's core architectural guarantee — that a secret value never
leaves the tool when the LLM asks about it:

1. **`config/credential_validation.py`** (commit `f075d8f6`) — sends
   the secret to the issuing service's API (GitHub, OpenAI, Stripe) to
   check if it's still active. Justified at the time as "goes to the
   legitimate service, not an LLM vendor." That is a policy-based
   distinction, not an architectural one. The secret left the tool.

2. **`config/compromise_detection.py`** (commit `ddc81a47`) — HIBP
   sends a SHA-1 hash prefix (closer to acceptable), but the GitHub
   scanning path sends the full token to the GitHub API. Same problem:
   the secret left the tool.

**Actual state (verified 2026-08-29):** These modules were built but
**never wired into `describe_secret`**. The `describe_secret` function
in `secure_response.py` only calls `identify_credential` from
`credential_formats.py` (local pattern matching — no secret leaves).
The `validate_credential` and `check_compromised` functions are not
called from anywhere in the codebase except their own tests.

However, `CredentialValidationConfig` and `CompromiseCheckConfig`
dataclasses were added to `SecurityConfig` in `being_config.py`, and
their docstrings falsely claim "When enabled, describe_secret calls..."
— this is not true. The docstrings describe a wiring that was never
implemented. The config dataclasses and their misleading docstrings
must be removed to prevent future developers from thinking the wiring
exists or should be completed.

The modules themselves (`credential_validation.py`,
`compromise_detection.py`) are orphaned — standalone code with tests
but no callers. They are not dangerous in their current state (no code
path triggers them), but they should be documented as standalone
human-run tools, not part of the Tier 2 describe path.

---

## Research Findings

The user's original request was to research how others have solved the
"describe a secret without revealing it" problem — whitepapers, CS
blogs, production systems. Five sources are directly relevant.

### 1. AWS Secrets Manager — `describe-secret`

The canonical metadata-only API. Returns: name, ARN, description, KMS
key ID, rotation enabled, rotation rules, last rotated date, last
accessed date, last changed date, tags, version stages. The encrypted
value is **structurally absent** from the response. Not redacted —
absent. The API has no code path that produces the value.

Source: https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_DescribeSecret.html

### 2. Snowflake — `DESCRIBE SECRET`

Returns: created_on, name, owner, secret_type (OAUTH2, PASSWORD,
GENERIC, SYMMETRIC_KEY, CLOUD_PROVIDER_TOKEN,
WORKLOAD_IDENTITY_FEDERATION), username, oauth token expiry times,
oauth scopes, algorithm, key_length. Their docs state plainly:
"Snowflake never returns the PASSWORD property value." The value field
does not exist in the response schema.

Source: https://docs.snowflake.com/en/sql-reference/sql/desc-secret

### 3. AgentSecrets — Zero-Knowledge Architecture

The most important finding. AgentSecrets draws a distinction between
**policy-based** and **architectural** guarantees:

> A policy-based guarantee says "we have decided not to do this, and our
> configuration enforces that decision." The system could, technically,
> log credential values or return them to callers. It does not because
> of rules applied on top of the system.
>
> An architectural guarantee means the system has no mechanism to do
> this. There is no code path that produces the outcome, no
> configuration that enables it, no edge case where it happens.

Their concrete examples of architectural guarantees:
- The proxy returns only the API response: there is no code path that
  returns the resolved credential value to the caller
- The SDK has no `get()` method: there is no method to call that would
  retrieve a value
- The audit log schema has no value field: the field does not exist, it
  is not set to null or redacted, it is simply absent

> You cannot accidentally break these guarantees by misconfiguring
> something. There is no "verbose mode" that adds a value field to the
> audit log. There is no debug flag that makes the proxy return
> resolved values. The architecture has no path for the value to travel
> anywhere it should not be.

Source: https://agentsecrets.theseventeen.co/docs/concepts/zero-knowledge

### 4. Vault Proxy Pattern (AgentSecrets, Infisical Agent Vault, Keys on the Wire)

The industry has converged on a pattern where the agent holds an opaque
handle (e.g. `$CRED{stripe_key}`) and a proxy resolves it at the
transport layer. "An agent cannot leak a credential it does not hold."
The credential value never enters the agent's process memory, context
window, or logs.

Multiple production implementations:
- AgentSecrets: https://github.com/The-17/agentsecrets
- Infisical Agent Vault: https://github.com/Infisical/agent-vault
- Keys on the Wire: https://github.com/inflightsec/agent-vault-proxy

A 2026 study scanned 3,984 agent skills and found 283 (7.1%) contained
critical credential-handling flaws that passed API keys through LLM
context in plaintext. 76 skills contained deliberate credential-theft
payloads. The conclusion: "The only structural defence is ensuring
credentials never exist in agent context."

Source: https://www.openlegion.ai/en/learn/credential-management-ai-agents

### 5. TruffleHog — Scanner Verification (Not Applicable Here)

TruffleHog classifies 800+ secret types and verifies them against
issuing APIs. But TruffleHog is a **scanner** — a tool for finding
leaked secrets in git repos and cloud storage. The verification step
(sending the secret to the issuing API to check if it's live) is
appropriate for a scanner that a human runs deliberately, not for a
deterministic responder that describes a secret to an LLM without
revealing it.

The distinction: a scanner's job is to find and verify secrets. A
deterministic responder's job is to describe a secret to an LLM without
the value leaving the tool. These are different trust boundaries.

Source: https://github.com/trufflesecurity/trufflehog

---

## What Tier 2 Should Be

Based on the research, Tier 2's job is **metadata-only description** —
the AWS `describe-secret` / Snowflake `DESCRIBE SECRET` pattern. The
secret value is architecturally absent from what goes to the LLM. What
the LLM gets instead:

| Field | Source | Sends secret? |
|-------|--------|--------------|
| credential type | format database (pattern match on shape) | no |
| length, charset, entropy | local computation | no |
| file path, key name | canon DB | no |
| rotation status | local tracking (file mtime, last changed) | no |
| last accessed | local file metadata | no |
| correlation count | local hash index | no |
| view command | local shell command for the human | no |
| breach risk assessment | format database (static, per-type) | no |

None of this requires the secret to leave the tool. The modules that
are already correct:
- `credential_formats.py` — matches the value's shape against known
  formats locally. No secret leaves.
- `dynamic_prefixes.py` — fetches pattern definitions, not secrets.
  No secret leaves.
- `secret_correlation.py` — stores only SHA-256 hashes. No secret
  leaves.

The modules that break the guarantee:
- `credential_validation.py` — sends secret to service API. Must be
  removed from the `describe_secret` path.
- `compromise_detection.py` — sends secret (or hash prefix) to
  external services. Must be removed from the `describe_secret` path.

---

## Remediation Plan

### Step 1: Remove the misleading config dataclasses

Remove `CredentialValidationConfig` and `CompromiseCheckConfig` from
`SecurityConfig` in `being_config.py`. Their docstrings claim they're
used by `describe_secret`, but they're not. The security tier system
must not reference features that break the architectural guarantee, and
the misleading docstrings must not survive to mislead future developers.

The `describe_secret` function in `secure_response.py` is already
architecturally clean — it only calls `identify_credential` (local
pattern matching). No code changes needed there for this step.

### Step 2: Document the modules as standalone human-run tools

The modules are already standalone (not called from `describe_secret`
or anywhere else in the agent path). Fix their docstrings to say what
they actually are: standalone tools a human can run to check their own
credentials, not part of the Tier 2 describe path.

Leave the `.py` files in `config/` for now. Follow-up todo: move them
to a proper CLI location (`cli/` directory with console_scripts
entries) in a future session.

### Step 3: Enrich the metadata-only describe_secret

Add two local-computed fields that AWS and Snowflake both return:
- `breach_risk` — static assessment from the credential format
  database (e.g. "GitHub PAT: high — full repo access if leaked").
  Already exists in `credential_formats.py` entries; just surface it
  through `identify_credential`'s return value.
- `last_changed` — file mtime via `os.path.getmtime()`. Simple local
  filesystem call. Tells the LLM "this secret hasn't been changed in
  2 years, recommend rotation."

Skip `rotation_status` (requires snapshot history comparison,
`last_changed` covers the same ground) and `last_accessed` (file atime
is unreliable on modern Linux and macOS).

### Step 4: Architectural guarantee test and documentation

Document in `secure_response.py` that `describe_secret` has no code
path that sends the secret value to any external service. This is an
architectural guarantee, not a policy. The function's contract is:
input is a secret value, output is metadata, the value does not appear
in any network call, log, or return field.

Write a test that mocks all network calls and asserts that
`describe_secret` never triggers any of them, regardless of config
settings. This is the AgentSecrets pattern: prove there is no code
path, not just that the code path is disabled.

---

## What NOT to Change

The following modules are correct and should not be modified:
- `credential_formats.py` — local pattern matching, no secret leaves
- `dynamic_prefixes.py` — fetches pattern definitions, not secrets
- `secret_correlation.py` — stores only hashes, no secret leaves
- `sensitivity.py` — local classification, no secret leaves
- `redaction.py` — local redaction, no secret leaves
- `queries.py` — tier routing, no secret leaves (the per-key escape
  hatch and canon staleness fix are correct)
- `mcp/server.py` — the run_scanner gating, rate limiting, SSE limits,
  and CORS hardening are all correct

---

## Files to Modify

| File | Change |
|------|--------|
| `config/being_config.py` | Remove `CredentialValidationConfig` and `CompromiseCheckConfig` dataclasses and their references in `SecurityConfig`. |
| `config/secure_response.py` | Add `breach_risk` and `last_changed` fields to `describe_secret`. Add architectural guarantee docstring. |
| `config/credential_formats.py` | Surface `breach_risk` in `identify_credential` return value. |
| `config/credential_validation.py` | Fix docstring — standalone human-run tool, not called from describe_secret. |
| `config/compromise_detection.py` | Fix docstring — standalone human-run tool, not called from describe_secret. |
| `tests/test_secure_response.py` | Add architectural guarantee test (no network calls). Add tests for breach_risk and last_changed fields. |
| `tests/test_being_config_security.py` | Verify no tests reference removed dataclasses (none do currently). |

## Files NOT to Create

The original plan called for `cli/check_credential.py` and
`cli/check_breach.py`. Deferred — the modules stay in `config/` for now
with corrected docstrings. Follow-up todo added to MASTER-TODO.md.

---

## Test Verification

After remediation, verify the architectural guarantee with a test that
mocks all network calls and asserts that `describe_secret` never
triggers any of them, regardless of config settings. This is the
AgentSecrets pattern: prove there is no code path, not just that the
code path is disabled.

```python
def test_describe_secret_makes_no_network_calls():
    """Architectural guarantee: describe_secret never sends the secret
    to any external service, regardless of config."""
    with patch("urllib.request.urlopen") as mock_open:
        result = describe_secret("password", "hunter2", "/etc/app.conf")
        assert mock_open.call_count == 0
    assert result["redacted"] is True
    assert "hunter2" not in str(result)
```

---

## References

- AgentSecrets zero-knowledge: https://agentsecrets.theseventeen.co/docs/concepts/zero-knowledge
- AgentSecrets architecture: https://github.com/The-17/agentsecrets/blob/main/docs/ARCHITECTURE.md
- AWS describe-secret: https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_DescribeSecret.html
- Snowflake DESCRIBE SECRET: https://docs.snowflake.com/en/sql-reference/sql/desc-secret
- Infisical Agent Vault: https://github.com/Infisical/agent-vault
- Keys on the Wire: https://github.com/inflightsec/agent-vault-proxy
- OpenLegion vault-proxy: https://www.openlegion.ai/en/learn/credential-management-ai-agents
- TruffleHog: https://github.com/trufflesecurity/trufflehog
- TruffleHog false positive handling: https://deepwiki.com/trufflesecurity/trufflehog/4.4-false-positive-handling
