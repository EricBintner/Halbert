# OPENCLAW-LIFT-PACKET-05 — Redaction choke-point hardening: variant registration, echo guard, one pipeline

**Series:** OpenClaw lift program (master plan: `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`)
**Source research:** `.handoff/OSS-REVIEW-OPENCLAW-2026-09-07.md` §9 (MCP client boundary) and anti-pattern notes
**OpenClaw source of record:** `/Volumes/Thunderbolt/AI/openclaw` — `src/logging/secret-redaction-registry.ts`, `src/gateway/boot-echo-guard.ts`, `src/secrets/egress-proxy/stream-substitution.ts`
**Executor tier:** Phases A and C are pure/portable — small-model friendly. Phase B involves locating the outbound-delivery seam — medium scope, verify-first.
**Status:** READY TO DISPATCH (after one pre-flight check below)

---

## Objective

Three reinforcements to Halbert's existing deterministic redaction choke point, all lifted from OpenClaw's belt-and-suspenders secret design:

1. **Secret variant registration** — register the exact secret value *plus its URL-encoded and JSON-escaped forms* when a secret becomes known, so redaction catches the leak forms a plain-value registry misses (the leak class Halbert's own audit would flag).
2. **Echo guard** — a second, independent layer over the choke point: detect when outbound agent delivery reproduces long chunks of recently egress-acknowledged sensitive material, catching paraphrase-around-the-marker leaks deterministically.
3. **One policy pipeline** — internal tool results and MCP tool results must flow through the *same* redaction core; extract it so there is exactly one implementation and no future drift.

## Pre-flight check (executor must do this first)

The security branch `worktree-sec-1-one-door` (worktree `.claude/worktrees/sec-1-one-door`, tip `71c7b88b`, **6 commits unmerged**) touches `dashboard/auth.py`, `streaming/pty.py`, `tools/safety.py`, `system_info.py`, deploy units. **Before starting, verify it does not touch `mcp/response.py`, `ingestion/redaction.py`, or `config/security_constants.py`:**

```bash
git diff main..worktree-sec-1-one-door --stat -- halbert_core/halbert_core/mcp/response.py halbert_core/halbert_core/ingestion/redaction.py halbert_core/halbert_core/config/security_constants.py
```

Expected: empty. If not empty, coordinate with the sec branch owner before proceeding (merge conflict risk). Also confirm with the master plan whether the sec branch has merged by the time you start — if it has, branch from that merge.

## Verified current state (do not re-derive; verified 2026-09-07)

- **Response choke point:** `halbert_core/halbert_core/mcp/response.py` — `mcp_response()` wraps every MCP tool result (`server.py:35` imports it; every handler returns through it). `_redact_value()` (110) recurses strings/lists/dicts; `_redact_dict()` (126) applies: config-value-pair shape `{"key": <secret-name>, "value": ...}` → value → `"<secret>"`, and secret dict keys (skipping `_MCP_FIELD_NAMES` metadata). Deliberate escape: a dict carrying `EGRESS_ACK_FIELD` (from `config/security_constants.py`, set only by `config/queries.get_config_value` after tier + acknowledgment + TTL) keeps its raw `value`.
- **Text redaction:** `halbert_core/halbert_core/ingestion/redaction.py` — `redact_text()`, `_is_secret_key()`. This is where the variant registry belongs.
- **Tier routing:** `classify_sensitivity()` (`config/sensitivity.py:87`); `get_config_value(key, ..., operational_tier="cloud_ok", secret_tier="local_only", secret_tier_expiry)` in `config/queries.py` with TTL re-check (~275-281). Tier 2 = deterministic template via `config/secure_response.py` (`describe_secret`) — never an LLM (founder-verified posture: every local model leaked in measurement; qwen3:4b 4/4).
- **MCP surface:** `mcp/server.py` — `TOOL_HANDLERS` registry (847), dispatch (~1247). `mcp/camera_gate.py` (`gate_response()` strips image data) is **wired to nothing** — no frigate/vision tool is registered; `mcp/__init__.py` labels this R2-OBS-1 as a landmine for whoever adds one.
- **MCP client side:** `federation/fleet_proxy.py` — `FleetProxy` (63), JSON-RPC 2.0 to satellites.
- **Known held-back items on the sec branch that neighbor this packet** (do not duplicate): command classifier ruling, macOS seatbelt profile, path primitive (`ResolvedPath`). Open P0 rows SEC-2, SEC-3, SEC-4, SEC-5+8, SEC-6 are separate work.

## Out-of-scope guards

- Do NOT change tier routing, `secure_response.py`, or the EGRESS_ACK_FIELD escape semantics — they embody ratified founder decisions (memory: Tier 2 = deterministic template, never an LLM).
- Do NOT build OpenClaw's sentinel-sealing/egress-proxy — that is a larger architecture; this packet only takes the registry-variants and echo-detection ideas.
- Do NOT touch the sec branch's held-back items or its open P0 rows.
- No LLM anywhere in this packet — all layers deterministic (memory: LLM summarization gate is NO-GO).

---

## Phase A — secret variant registration (pure, small-model friendly)

**Branch:** `feat/redaction-variants` off `main`.

### Task A1: The variant registry

**Files:**
- Create: `halbert_core/halbert_core/ingestion/redaction_registry.py`
- Test: `halbert_core/tests/ingestion/test_redaction_registry.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Lifted from OpenClaw src/logging/secret-redaction-registry.ts: when a secret value
becomes known, register its exact value PLUS url-encoded and json-escaped forms —
those are the leak forms that evade plain-value redaction."""
import json
import urllib.parse

from halbert_core.halbert_core.ingestion.redaction_registry import (
    SecretVariantRegistry, REDACTION_PLACEHOLDER,
)

def _reg():
    return SecretVariantRegistry(max_entries=64)

def test_plain_form_is_registered():
    reg = _reg()
    reg.register("hunter2")
    assert "hunter2" in reg
    assert reg.redact_text("password is hunter2 ok") == f"password is {REDACTION_PLACEHOLDER} ok"

def test_urlencoded_form_is_caught():
    reg = _reg()
    reg.register("p@ss w/rd")
    encoded = urllib.parse.quote("p@ss w/rd")
    assert reg.redact_text(f"see {encoded} in url") == f"see {REDACTION_PLACEHOLDER} in url"

def test_json_escaped_form_is_caught():
    reg = _reg()
    secret = 'say "hi"\\now'
    escaped = json.dumps(secret)[1:-1]  # the inner escaped form as it appears when embedded in JSON text
    reg.register(secret)
    assert reg.redact_text(f"payload {escaped} end") == f"payload {REDACTION_PLACEHOLDER} end"

def test_bounded_and_fifo():
    reg = SecretVariantRegistry(max_entries=4)
    for i in range(6):
        reg.register(f"secret-{i}")
    assert "secret-0" not in reg  # oldest evicted
    assert "secret-5" in reg

def test_empty_and_short_values_ignored():
    reg = _reg()
    reg.register("")
    reg.register("ab")  # too short to redact safely — would blank out ordinary text
    assert len(reg) == 0
```

- [ ] **Step 2: Run, verify failure.** `arch -arm64 .venv/bin/pytest halbert_core/tests/ingestion/test_redaction_registry.py -v`

- [ ] **Step 3: Implement `redaction_registry.py`**

```python
"""Exact-value secret redaction with encoded-variant coverage.

OpenClaw's registry (src/logging/secret-redaction-registry.ts) registers the raw
value plus its URL-encoded and JSON-escaped forms so percent-encoded egress and
serialized captures both redact. Bounded FIFO; values shorter than
MIN_SECRET_VARIANT_LEN are ignored (redacting "ab" blanks out ordinary prose).
"""
from __future__ import annotations
import json
import urllib.parse
from collections import OrderedDict

REDACTION_PLACEHOLDER = "<secret>"
MIN_SECRET_VARIANT_LEN = 4

class SecretVariantRegistry:
    def __init__(self, max_entries: int = 512):
        self._max = max_entries
        self._variants: OrderedDict[str, None] = OrderedDict()

    @staticmethod
    def _variants_of(value: str) -> list[str]:
        forms = {value, urllib.parse.quote(value), json.dumps(value)[1:-1]}
        return sorted(f for f in forms if len(f) >= MIN_SECRET_VARIANT_LEN)

    def register(self, value: str) -> None:
        if not value or len(value) < MIN_SECRET_VARIANT_LEN:
            return
        for form in self._variants_of(value):
            if form in self._variants:
                self._variants.move_to_end(form)
            else:
                self._variants[form] = None
                if len(self._variants) > self._max:
                    self._variants.popitem(last=False)

    def __contains__(self, text: str) -> bool:
        return text in self._variants

    def __len__(self) -> int:
        return len(self._variants)

    def redact_text(self, text: str) -> str:
        # longest forms first so a longer variant never gets partially replaced by a shorter prefix
        for form in sorted(self._variants, key=len, reverse=True):
            if form in text:
                text = text.replace(form, REDACTION_PLACEHOLDER)
        return text

def get_global_registry() -> SecretVariantRegistry:
    """Process-global registry; redaction is belt-and-suspenders and must be cheap."""
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = SecretVariantRegistry()
    return _GLOBAL

_GLOBAL: SecretVariantRegistry | None = None
```

- [ ] **Step 4: Run, verify pass. Commit:**

```bash
git add halbert_core/halbert_core/ingestion/redaction_registry.py halbert_core/tests/ingestion/test_redaction_registry.py
git commit -m "feat(redaction): exact-value registry covering url-encoded and json-escaped variants"
```

### Task A2: Wire registration into the egress-ack path

**Files:**
- Modify: `halbert_core/halbert_core/config/queries.py` — in `get_config_value`, at the point where a value passes tier + acknowledgment + TTL and is returned raw (the only path that sets `EGRESS_ACK_FIELD`)
- Test: `halbert_core/tests/ingestion/test_redaction_registry.py` (append integration test with a monkeypatched config)

- [ ] **Step 1:** After the ack check succeeds, call `get_global_registry().register(value)` before returning. One line plus import. The rule being encoded: *the moment a secret is deliberately egressed, every encoded form of it becomes known-dangerous everywhere else.*
- [ ] **Step 2:** Test: a config value returned through the ack path is subsequently redacted from arbitrary text by `redact_text()` even when URL-encoded.
- [ ] **Step 3:** Run the config + ingestion suites. Commit: `feat(redaction): register egress-acked values in the variant registry`

### Task A3: Route `mcp/response.py` string redaction through the registry

**Files:**
- Modify: `halbert_core/halbert_core/mcp/response.py` — in `_redact_value()`'s string branch (after the existing `redact_text()` call, additionally apply `get_global_registry().redact_text(text)`)
- Test: extend `halbert_core/tests/ingestion/test_redaction_registry.py`

- [ ] **Step 1:** Compose the two passes: existing `redact_text()` first, registry pass second (registry is exact-value, so it is safe after key-based redaction).
- [ ] **Step 2:** Test: a tool result string containing an egress-acked value (raw and URL-encoded) is fully redacted through `mcp_response()`.
- [ ] **Step 3:** Run the MCP suite. Commit: `fix(mcp): response redaction consults the secret variant registry`

---

## Phase B — echo guard (second layer over the choke point)

OpenClaw's `boot-echo-guard.ts` caches recently injected sensitive prompts and suppresses any outbound delivery reproducing an 80-char contiguous chunk. Halbert's analogue: **config values deliberately egressed with acknowledgment** (the `EGRESS_ACK_FIELD` path) are the "recently injected sensitive material"; if an agent reply reproduces a long contiguous chunk of one, something is wrong — the model is echoing context it should paraphrase.

### Task B1: Pure detector

**Files:**
- Create: `halbert_core/halbert_core/security/echo_guard.py`
- Test: `halbert_core/tests/security/test_echo_guard.py`

- [ ] **Step 1: Write the failing tests**

```python
from halbert_core.halbert_core.security.echo_guard import EchoGuard

def test_exact_chunk_detected():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected("api key abc123def456ghi789jkl012mno345pqr678stu901 use it for calls")
    flagged = guard.scan_outbound("so the key is abc123def456ghi789jkl012mno345pqr678stu901 fyi")
    assert flagged

def test_short_overlap_not_flagged():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected("api key abc123def456 use it")
    assert not guard.scan_outbound("the key starts with abc123")

def test_paraphrase_not_flagged():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected("api key abc123def456ghi789jkl012mno345pqr678stu901")
    assert not guard.scan_outbound("I've confirmed the key is configured correctly and won't repeat it.")

def test_session_scoped_clear():
    guard = EchoGuard(window=40, threshold=40)
    guard.note_injected("x" * 60)
    guard.clear_session("default")
    assert not guard.scan_outbound("x" * 60)
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement `echo_guard.py`**

```python
"""Deterministic echo guard: second layer over the redaction choke point.

Lifted from OpenClaw src/gateway/boot-echo-guard.ts: rolling-window chunk match of
recently injected sensitive material against outbound deliveries. Catches the
model reproducing a long verbatim chunk even after paraphrasing around markers.
Pure detection — the wiring layer decides suppression vs. warn.
"""
from __future__ import annotations

class EchoGuard:
    def __init__(self, window: int = 80, threshold: int = 80):
        self._window = window
        self._threshold = threshold
        self._injected: set[str] = set()  # normalized chunk set per session scope

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.split())

    def note_injected(self, text: str, session: str = "default") -> None:
        norm = self._normalize(text)
        for i in range(0, max(1, len(norm) - self._window + 1):
            self._injected.add(norm[i:i + self._window])

    def scan_outbound(self, text: str, session: str = "default") -> bool:
        norm = self._normalize(text)
        for i in range(0, max(1, len(norm) - self._window + 1):
            if norm[i:i + self._window] in self._injected:
                return True
        return False

    def clear_session(self, session: str = "default") -> None:
        self._injected.clear()
```

(Note: `scan_outbound` flags any single window ≥ `window` chars; `threshold` is reserved for a minimum flagged-chunk count if telemetry shows false positives — leave the parameter, use `window` only.)

- [ ] **Step 4: Run, verify pass. Commit:** `feat(security): deterministic echo guard over injected sensitive material`

### Task B2: Wire the guard at the outbound seam (verify-first)

- [ ] **Step 1 — locate the seam (do not guess):** Find the single point where an assistant turn's final text is persisted/emitted toward the dashboard. Candidates to verify in this order: the transcript append in `agents/state_machine.py` (RESPONDING finalize), `SqliteConversationStore` append, or the dashboard agent route's response emission. Pick the point where *all* user-visible delivery passes; write the chosen path into the master plan status row before proceeding.
- [ ] **Step 2:** At `get_config_value`'s ack success (Phase A2 site), call `echo_guard.note_injected(value)`. At the chosen outbound seam, call `scan_outbound(final_text)`; on flag: **redact the flagged text through the registry and log a structured warning** (`echo_guard_flagged`, with a hash of the matched material — never the material itself). Do not silently drop the reply (single-user assistant; warn-and-redact is the right posture, review may upgrade it).
- [ ] **Step 3:** Integration test: an acked config value echoed verbatim into a reply arrives at the dashboard redacted, with a warning line in the log.
- [ ] **Step 4:** Run the full affected suites (agents + config + security). Commit: `feat(security): echo guard wired at outbound delivery with warn-and-redact`

---

## Phase C — one policy pipeline (parity extraction)

### Task C1: Shared redaction core for internal + MCP results

**Files:**
- Create: `halbert_core/halbert_core/security/result_redaction.py` — extracts the core of `mcp/response.py`'s `_redact_value`/`_redact_dict` as a reusable function `redact_result(payload)`.
- Modify: `halbert_core/halbert_core/mcp/response.py` — `mcp_response()` delegates to it (behavior byte-identical).
- Test: `halbert_core/tests/security/test_result_redaction.py` — table-driven cases run against BOTH `redact_result()` and `mcp_response()`, asserting identical outputs (parity pin, the pattern OpenClaw uses everywhere two surfaces must never drift).

- [ ] **Step 1:** Write the parity test first (it should fail on import). Step 2: extract; `mcp_response` becomes a thin wrapper. Step 3: run MCP suite + parity test. Step 4: Commit: `refactor(security): single redaction core shared by MCP and internal result paths`.

The consumer integration (routing internal tool results through `redact_result`) is deliberately **not** in this packet: whether internal executor results need the same treatment is a design question (they may pass through ingestion redaction already). The extraction alone kills the drift risk. Record the integration decision in the master plan for the deep pass.

### Task C2: camera_gate landmine guard

**Files:**
- Modify: `halbert_core/halbert_core/mcp/__init__.py` or `mcp/server.py` — add an import-time assertion next to the existing R2-OBS-1 note: if any tool id matching `frigate` or `vision` is present in `TOOL_HANDLERS`, `gate_response()` from `camera_gate.py` must be wired into that handler's return path — enforce as a registration-time check in the dispatch loop rather than a comment.

```python
# in the TOOL_HANDLERS registration/dispatch seam:
_CAMERA_TOOL_MARKERS = ("frigate", "vision", "camera")
def _assert_camera_gate_wired(tool_id: str) -> None:
    if any(marker in tool_id.lower() for marker in _CAMERA_TOOL_MARKERS):
        raise RuntimeError(
            f"camera/vision tool '{tool_id}' registered without the camera gate; "
            "wire mcp/camera_gate.gate_response into its return path first (R2-OBS-1)"
        )
```

- [ ] Test: registering a fake `frigate_snapshot` handler without the gate raises; with the gate passes. Commit: `fix(mcp): camera gate enforced at tool registration, not by convention`

---

## Verification gates (whole packet)

- `arch -arm64 .venv/bin/pytest halbert_core/tests/ingestion halbert_core/tests/security -v` plus the MCP suite — all pass.
- Tier-2 behavior unchanged: `describe_secret` still returns described-not-revealed values; `EGRESS_ACK_FIELD` escape still exactly one site.
- `git diff main..HEAD --stat` touches only: the new modules/tests, `ingestion/redaction_registry.py` consumers, `mcp/response.py`, `mcp/server.py` (or `__init__.py`), `config/queries.py` (one registration call), and the outbound seam found in B2.

## Executor gotchas

- Same as PACKET-02: `arch -arm64 .venv/bin/pytest`, pathspec commits, `halbert_core.halbert_core.…` import paths, no Co-Authored-By trailers.
- `.handoff/SECURITY-AUDIT-FINDINGS-2026-09-06.md` and the other audit-corpus files are **untracked on main** (committed only on the sec branch) — do not delete or move them; if you need to reference finding numbers, cite by section number from the findings doc and SEC-N row from `SECURITY-IMPLEMENTATION-PLAN-2026-09-06.md`.
- The redaction code is security-critical: if any existing test encodes today's redaction output in a golden file, the registry pass (A3) may change outputs — if a golden shifts, investigate WHY before updating it; a shift means a real string was previously passing through unredacted.

---

## ADDENDUM (2026-09-07, from the Hermes review — see `OSS-REVIEW-HERMES-2026-09-07.md` §8)

One Hermes finding extends this packet:

**Display-side redact+cap seam (new Task, Phase C).** Hermes ships tool text to its UI through exactly one seam — `_verbose_text(render, fallback)` → forced `redact_sensitive_text(force=True)` → hard cap (1000 chars / 16 lines, tail-keeping with an `[omitted N lines]` header). Full output stays in agent context and SQLite; only the redacted, capped preview crosses the wire — and the cap is an **OOM defense**, not just privacy (unbounded output blew up the render tree and killed the TUI parent, #34095). Reference: `tui_gateway/tool_progress.py`, `agent/redact.py`.

- [ ] Add a task to Phase C: audit Halbert's dashboard for the equivalent seam — where tool args/results are shipped to the Tauri frontend (SSE tool events, terminal block payloads, job status lines). If more than one emission path exists, either route them through one `_verbose_text()`-style helper or add the helper at the existing dominant seam. The helper = registry redaction (this packet's Phase A) + a hard cap with an omitted-lines marker. Tests: a tool result containing an egress-acked secret renders redacted at the frontend seam; a 50KB result arrives capped. Commit: `feat(security): display-side redact-and-cap seam on UI transport emissions`
- The related Hermes anti-pattern to note in review: their MCP `permissions_respond` is a wire tool with no enforcement path. When adding anything approval-shaped to Halbert's surfaces, the knob must route to the enforcement point (PACKET-02's decision records are the shape to emit).