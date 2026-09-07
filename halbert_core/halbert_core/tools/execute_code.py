# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""``execute_code`` — collapse a multi-step tool pipeline into one turn
(Packet 06, Phases A+B).

The model writes one Python script that calls Halbert's real agent tools
through the generated ``halbert_tools`` stub module
(``tools/script_stubs.py``). Only the script's stdout returns to context,
capped at a head and a tail with a spill-file pointer for the rest — the
zero-context win is that intermediate *results* never enter context.

The non-negotiable (the one deliberate design improvement over the Hermes
reference): **policy is preserved per call.** Every stub call is served by
``tools/script_rpc_host.py`` and dispatched through
``ToolExecutor.execute()`` — the same pipeline an interactive turn takes:
the guest allowlist, RoleGate, safety classification, and the audit log,
including the state-dependent semantic gates (R-DH-4) that no static stub
set can encode. A script is never a policy bypass.

Honest scope statement (founder sign-off F-1(a), 2026-09-07): the script
runs **non-sandboxed, in-process, in this same interpreter** — accepted for
a single-user local assistant. This is not a security boundary: script
code can read files and open sockets exactly as any Python in this
process can. What the per-call pipeline bounds is what scripts can do
*through Halbert's tools*, on the record; the deterministic script-text
gate below refuses the named shell-out affordances (subprocess imports,
``os.system``/``os.popen``) so tool work stays on the tool pipeline — a
scan, not a sandbox. Remote/sandboxed backends are recorded as future
extensions only (Packet 06 Phase C, not built).
"""
from __future__ import annotations

import asyncio
import ast
import importlib.util
import logging
import os
import sys
import tempfile
import threading
import time
import traceback
from typing import Dict, FrozenSet, Optional, Tuple

from .executor import current_speaker_role
from .safety import THREAD_META_TOOLS
from .script_rpc_host import ScriptRpcHost
from .script_stubs import generate_stub_module

logger = logging.getLogger("halbert.tools.execute_code")

TOOL_NAME = "execute_code"

#: Whole-script tool-call budget. The point is to stop a runaway loop, not
#: to ration ordinary work: 25 calls collapses even a fat pipeline.
DEFAULT_TOOL_CALL_BUDGET = 25
MAX_TOOL_CALL_BUDGET = 100
MAX_SCRIPT_BYTES = 256 * 1024

#: PACKET-03 addendum rule: the run dies after this long with no tool call
#: and no output byte — inactivity, not a flat wall clock, so a long but
#: productive run is never killed mid-thought.
INACTIVITY_SECONDS = 30.0

#: The stdout contract: 50 KiB head + 50 KiB tail enter context; the whole
#: stream is spilled to disk first so the model recovers instead of rerunning.
STDOUT_HEAD_BYTES = 50 * 1024
STDOUT_TAIL_BYTES = 50 * 1024
# Kept a little ahead of the cap so assembly never re-reads the spill file.
_HEAD_KEEP = 128 * 1024
_TAIL_KEEP = 128 * 1024

#: F-1(b) ratified: the default stub set is read-only. Write-plane tools stay
#: deferred behind the PACKET-02 lattice gate test; nothing in this set has
#: side effects beyond the read itself (web_search is an egress read — the
#: CAP_WEB switch still gates it, per call, inside the pipeline). Screen
#: capture stays out on purpose: vision consent is its own surface.
READ_ONLY_STUB_TOOLS: FrozenSet[str] = frozenset({
    "recall_memory",
    "read_file",
    "list_directory",
    "web_search",
    # read-side house and view tools (the guest derivation intersects these
    # with GUEST_ALLOWED_TOOLS, so a fronting guest sees only its own)
    "ha_get_entity_state",
    "frigate_list_cameras",
    "frigate_get_events",
    "frigate_get_reviews",
    "frigate_get_latest_frame",
    "frigate_get_snapshot",
    "capture_webcam",
    "detect_motion",
    "detect_objects",
    "detect_faces",
})

EXECUTE_CODE_SCHEMA: Dict = {
    "name": TOOL_NAME,
    "description": (
        "Run one short Python script that calls Halbert tools via the "
        "`halbert_tools` module; only the script's stdout is returned."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "The Python script to run (imports halbert_tools).",
            },
            "max_tool_calls": {
                "type": "integer",
                "description": "Tool-call budget for the run (default 25, max 100).",
            },
        },
        "required": ["script"],
    },
}


# ---------------------------------------------------------------------------
# Stub-set derivation
# ---------------------------------------------------------------------------

def _guest_fronting():
    """The guest persona fronting right now, or None. Lazy so this module
    never depends on the persona package at import."""
    try:
        from ..persona.guest import current_guest
        return current_guest()
    except Exception:
        return None


def _read_only_tools() -> FrozenSet[str]:
    """READ_ONLY_STUB_TOOLS plus the guest's own memory recall (read-only,
    served by the executor's guest-only path while a guest fronts)."""
    base = READ_ONLY_STUB_TOOLS
    try:
        from ..persona.guest_tools import RECALL_GUEST_MEMORY_TOOL_NAME
        return base | {RECALL_GUEST_MEMORY_TOOL_NAME}
    except Exception:
        return base


def derive_script_tool_sets(executor) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """What a run's stub module contains, and what its RPC boundary serves.

    Returns ``(stub_set, allow_set)``:

    * ``stub_set`` — the defs the generated ``halbert_tools`` module has.
      Read-only only (F-1(b)); the model is never offered a write-plane tool
      inside a script while the lattice deferral stands.
    * ``allow_set`` — what ``ScriptRpcHost`` will dispatch. With no guest
      fronting it equals the stub set: a forged ``_call('write_file', ...)``
      fails closed at the boundary (deferred, not a policy question).
      While a guest fronts, it is every tool the executor can serve except
      ``execute_code`` and the thread meta-tools — because the executor's
      own per-call guest gate is the authoritative, state-dependent refusal,
      and a script-side refusal must land in the audit log with exactly the
      record an interactive attempt produces, not a second weaker shape.

    ``execute_code`` is in neither set, by construction: a script must not
    be able to start another script run.
    """
    registered = frozenset(executor.tools)
    read_only = _read_only_tools()
    forbidden = {TOOL_NAME} | set(THREAD_META_TOOLS)

    if _guest_fronting() is None:
        stub = read_only & registered
        return stub - forbidden, stub - forbidden

    from ..persona.guest_tools import RECALL_GUEST_MEMORY_TOOL_NAME
    available = registered | {RECALL_GUEST_MEMORY_TOOL_NAME}
    stub = read_only & _guest_allowed() & available
    allow = available - forbidden
    return stub, allow


def _guest_allowed() -> FrozenSet[str]:
    try:
        from ..persona.guest_tools import GUEST_ALLOWED_TOOLS
        return GUEST_ALLOWED_TOOLS
    except Exception:
        return frozenset()


# ---------------------------------------------------------------------------
# Deterministic script-text gate (founder posture: deterministic-first)
# ---------------------------------------------------------------------------

_BANNED_MODULES = frozenset({"subprocess"})
_BANNED_OS_CALLS = frozenset({"system", "popen"})


def scan_script_text(script: str) -> list:
    """The deterministic gate on script text: an AST scan, no LLM.

    Refuses the named shell-out affordances — ``subprocess`` in any import
    form (including ``__import__``) and ``os.system``/``os.popen`` — so
    that tool work in scripts stays on the tool pipeline where it is
    classified, gated and audited per call. A scan, not a sandbox: this
    cannot see through dynamic strings, and the in-process execution model
    is accepted as such (module docstring, F-1(a)).
    """
    try:
        tree = ast.parse(script)
    except SyntaxError:
        return []  # exec reports the syntax error itself, as a script error

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _BANNED_MODULES:
                    violations.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level == 0 and root in _BANNED_MODULES:
                violations.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr in _BANNED_OS_CALLS
            ):
                violations.append(f"os.{node.attr}(...)")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "__import__":
                if (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and node.args[0].value.split(".")[0] in _BANNED_MODULES
                ):
                    violations.append(f"__import__({node.args[0].value!r})")
    return violations


# ---------------------------------------------------------------------------
# Stdout capture: write-through to the spill, head/tail kept in memory
# ---------------------------------------------------------------------------

class _OutputCapture:
    """Stand-in for sys.stdout during a run.

    Every byte is written through to the spill file as it happens — the
    spill is on disk *before* any cap is applied, so a truncated result is
    always recoverable without rerunning the script. Head and tail are
    kept in memory (a little ahead of the cap) so assembling the capped
    return never re-reads the file.
    """

    def __init__(self, activity: list, spill_path: Optional[str]):
        self.activity = activity
        self.spill_path = spill_path
        self.total = 0
        self.original = sys.stdout
        self._spill = None
        self._head = bytearray()
        self._tail = bytearray()

    # file-object surface used by print()
    def write(self, s) -> int:
        if not s:
            return 0
        data = s.encode("utf-8", "replace") if isinstance(s, str) else bytes(s)
        self.activity[0] = time.monotonic()
        self.total += len(data)
        if self._spill is None and self.spill_path:
            self._spill = open(self.spill_path, "wb")
        if self._spill is not None:
            self._spill.write(data)
        if len(self._head) < _HEAD_KEEP:
            room = _HEAD_KEEP - len(self._head)
            self._head.extend(data[:room])
            data = data[room:]
        if data:
            self._tail.extend(data)
            if len(self._tail) > _TAIL_KEEP:
                del self._tail[: len(self._tail) - _TAIL_KEEP]
        return len(s)

    def flush(self) -> None:
        if self._spill is not None:
            self._spill.flush()

    def isatty(self) -> bool:
        return False

    def close(self) -> None:
        if self._spill is not None:
            try:
                self._spill.close()
            except Exception:
                pass
            self._spill = None

    def assemble(self) -> Tuple[str, bool]:
        """The capped stdout, and whether truncation happened."""
        cap = STDOUT_HEAD_BYTES + STDOUT_TAIL_BYTES
        if self.total <= cap:
            return bytes(self._head).decode("utf-8", "replace"), False
        head = bytes(self._head)[:STDOUT_HEAD_BYTES]
        tail = bytes(self._tail)[-STDOUT_TAIL_BYTES:]
        elided = self.total - len(head) - len(tail)
        marker = (
            f"\n...[{elided} bytes elided] full output saved to {self.spill_path} — "
            f"read(offset={len(head)}) continues from where this cuts off "
            f"(read_file(path={self.spill_path!r}), or in a script: "
            f"halbert_tools.read_file(path={self.spill_path!r}))\n"
        )
        body = head.decode("utf-8", "replace") + marker + tail.decode("utf-8", "replace")
        return body, True


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _interrupt_worker(thread: threading.Thread) -> None:
    """Best-effort stop: raise KeyboardInterrupt in the script thread.

    Lands at the next Python bytecode boundary — a pure busy loop dies;
    a thread wedged in C code is the documented residual (the thread is
    a daemon and the run is already over).
    """
    tid = thread.ident
    if tid is None:
        return
    import ctypes

    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(tid), ctypes.py_object(KeyboardInterrupt)
    )


async def run_script(executor, args: Dict) -> Dict:
    """Execute one script run; the registered tool's handler body."""
    script = args.get("script")
    if not isinstance(script, str) or not script.strip():
        raise ValueError("execute_code requires a non-empty 'script' string")
    if len(script.encode("utf-8", "replace")) > MAX_SCRIPT_BYTES:
        raise ValueError(
            f"script too large ({MAX_SCRIPT_BYTES} byte cap) — split the work"
        )
    budget = args.get("max_tool_calls") or DEFAULT_TOOL_CALL_BUDGET
    try:
        budget = min(int(budget), MAX_TOOL_CALL_BUDGET)
    except (TypeError, ValueError):
        budget = DEFAULT_TOOL_CALL_BUDGET

    # Deterministic gate on the script text, before anything runs.
    violations = scan_script_text(script)
    if violations:
        raise ValueError(
            "script refused by the deterministic gate: "
            + ", ".join(violations)
            + ". Tool work in scripts goes through halbert_tools; direct "
            "subprocess/os.system use is not part of the script contract."
        )

    # The run's policy context: the executor set current_agent_session /
    # current_speaker_role around this handler; nested per-call dispatch
    # must carry the same session and the same speaker role, so RoleGate
    # caps exactly what it caps interactively — never looser.
    from ..streaming.terminal_bridge import current_agent_session

    session_id = current_agent_session.get()
    speaker_role = current_speaker_role.get() or "admin"

    stub_set, allow_set = derive_script_tool_sets(executor)
    host = ScriptRpcHost(allowed_tools=allow_set, budget=budget)
    loop = asyncio.get_running_loop()
    activity = [time.monotonic()]

    def dispatch(name: str, tool_args: Dict) -> Dict:
        """The integration seam: every stub call becomes a full
        ToolExecutor.execute() — guest gate, RoleGate, safety classify,
        audit — exactly the interactive pipeline (R-DH-4 included)."""
        activity[0] = time.monotonic()
        try:
            fut = asyncio.run_coroutine_threadsafe(
                executor.execute(
                    name, tool_args,
                    session_id=session_id, speaker_role=speaker_role,
                ),
                loop,
            )
            res = fut.result()
        except Exception as e:
            return {"error": f"{name} could not be dispatched: {e}"}
        finally:
            activity[0] = time.monotonic()
        if getattr(res, "success", False):
            return res.result
        if getattr(res, "requires_confirmation", False):
            return {
                "error": (
                    f"{name} requires user confirmation; confirmations cannot "
                    f"be granted inside a script — ask in your final answer"
                ),
            }
        return {"error": getattr(res, "error", None) or f"{name} failed"}

    host.dispatch_hook = dispatch

    # Per-run scratch: the stub module on sys.path, and the spill file.
    tmpdir = tempfile.mkdtemp(prefix="halbert-script-")
    fd, spill_path = tempfile.mkstemp(prefix="halbert-script-output-", suffix=".txt")
    os.close(fd)
    module_path = os.path.join(tmpdir, "halbert_tools.py")
    with open(module_path, "w", encoding="utf-8") as f:
        f.write(generate_stub_module(stub_set))

    # Import the stub module ourselves so the wiring is in place before any
    # script line runs; the script's `import halbert_tools` then gets the
    # wired module from sys.modules.
    spec = importlib.util.spec_from_file_location("halbert_tools", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["halbert_tools"] = module
    spec.loader.exec_module(module)
    module._call = host.bind_call()
    sys.path.insert(0, tmpdir)

    capture = _OutputCapture(activity, spill_path)
    done = threading.Event()
    outcome: Dict = {}

    def worker() -> None:
        try:
            sys.stdout = capture
            g: Dict = {"__name__": "__halbert_script__"}
            exec(compile(script, "<halbert_script>", "exec"), g)
            outcome["exc"] = None
        except BaseException as e:  # the script's failure is data, not ours
            outcome["exc"] = e
        finally:
            if sys.stdout is capture:
                sys.stdout = capture.original
            capture.close()
            done.set()

    thread = threading.Thread(target=worker, daemon=True, name="halbert-script")
    result: Optional[Dict] = None
    timed_out = False
    try:
        thread.start()
        while not done.is_set():
            await asyncio.sleep(0.25)
            if time.monotonic() - activity[0] > INACTIVITY_SECONDS:
                timed_out = True
                _interrupt_worker(thread)
        if timed_out:
            # Keep nudging until the injection lands or the grace runs out.
            grace_deadline = time.monotonic() + 10
            while not done.is_set() and time.monotonic() < grace_deadline:
                _interrupt_worker(thread)
                await asyncio.sleep(0.25)

        calls = host.calls_dispatched
        remaining = host.budget_remaining

        if timed_out:
            result = {
                "error": (
                    f"script stopped: {INACTIVITY_SECONDS:g}s with no tool "
                    f"call or output byte. If the work needs longer "
                    f"stretches of silence, print progress as you go."
                ),
                "tool_calls_made": calls,
                "budget_remaining": remaining,
            }
        elif outcome.get("exc") is None:
            stdout, truncated = capture.assemble()
            result = {
                "stdout": stdout,
                "truncated": truncated,
                "spill_path": spill_path if truncated else None,
                "tool_calls_made": calls,
                "budget_remaining": remaining,
            }
        else:
            exc = outcome["exc"]
            tb_tail = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )[-2000:]
            result = {
                "error": f"script raised {type(exc).__name__}: {exc}",
                "traceback_tail": tb_tail,
                "tool_calls_made": calls,
                "budget_remaining": remaining,
            }
    finally:
        # Per-run hygiene. The worker's finally restores stdout, but a
        # thread wedged in C code may never reach it, so the async side
        # restores too — idempotently.
        if sys.stdout is capture:
            sys.stdout = capture.original
        capture.close()
        sys.modules.pop("halbert_tools", None)
        if tmpdir in sys.path:
            sys.path.remove(tmpdir)
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
        keep_spill = capture.total > STDOUT_HEAD_BYTES + STDOUT_TAIL_BYTES
        if not keep_spill and os.path.exists(spill_path):
            try:
                os.remove(spill_path)
            except OSError:
                pass

    assert result is not None
    return result


def register_execute_code(executor) -> None:
    """Register the execute_code tool on an executor.

    A registrar of its own because the handler needs the executor
    instance: the stub pipeline dispatches back into that same
    executor's policy path, never around it.
    """

    async def _execute_code(args: Dict) -> Dict:
        return await run_script(executor, args)

    executor.register(TOOL_NAME, _execute_code, EXECUTE_CODE_SCHEMA)