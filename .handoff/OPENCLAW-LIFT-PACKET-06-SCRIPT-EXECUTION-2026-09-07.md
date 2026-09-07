# OPENCLAW-LIFT-PACKET-06 — Zero-context-cost script execution (`execute_code`)

**Series:** Hermes-derived packet 1 of 4 (master plan: `OPENCLAW-LIFT-MASTER-PLAN-2026-09-07.md`)
**Source research:** `.handoff/OSS-REVIEW-HERMES-2026-09-07.md` §1
**Hermes source of record:** `/Volumes/Thunderbolt/AI/OSS/hermes-agent/tools/code_execution_tool.py` (931 lines — the whole mechanism), `tools/code_execution_rpc.py`, `tools/code_kernel.py`, `agent/auxiliary_client.py`
**Executor tier:** Phases A–B pure/host-side — small-model friendly with care. Phase C (kernel persistence) optional, defer. **Founder sign-off recommended before dispatch** (new capability surface).
**Status:** READY TO DISPATCH after sign-off

---

## Objective

Give Halbert's agent the ability to collapse a multi-step tool pipeline into one turn: the model writes **one Python script** that calls Halbert's real agent tools through a generated stub module; only the script's **stdout** returns to context (capped, with a spill-file pointer). The wins:

- A "scan every terminal session's scrollback, classify, act" pipeline becomes one tool call instead of 40 turns of grep/read/parse round-trips.
- **Policy is preserved per-call**: unlike Hermes (whose scripts can `os.system` past the terminal guard — documented in their own docstring), Halbert's stubs call back into `ToolExecutor.execute()` through the **same policy pipeline as interactive turns**. The zero-context win is that intermediate *results* never enter context — never that policy is bypassed. This is the one deliberate design improvement over the reference; keep it non-negotiable.

## Verified current state (do not re-derive; verified 2026-09-07)

- Tool dispatch: `halbert_core/halbert_core/tools/executor.py` — process-global `ToolExecutor` built by `dashboard/routes/agent.py get_agent()`; `register(name, handler)` (become-tool registrar at :1052), `get_schemas()` (:374, narrows to `GUEST_ALLOWED_TOOLS` while a guest fronts), `execute()` (:398, refuses hidden tools, audited refusals). RoleGate wraps `ToolSafetyFramework.classify()` (`tools/role_gate.py`), wired at `routes/agent.py:127`.
- Guest/write-plane: `persona/guest_tools.py` — `WRITE_PLANE_TOOLS` = `{run_command, write_file, write_config, schedule_cron, terminal_blocks}` (audit-log writers); `is_tool_allowed_for_guest()` authoritative.
- The agent's turns are serialized by `_turn_lock` (`routes/agent._agent_instance`); the state machine runs `IDLE→PLAN→…→RESPONDING` with `ContextAssembler.assemble()` at `state_machine.py:1939`.
- Python 3.11+, macOS (arm64); the core is sync Python inside an asyncio FastAPI process.

## Out-of-scope guards

- **No `subprocess`/`os.system` in the stub contract.** The generated module exposes ONLY registered Halbert tools. Hermes's guard docstring admits scripts can shell out past tool guards; Halbert's answer is different: the *execution environment* is the same interpreter with no shell affordances added, and any script use of `subprocess` is a policy question for the executor's own safety classifier on the *script text* (Phase B gate). Do not add a Python kernel with implicit imports beyond a documented allowlist.
- **Per-call policy includes state-dependent semantic gates, not just tool-set membership** (DebateHaus R-DH-4): a stub call's dispatch through `ToolExecutor.execute()` must preserve checks like "the turn holder cannot be in violation of their own turn" — semantic rules against session state that the stub set cannot encode. This is the second reason (after the one-policy-pipeline rule) the stub must call back through the executor; the Phase B dispatch hook must not be a bare allow-list check but the full executor path.
- **No remote/sandboxed backends** (Docker/SSH/Modal) — Halbert runs locally; the file-based RPC transport is recorded as a future extension only if satellite execution ever needs it.
- **No write-plane tools in the default stub set.** Phase A stubs = read-only tools (`recall_memory`, read-side terminal/watch tools, web-search/read if present). Write-plane tools in stubs require the PACKET-02 lattice merged and a per-call gate test (Phase B).
- Do NOT copy Hermes's `background/pty/notify/watch_patterns` param-stripping complexity; the per-call policy pipeline makes it unnecessary.

---

## Phase A — the host-side RPC core (pure, no agent integration)

**Branch:** `feat/script-execution` off `main`.

### Task A1: The stub-module generator

**Files:**
- Create: `halbert_core/halbert_core/tools/script_stubs.py`
- Test: `halbert_core/tests/tools/test_script_stubs.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Generated stub module: one def per allowed tool, compiled per-run from the
enabled-tool intersection. A disabled tool physically does not exist in the
module (Hermes pattern) — the model cannot keep trying it."""
import types
from halbert_core.halbert_core.tools.script_stubs import generate_stub_module, DEFAULT_STUB_TOOLS

def test_module_is_plain_source_and_executes():
    src = generate_stub_module(tool_names=["recall_memory", "list_terminals"])
    assert "def recall_memory(" in src and "def list_terminals(" in src
    ns = {}
    exec(src, ns)  # noqa: S102 - testing generated source
    assert callable(ns["recall_memory"])

def test_disabled_tool_absent():
    src = generate_stub_module(tool_names=["recall_memory"])
    assert "write_file" not in src

def test_stub_call_reaches_rpc():
    captured = {}
    src = generate_stub_module(tool_names=["recall_memory"])
    ns = {"_call": lambda name, args: captured.update(name=name, args=args) or {"ok": True}}
    exec(src, ns)  # noqa: S102
    result = ns["recall_memory"](query="scanner")
    assert captured == {"name": "recall_memory", "args": {"query": "scanner"}}
    assert result == {"ok": True}

def test_docstrings_describe_return_shapes():
    src = generate_stub_module(tool_names=DEFAULT_STUB_TOOLS)
    assert "returns dicts" in src  # failure-hint discipline from Hermes: tools return structured data
```

- [ ] **Step 2: Run, verify failure.** `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/tools/test_script_stubs.py -q`

- [ ] **Step 3: Implement `script_stubs.py`**

```python
"""Generate the per-run `halbert_tools.py` stub module (Hermes code_execution_tool pattern).

Plain-source Python, zero dependencies, written to a temp dir and put on sys.path
for the run. One def per tool in `tool_names` — the intersection decides what
exists. Every stub routes through `_call(name, args)`, the host-side RPC seam.
"""
from __future__ import annotations
import textwrap

DEFAULT_STUB_TOOLS = ("recall_memory",)  # Phase A: read-only; extend per the enabled-tool set at dispatch

_TEMPLATE = '''
"""Halbert agent tools. Generated per run — do not edit.
Tool functions return DICTS (structured results); do not json.loads() their output.
Call tools by keyword arguments matching the tool schema.
"""
def _call(name, args):
    raise NotImplementedError("wired by the host at run time")

{defs}
'''

_DEF = '''
def {name}(**kwargs):
    """Halbert tool `{name}` — returns a structured dict."""
    return _call({name!r}, kwargs)
'''

def generate_stub_module(tool_names) -> str:
    defs = "".join(_DEF.format(name=t) for t in tool_names)
    return _TEMPLATE.format(defs=defs)
```

- [ ] **Step 4: Run, verify pass. Commit:** `feat(tools): generated per-run tool stub module for script execution`

### Task A2: The RPC host — token, allow-list, budget, dispatch-through-policy

**Files:**
- Create: `halbert_core/halbert_core/tools/script_rpc_host.py`
- Test: `halbert_core/tests/tools/test_script_rpc_host.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Host-side RPC: the ONLY place a stub call is served. Enforcement order is
fixed (Hermes order): token -> allow-list -> budget -> dispatch -> log.
Budget is consumed only by a dispatched call (refusals are free)."""
import os, pytest
from halbert_core.halbert_core.tools.script_rpc_host import ScriptRpcHost

def _host(allowed=("recall_memory",), budget=3):
    calls = []
    host = ScriptRpcHost(allowed_tools=set(allowed), budget=budget)
    host.dispatch_hook = lambda name, args: calls.append((name, args)) or {"ok": True}
    return host, calls

def test_valid_token_and_tool_dispatches():
    host, calls = _host()
    host.reveal_token_for_test = True
    tok = host.issue_token()
    assert host.handle(tok, "recall_memory", {"query": "x"}) == {"ok": True}
    assert calls == [("recall_memory", {"query": "x"})]

def test_bad_token_fails_closed():
    host, _ = _host()
    assert "error" in host.handle("wrong", "recall_memory", {})

def test_disallowed_tool_refused_without_budget_cost():
    host, calls = _host(allowed=("recall_memory",), budget=1)
    before = host.budget_remaining
    res = host.handle(host.issue_token(), "write_file", {"path": "x"})
    assert "error" in res and "not available in scripts" in res["error"]
    assert host.budget_remaining == before  # refusal is free

def test_budget_exhaustion_then_dispatch_refused():
    host, calls = _host(budget=1)
    tok = host.issue_token()
    host.handle(tok, "recall_memory", {})
    assert "error" in host.handle(tok, "recall_memory", {})
```

- [ ] **Step 2: Run, verify failure. Step 3: Implement** — `ScriptRpcHost` holds: `secrets.token_hex(32)` token compared with `secrets.compare_digest` (fail closed on empty); `allowed_tools: frozenset`; `budget: list[int]` (mutable single-slot counter); `handle(token, name, args)` returning `{"error": ...}` dicts on every refusal (never raising into the script); `dispatch_hook` — **the integration seam: Phase B wires this to `ToolExecutor.execute()` so every existing gate (RoleGate, guest allowlist, safety classify, audit) runs per call unchanged.** Every handled call logs one structured line (tool name, budget delta; never args).

- [ ] **Step 4: Run, verify pass. Commit:** `feat(tools): host-side script RPC with token/allow-list/budget discipline`

---

## Phase B — the `execute_code` tool

### Task B1: Tool handler + transport

**Files:**
- Create: `halbert_core/halbert_core/tools/execute_code.py` (the registered tool handler)
- Modify: `halbert_core/halbert_core/tools/executor.py` (register; stub set derivation)
- Test: `halbert_core/tests/tools/test_execute_code.py`

- [ ] **Step 1: Write failing tests:**

```python
"""The one-turn pipeline tool: script runs in-process with the generated stub on
sys.path; the stub's _call is routed through ToolExecutor.execute() — the SAME
policy pipeline as interactive turns; only capped stdout enters the result."""
```

Test cases (write them all before implementing):
1. A script calling `recall_memory(...)` returns that tool's real result dict; **`ToolExecutor.execute()` was invoked** (monkeypatch-asserted) — the one-policy-pipeline pin.
2. Guest fronting: with `current_guest()` fronting, the stub set is `GUEST_ALLOWED_TOOLS ∩ read-only` and `write_file` calls return the guest refusal, audited exactly as an interactive attempt would be.
3. Write-plane tool in a script: **refused** unless the PACKET-02 lattice test suite passes its guest-floor test in the same run (guard: skip this test if lattice not yet merged; mark it in the handoff).
4. Stdout cap: a script printing 100KB returns a 50KB-head/50KB-tail-capped result with a spill file path + `recall-style read(offset=...)` pointer; the spill file is written before the cap is applied (recover-don't-rerun).
5. Tool errors inside the script surface as `{"error": ...}` dicts to the script (the script decides how to continue); an unhandled script exception returns a structured error with the traceback tail, never raw stdout.
6. Budget propagation: the run's `ScriptRpcHost` budget (default 25 calls) is enforced across the whole script.

- [ ] **Step 2: Implement.** Handler flow: derive stub set = registered tools ∩ (read-only default set; guest-intersected when fronting) → write `halbert_tools.py` to a per-run temp dir → prepend to `sys.path` for the run only → exec the script with `__name__ == "__halbert_script__"` → capture stdout with the cap + spill → return `{stdout, spill_path, tool_calls_made, budget_remaining}`. The script timeout is **inactivity-based** (PACKET-03 addendum rule): 30s without a tool call or an output byte kills the run, not a flat wall clock.

- [ ] **Step 3:** Run the tools + persona suites. **Step 4: Commit:** `feat(tools): execute_code — one-turn tool pipelines through the standard policy pipeline`

### Task B2: Prompt + schema description

- [ ] Write the tool description with Hermes's when-to-use discipline: "Use for 3+ tool calls with logic between them: filtering/reducing large outputs before they enter context, branching, or loops. Prefer normal tool calls for 1–2 calls." Register in the prompt tier alongside `recall_memory` (agent_prompts.py:785 neighborhood). Add the failure-hint line to the stub docstrings: tools return DICTS. Commit: `feat(tools): execute_code schema and prompt guidance`

---

## Phase C — recorded, do not build now

- **Persistent kernels** (variables/imports surviving across `execute_code` calls; Hermes `code_kernel.py` with per-kernel random sentinels and parent-death pipe) — defer until usage proves the re-import cost matters.
- **File-based RPC for remote backends** — only if satellite execution (fleet proxy) ever needs it.
- **Failure-hint rule table** (Hermes mined theirs from production): revisit after the first month of usage logs; don't pre-invent hints.

## Verification gates (whole packet)

- One-policy-pipeline pin: every test asserts stub calls traverse `ToolExecutor.execute()` — grep the diff for any path that calls a tool handler directly.
- Guest floor holds: fronting-guest script cannot reach any write-plane tool; refusals are audited with the same records as interactive attempts.
- `cd halbert_core && arch -arm64 ../.venv/bin/python -m pytest tests/tools tests/persona -q` green; no regressions in the guest allowlist self-check.
- The tool is **off** for the guest persona by default (not in `GUEST_ALLOWED_TOOLS`) — pin with a test that the guest schema set excludes `execute_code`.

## Executor gotchas

- Standard set: `arch -arm64 ../.venv/bin/python -m pytest` from `halbert_core/`; worktrees need `arch -arm64 ./wt_pytest.py`; pathspec commits; no co-author trailers.
- The process-global `ToolExecutor` is shared — the `ScriptRpcHost` must never re-enter `execute()` re-entrantly for the *same* turn (guard: the host is created per `execute_code` call, and tool calls made from inside the script must not themselves be `execute_code` — the stub set excludes it by construction; pin with a test).
- `sys.path` manipulation is per-run and restored in a `finally`; a leaked path entry is a test failure, not a warning.