# OPENCLAW-LIFT-PACKET-02 — Policy lattice, named-gate decisions, and identifier authentication for personas

**Series:** OpenClaw lift program (master plan: `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`)
**Source research:** `.handoff/OSS-REVIEW-OPENCLAW-2026-09-07.md` §3 (Guest persona / permission-and-consent)
**OpenClaw source of record:** `/Volumes/Thunderbolt/AI/openclaw` — `src/infra/exec-approvals-core.ts`, `exec-approvals-policy.ts`, `src/channels/message-access/{decision,identifier-authentication}.ts`, `src/plugins/access-groups.ts` (in that repo), `src/pairing/*`
**Executor tier:** Phases A–B are pure functions + tests — small-model friendly. Phase C integration needs review before merge.
**Status:** READY TO DISPATCH

---

## Objective

Give Halbert's persona system three mechanical primitives that OpenClaw proved out, without rewriting the guest allowlist that already works:

1. A **two-axis policy lattice** (`security` capability × `ask` consultation) with fail-closed min/max merging, so "guest = execute-deny" is a *capability floor* rather than a persona special-case.
2. **Named-gate decision records** for inbound requests: every admission decision is an explainable object with a decisive gate and a reason code.
3. An **identifier-authentication strength ladder** for identity *claims* (not names): authorization floors are expressed in claim strength, so a free-text name can never authorize what a token can.

These are exactly the mechanism layer that `documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md` (five axes: `ceiling ∧ affordance ∧ os_grant ∧ consent ∧ ¬halted`) needs but does not implement — `capabilities/ceiling.py`, `affordance.py`, `os_grant.py`, `runtime/halt.py` do not exist in the tree. **This packet builds the lattice and decision-record machinery the permission system will consume. It must not invent a competing consent system.**

## Verified current state (do not re-derive; verified 2026-09-07)

- `feat/guest-persona` is **already merged into main**. Target the main checkout. The worktree at `.claude/worktrees/feat-guest-persona` is 3 commits behind main — do not build there.
- Guest deny today is an **allowlist**: `halbert_core/halbert_core/persona/guest_tools.py` — `GUEST_ALLOWED_TOOLS` frozenset, `GUEST_DENIED_TOOLS` (exists only so tests can force classification of every registered tool), `is_tool_allowed_for_guest()` (line 203) authoritative ("not on the allowlist means denied"), `filter_tools_for_guest()` (208). An import-time `_self_check()` enforces allow/deny disjointness and `GUEST_ALLOWED_TOOLS ∩ WRITE_PLANE_TOOLS = ∅`.
- `halbert_core/halbert_core/capabilities.py` — `CapabilityRegistry` (`has()`, `has_all()`, `has_any()`, `probe()`), module-level `has_capability()` (line 455). It answers "is it present" — it is not a consent/permission system.
- `halbert_core/halbert_core/identity.py` — `resolve_entity_name()` (line 123): flat five-step fallback (env → preferences `ai_name` → being.yml → short hostname → "Halbert"). **No name tiers — founder directive; keep it that way.** This packet adds *claim strength* for authorization, which never touches display-name resolution.
- `halbert_core/halbert_core/tools/role_gate.py` — `RoleGate` wraps `ToolSafetyFramework.classify()`; `ROLE_MAX_RISK` = admin→critical, member→high, guest→medium, restricted→low, unknown→medium; PIN confirm for HIGH. Wired in exactly two places: `dashboard/routes/agent.py:127`, `integrations/voice_auth_gate.py:229`.
- `halbert_core/halbert_core/persona/guest.py` — `GuestPersona`, `GuestHome`, `GuestSession`; `current_guest()` (333), `offer()` (377), `heartbeat()` (428), `withdraw()` (441), `handback()` (455).
- Dashboard guest routes: `halbert_core/halbert_core/dashboard/routes/guest.py` — `POST /api/guest/pull` (170) behind `Depends(require_local_admin)`; offer/heartbeat/withdraw/end/homes/become/forget; `require_owner` at `dashboard/auth.py:360`.
- The audit write-plane concept already exists: `WRITE_PLANE_TOOLS` (tools whose handlers write the hash-chained audit log) in `guest_tools.py`.

## Out-of-scope guards (from the review's anti-patterns — do NOT do these)

- Do not replace `is_tool_allowed_for_guest()` or restructure the allowlist. The lattice *feeds* it and generalizes it; the guest allowlist stays authoritative for guest until the permission doc's five-axis system lands.
- Do not add name tiers anywhere, including in the ladder. The ladder grades *claims* (how was this identity established), never *names* (what is it called).
- Do not add an implicit "no approvers configured → allow" fallback of any kind (OpenClaw's same-chat approval hole is the named anti-pattern).
- Do not build multi-instance/lease machinery. Halbert is single-instance.
- Do not touch `resolve_entity_name()`.

---

## Phase A — the lattice (pure functions, small-model friendly)

**Branch:** `feat/policy-lattice` off `main`.

### Task A1: The two axes and merge functions

**Files:**
- Create: `halbert_core/halbert_core/persona/policy.py`
- Test: `halbert_core/tests/persona/test_policy_lattice.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Lattice semantics: security merges with min (strictest wins), ask merges with max (most prompting wins)."""
import pytest
from halbert_core.halbert_core.persona.policy import (
    SecurityLevel, AskPolicy, min_security, max_ask, PolicyPair, merge_policies,
)

def test_security_order_and_min():
    assert min_security(SecurityLevel.FULL, SecurityLevel.DENY) is SecurityLevel.DENY
    assert min_security(SecurityLevel.FULL, SecurityLevel.ALLOWLIST) is SecurityLevel.ALLOWLIST
    assert min_security(SecurityLevel.DENY, SecurityLevel.DENY) is SecurityLevel.DENY

def test_ask_order_and_max():
    assert max_ask(AskPolicy.OFF, AskPolicy.ALWAYS) is AskPolicy.ALWAYS
    assert max_ask(AskPolicy.ON_MISS, AskPolicy.OFF) is AskPolicy.ON_MISS

def test_deny_cannot_be_loosened_by_any_layer():
    # the load-bearing property: guest floor + generous session override still deny
    floor = PolicyPair(security=SecurityLevel.DENY, ask=AskPolicy.OFF)
    session = PolicyPair(security=SecurityLevel.FULL, ask=AskPolicy.OFF)
    assert merge_policies([floor, session]).security is SecurityLevel.DENY

def test_yolo_requires_every_layer_to_agree():
    layers = [PolicyPair(SecurityLevel.FULL, AskPolicy.OFF)] * 3
    assert merge_policies(layers).security is SecurityLevel.FULL
    assert merge_policies(
        layers + [PolicyPair(SecurityLevel.ALLOWLIST, AskPolicy.OFF)]
    ).security is SecurityLevel.ALLOWLIST

def test_merge_empty_is_deny_and_ask():
    # fail closed: no policy expressed at all is deny + ask
    merged = merge_policies([])
    assert merged.security is SecurityLevel.DENY
    assert merged.ask is AskPolicy.ALWAYS
```

- [ ] **Step 2: Run, verify failure**

Run: `arch -arm64 .venv/bin/pytest halbert_core/tests/persona/test_policy_lattice.py -v` (see Executor gotchas)
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `policy.py`**

```python
"""Two-axis persona policy lattice.

security  = capability:   DENY < ALLOWLIST < FULL   (merged with min — strictest wins)
ask       = consultation: OFF < ON_MISS < ALWAYS   (merged with max — most prompting wins)

The load-bearing invariant, lifted from OpenClaw src/infra/exec-approvals-core.ts:
a persona defined as a security FLOOR (e.g. guest = DENY on the write plane) can
never be loosened by any other layer's generosity; "full and never ask" requires
every merged layer to agree. No layer merge may produce it otherwise.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum

class SecurityLevel(IntEnum):
    DENY = 0
    ALLOWLIST = 1
    FULL = 2

class AskPolicy(IntEnum):
    OFF = 0
    ON_MISS = 1
    ALWAYS = 2

@dataclass(frozen=True)
class PolicyPair:
    security: SecurityLevel
    ask: AskPolicy

def min_security(a: SecurityLevel, b: SecurityLevel) -> SecurityLevel:
    return SecurityLevel(min(a, b))

def max_ask(a: AskPolicy, b: AskPolicy) -> AskPolicy:
    return AskPolicy(max(a, b))

_DEFAULT_FAIL_CLOSED = PolicyPair(security=SecurityLevel.DENY, ask=AskPolicy.ALWAYS)

def merge_policies(layers) -> PolicyPair:
    """Merge policy layers left-to-right. Empty input fails closed to deny+ask."""
    if not layers:
        return _DEFAULT_FAIL_CLOSED
    security = SecurityLevel.DENY
    ask = AskPolicy.OFF
    for layer in layers:
        security = min_security(security, layer.security)
        ask = max_ask(ask, layer.ask)
    return PolicyPair(security=security, ask=ask)

# Named floors, derived from the existing guest allowlist (single source of truth stays guest_tools)
GUEST_WRITE_PLANE_FLOOR = PolicyPair(security=SecurityLevel.DENY, ask=AskPolicy.OFF)
OWNER_DEFAULT = PolicyPair(security=SecurityLevel.FULL, ask=AskPolicy.ON_MISS)
```

- [ ] **Step 4: Run, verify pass. Commit:**

```bash
git add halbert_core/halbert_core/persona/policy.py halbert_core/tests/persona/test_policy_lattice.py
git commit -m "feat(persona): two-axis policy lattice with fail-closed min/max merging"
```

### Task A2: Guest floor expressed through the lattice (parity test, not replacement)

**Files:**
- Test: `halbert_core/tests/persona/test_policy_lattice.py` (append)

- [ ] **Step 1: Write the parity test**

```python
from halbert_core.halbert_core.persona import guest_tools

def test_guest_floor_agrees_with_existing_allowlist():
    """The lattice's guest write-plane floor must agree with guest_tools' self-checked invariant:
    GUEST_ALLOWED_TOOLS ∩ WRITE_PLANE_TOOLS = ∅. Lattice is a projection of the allowlist,
    not a second authority."""
    assert not (set(guest_tools.GUEST_ALLOWED_TOOLS) & set(guest_tools.WRITE_PLANE_TOOLS))
    # and the floor the lattice would assign to those tools is DENY
    assert GUEST_WRITE_PLANE_FLOOR.security is SecurityLevel.DENY
```

- [ ] **Step 2: Run, verify pass** (this is a pin, so it should pass immediately if the invariant holds; if it fails, STOP and report — do not edit `guest_tools.py`).
- [ ] **Step 3: Commit:** `test(persona): pin lattice guest floor to the allowlist self-check invariant`

---

## Phase B — named-gate decisions and the identifier ladder (pure functions)

### Task B1: Decision records

**Files:**
- Create: `halbert_core/halbert_core/persona/admission.py`
- Test: `halbert_core/tests/persona/test_admission.py`

- [ ] **Step 1: Write the failing tests**

```python
from halbert_core.halbert_core.persona.admission import (
    Gate, GateEffect, decide_ingress, IngressDecision, ADMISSION_DISPATCH, ADMISSION_DROP,
)

def _gate(id, effect=GateEffect.ALLOW, reason="ok", **facts):
    return Gate(id=id, phase="test", effect=effect, allowed=effect is not GateEffect.BLOCK, reason_code=reason, facts=facts)

def test_first_blocker_is_decisive_and_recorded():
    gates = [_gate("identity"), _gate("persona", effect=GateEffect.BLOCK, reason="persona_execute_deny")]
    decision = decide_ingress(gates)
    assert decision.admission == ADMISSION_DROP
    assert decision.decisive_gate == "persona"
    assert decision.reason_code == "persona_execute_deny"
    assert len(decision.gate_graph) == 2  # full graph retained for the audit trail

def test_all_allow_dispatches():
    decision = decide_ingress([_gate("identity"), _gate("persona"), _gate("session")])
    assert decision.admission == ADMISSION_DISPATCH
    assert decision.decisive_gate == "session"  # last gate evaluated

def test_empty_gate_list_fails_closed():
    decision = decide_ingress([])
    assert decision.admission == ADMISSION_DROP
    assert decision.reason_code == "no_gates_evaluated"
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement `admission.py`**

```python
"""Named-gate admission decisions.

Lifted from OpenClaw src/channels/message-access/decision.ts: every inbound request
walks an ordered list of named gates; the decision is an explainable record carrying
the decisive gate and reason code plus the full gate graph, so any deny can be
answered after the fact with "dropped at gate X, reason Y" — never "no".
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

class GateEffect:
    ALLOW = "allow"
    SKIP = "skip"
    BLOCK = "block"
    OBSERVE = "observe"

ADMISSION_DISPATCH = "dispatch"
ADMISSION_DROP = "drop"
ADMISSION_SKIP = "skip"
ADMISSION_OBSERVE = "observe"

@dataclass(frozen=True)
class Gate:
    id: str
    phase: str
    effect: str
    allowed: bool
    reason_code: str
    facts: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class IngressDecision:
    admission: str
    decisive_gate: str
    reason_code: str
    gate_graph: tuple[Gate, ...]

def decide_ingress(gates) -> IngressDecision:
    """First blocking gate wins; the decision records which gate and why."""
    if not gates:
        return IngressDecision(ADMISSION_DROP, "", "no_gates_evaluated", ())
    decisive = None
    for gate in gates:
        if gate.effect == GateEffect.BLOCK:
            decisive = gate
            break
    if decisive is None:
        decisive = gates[-1]
        return IngressDecision(ADMISSION_DISPATCH, decisive.id, decisive.reason_code, tuple(gates))
    return IngressDecision(ADMISSION_DROP, decisive.id, decisive.reason_code, tuple(gates))
```

- [ ] **Step 4: Run, verify pass. Commit:** `feat(persona): named-gate ingress decision records`

### Task B2: Identifier authentication ladder

**Files:**
- Create: `halbert_core/halbert_core/persona/claims.py`
- Test: `halbert_core/tests/persona/test_claims.py`

- [ ] **Step 1: Write the failing tests**

```python
from halbert_core.halbert_core.persona.claims import (
    ClaimStrength, meets_floor, weakest_claim, IdentifierClaim,
)

def test_strength_order():
    assert ClaimStrength.MUTABLE < ClaimStrength.UNVERIFIED < ClaimStrength.ASSERTED < ClaimStrength.VERIFIED

def test_floor_gating():
    assert meets_floor(ClaimStrength.VERIFIED, ClaimStrength.ASSERTED)
    assert meets_floor(ClaimStrength.ASSERTED, ClaimStrength.ASSERTED)
    assert not meets_floor(ClaimStrength.MUTABLE, ClaimStrength.ASSERTED)

def test_weakest_claim_combines_downward():
    # a session claiming both a dashboard token and a free-text name is as weak as the free text
    combined = weakest_claim([
        IdentifierClaim(kind="token", strength=ClaimStrength.ASSERTED),
        IdentifierClaim(kind="display_name", strength=ClaimStrength.MUTABLE),
    ])
    assert combined.strength is ClaimStrength.MUTABLE

def test_documented_strength_map_is_complete():
    # executor note: extend this table when a new auth surface is added; the test
    # forces every new ClaimStrength source to be classified deliberately
    from halbert_core.halbert_core.persona.claims import CLAIM_SOURCE_STRENGTHS
    for source in ("dashboard_token", "voice_speaker_verification", "free_text_name", "device_cert"):
        assert source in CLAIM_SOURCE_STRENGTHS
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement `claims.py`**

```python
"""Identifier-claim authentication strength.

Lifted from OpenClaw src/channels/message-access/identifier-authentication.ts:
identity CLAIMS carry a strength (verified > asserted > unverified > mutable);
authorization floors are expressed in required strength. Display names never
change strength — resolve_entity_name() is untouched by design (no name tiers).
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum

class ClaimStrength(IntEnum):
    MUTABLE = 0      # free-text name, anything the requester chose themselves
    UNVERIFIED = 1   # claimed but uncorroborated
    ASSERTED = 2     # issued credential the server validates (dashboard session token)
    VERIFIED = 3     # cryptographic device proof (device cert, mTLS)

@dataclass(frozen=True)
class IdentifierClaim:
    kind: str
    strength: ClaimStrength
    value_sha256: str = ""   # never store raw identifiers in the ladder

CLAIM_SOURCE_STRENGTHS: dict[str, ClaimStrength] = {
    "free_text_name": ClaimStrength.MUTABLE,
    "voice_speaker_verification": ClaimStrength.ASSERTED,
    "dashboard_token": ClaimStrength.ASSERTED,
    "device_cert": ClaimStrength.VERIFIED,
}

def meets_floor(actual: ClaimStrength, required: ClaimStrength) -> bool:
    return actual >= required

def weakest_claim(claims) -> IdentifierClaim:
    """Combined identity is only as strong as its weakest claim."""
    return min(claims, key=lambda c: c.strength)
```

- [ ] **Step 4: Run, verify pass. Commit:** `feat(persona): identifier-claim authentication strength ladder`

---

## Composition rules with the Warrant layer (from DebateHaus review feedback, R-DH-1/2/3 — 2026-09-07)

DebateHaus's reply (`REPLY-OSS-RESEARCH-PROGRAM-2026-09-07.md`, filed in this directory) reviewed this packet against their built, tested warrant module (`backend/ai-moderator/orchestrator/warrant.js`, branch `feat/moderator-warrant`). Three rules are now part of this packet's design contract:

1. **Lattice and warrant are complementary layers — never fold authority into `security`/`ask`.** The lattice answers *capability* (may this be executed) and *consultation* (must we ask first); the warrant answers *legitimacy* (by whose rule does the voice act) and carries the citation that names the rule. Folding authority into the axes would corrupt both: `security` would stop meaning capability, and the citation would have nowhere to live. Composition: **lattice gates execution; warrant gates legitimacy and names the rule.**
2. **The claims ladder and the warrant gate different questions and MUST NOT be chained.** The ladder grades identity *claims* (how strongly established); the warrant grades *mandated* actions (does the holder's mandate cover this). `ladder_strength → warrant.authorize()` would wrongly silence a mandated act when the trigger's identity is weak — which for DebateHaus is almost always (their 0/200k uid-attribution measurement). Ladder gates *directed* actions ("may this person adjust config mid-debate"); warrant gates *mandated* actions ("may the moderator act on this signal"). Any integrator documentation produced in Phase C must state this explicitly.
3. **`IngressDecision` is the second-instance shape.** DebateHaus's warrant already returns denial reason codes (`mandate:malformed`, `mandate:disabled:<type>`, `holder:maxInterventionRate:<n>`, …) in exactly the `reason_code` shape, and is adopting the full `gate_graph` record (their side, R-DH-3). Two concrete instances = a module candidate for the engine (see the universal-vs-app-specific reconciliation in the master plan). Task B1's `IngressDecision` should note the shared shape so a future engine lift has both instances to generalize from.

---

## Phase C — integration (needs review before dispatch; touches live request paths)

**Review checkpoint:** Phases A–B merge independently of C. Do not start C until A–B are merged and the master plan records the review.

### Task C1: Decision records on the guest dashboard routes

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/routes/guest.py` (offer/heartbeat/pull paths)
- Test: `halbert_core/tests/persona/test_admission_wiring.py`

- [ ] **Step 1:** Map each guest route's existing guard checks (`require_local_admin`, guest-session state, `is_tool_allowed_for_guest`) into an ordered gate list; produce an `IngressDecision` per request; on deny, return the decision's `reason_code` in the API error payload (today denials are opaque).
- [ ] **Step 2:** Tests: for each route, one allow case and one deny case asserting the reason_code string. Run the full guest persona suite for regressions: `arch -arm64 .venv/bin/pytest halbert_core/tests/persona -v`.
- [ ] **Step 3:** Commit: `feat(guest): named-gate admission decisions on guest routes with reason codes`

### Task C2: Lattice floors for the write plane in RoleGate

**Files:**
- Modify: `halbert_core/halbert_core/tools/role_gate.py`
- Test: extend `halbert_core/tests/persona/test_policy_lattice.py` or colocated role-gate tests

- [ ] **Step 1:** In `RoleGate`, compute the effective policy as `merge_policies([role_floor(role), tool_plane_policy(tool)])` where `tool_plane_policy` returns `GUEST_WRITE_PLANE_FLOOR` for tools in `WRITE_PLANE_TOOLS` and `OWNER_DEFAULT` otherwise; guest role floor = `SecurityLevel.ALLOWLIST` (the allowlist already does the actual filtering — this records the *policy view* and the ask level for the audit line).
- [ ] **Step 2:** Tests: guest + write-plane tool → security DENY regardless of session generosity (the A1 invariant, now at the integration seam); owner + write-plane tool → FULL/ON_MISS.
- [ ] **Step 3:** Commit: `feat(role-gate): lattice policy view over the write plane`

### Task C3 (deferred — record, do not build): pairing-as-onboarding

Halbert's guest onboarding is dashboard-local-admin-gated (`offer()` → accept), which is stricter than OpenClaw's channel pairing for now. Challenge-code pairing with TTL'd pending state and approve-by-hash becomes relevant only when guests can arrive over a non-local channel (e.g., the sibling-home path). Defer; noted in the master plan.

---

## Verification gates (whole packet)

- `arch -arm64 .venv/bin/pytest halbert_core/tests/persona -v` — all new tests pass, no guest regressions.
- Import-time `_self_check()` in `guest_tools.py` still passes untouched (we never edited it; if it fails, STOP).
- No changes to `identity.py`, `capabilities.py`, or `guest_tools.py` in the diff (except none expected; if the executor believes one is needed, STOP and report instead).

## Executor gotchas (verified house traps)

- Run pytest as `arch -arm64 .venv/bin/pytest` from the repo root — the venv's universal2 binary starts x86_64 otherwise and everything fails.
- The venv's editable install resolves `halbert_core` to the MAIN tree even from worktrees — use the repo's `wt_pytest.py` wrapper if executing from a worktree, or work in the main checkout.
- Commit with pathspecs (`git add <files>`), never `git add -A` — concurrent sessions sweep the index.
- pytest-from-root resolves `halbert_core` as an outer namespace package; package-level imports can fail in tests — use `halbert_core.halbert_core.…` module paths exactly as shown.
- No Co-Authored-By trailers, no generation attribution in commits (project rule).