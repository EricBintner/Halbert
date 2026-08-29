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
   the secret left the tool during a `describe_secret` operation.

Both are opt-in, which makes them policy-based safety — "we have a rule
that you have to enable it." The research below explains why
policy-based guarantees are insufficient for this boundary.

The `being_config.py` was also modified to add `CredentialValidationConfig`
and `CompromiseCheckConfig` dataclasses nested under `SecurityConfig`,
and `describe_secret` in `secure_response.py` was wired to call these
modules. This wiring must be removed.

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

### Step 1: Remove the breach from the describe_secret path

Unwire `credential_validation.py` and `compromise_detection.py` from
`describe_secret` in `secure_response.py`. The `describe_secret`
function must have no code path that sends the secret value anywhere.

Remove `CredentialValidationConfig` and `CompromiseCheckConfig` from
`SecurityConfig` in `being_config.py`. The security tier system must
not reference features that break the architectural guarantee.

### Step 2: Repurpose the modules as standalone human-run CLI tools

The credential validation and compromise detection modules are not
useless — they're tools a **human** would run to check their own
credentials. The TruffleHog research confirms this: verification
against issuing APIs is a scanner activity, not a describe activity.

Move them to standalone CLI commands:
- `halbert check-credential <key>` — validates a credential against
  the issuing service. Prints result to the terminal. The secret never
  enters an LLM context.
- `halbert check-breach <key>` — checks a credential against HIBP and
  GitHub scanning. Prints result to the terminal. The secret never
  enters an LLM context.

These are human-in-the-loop tools, not agent-facing tools. The being
config for them (if any) should be separate from the security tier
system — they are not part of Tier 2.

### Step 3: Enrich the metadata-only describe_secret

Add the fields that AWS and Snowflake return, computed locally:
- `last_changed` — file mtime from the canon DB or filesystem
- `last_accessed` — file atime (if available, or omitted like AWS)
- `rotation_status` — track if the value has changed between snapshots
  (uses the existing drift detection)
- `breach_risk` — static assessment from the format database (e.g.
  "GitHub PAT: high — full repo access if leaked")

These are all local computations. No secret leaves the tool.

### Step 4: Architectural guarantee documentation

Document in `secure_response.py` that `describe_secret` has no code
path that sends the secret value to any external service. This is an
architectural guarantee, not a policy. The function's contract is:
input is a secret value, output is metadata, the value does not appear
in any network call, log, or return field.

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
| `config/secure_response.py` | Remove credential_validation and compromise_detection calls from `describe_secret`. Add local metadata fields (last_changed, rotation_status, breach_risk). Add architectural guarantee docstring. |
| `config/being_config.py` | Remove `CredentialValidationConfig` and `CompromiseCheckConfig` from `SecurityConfig`. |
| `config/credential_validation.py` | Repurpose as standalone CLI tool. Remove `describe_secret` integration. |
| `config/compromise_detection.py` | Repurpose as standalone CLI tool. Remove `describe_secret` integration. |
| `tests/test_secure_response.py` | Update tests to verify no network calls in describe_secret path. |
| `tests/test_credential_validation.py` | Update tests for standalone CLI tool usage. |
| `tests/test_compromise_detection.py` | Update tests for standalone CLI tool usage. |
| `tests/test_being_config_security.py` | Remove tests for removed config dataclasses. |

## Files to Create

| File | Purpose |
|------|---------|
| `cli/check_credential.py` | Standalone CLI command for credential validation |
| `cli/check_breach.py` | Standalone CLI command for compromise detection |

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
