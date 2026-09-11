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

#: How long the abandon path waits after the first interrupt injection
#: before giving up on the worker entirely (A04-G1). The worker is a
#: daemon thread, so abandoning it costs the process nothing at exit.
GRACE_SECONDS = 10.0

#: The most a script may spill to disk (A04-G3, fix-first row 13). The
#: spill was UNBOUNDED and every byte written counted as activity, so
#: ``while True: print('x'*4096)`` never timed out and filled the volume.
#: Past this the spill stops, output stops counting as activity, and the
#: run ends with a structured "output cap exceeded".
MAX_SPILL_BYTES = 5 * 1024 * 1024

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
        "`halbert_tools` module (e.g. `halbert_tools.recall_memory(query=...)`) "
        "to collapse a multi-step pipeline into a single tool call. "
        "Use for 3+ tool calls with logic between them: filtering/reducing large "
        "outputs before they enter context, branching, or loops. "
        "Prefer normal tool calls for 1-2 calls. "
        "Tool functions take keyword arguments and return dicts (do not "
        "json.loads() them); only stdout is returned, capped at 50KiB head + "
        "50KiB tail with a spill-file pointer to the full output. Tool calls "
        "inside the script go through the same policy pipeline as interactive "
        "calls, so a refused call returns an {'error': ...} dict the script "
        "can branch on. print() a compact summary as the script's last step."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": (
                    "The Python script to run (imports halbert_tools). "
                    "It runs with __name__ == '__main__', so a "
                    "`if __name__ == \"__main__\":` block does fire. "
                    "stdout AND stderr come back, and a script that "
                    "raises still returns whatever it printed first."
                ),
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
        # Mode-aware: private mode must not leak Halbert's memory through
        # the script pipeline's view of the allowlist.
        from ..persona.guest_tools import guest_allowed_tools
        return guest_allowed_tools()
    except Exception:
        return frozenset()


# ---------------------------------------------------------------------------
# Deterministic script-text gate (founder posture: deterministic-first)
# ---------------------------------------------------------------------------

_BANNED_MODULES = frozenset({"subprocess"})
_BANNED_OS_CALLS = frozenset({"system", "popen"})


def resolve_budget(args: Dict) -> int:
    """The tool-call budget for one run (A04 bug 6).

    ``args.get("max_tool_calls") or DEFAULT`` read a deliberate ZERO as
    "unset" and handed the script the full default of 25 calls — the one
    value a caller passes when it means "none".
    """
    raw = args.get("max_tool_calls")
    if raw is None:
        return DEFAULT_TOOL_CALL_BUDGET
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_TOOL_CALL_BUDGET
    return max(0, min(value, MAX_TOOL_CALL_BUDGET))


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
    # A04 bug 1: the gate missed the obvious spellings. ``import os as o``
    # bound the module to a name the Attribute check never looked at, and
    # ``from os import system`` bound the FUNCTION directly so no
    # attribute access existed to see. Both are resolved by walking the
    # bindings first.
    os_aliases = {"os"}
    banned_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BANNED_MODULES:
                    violations.append(f"import {alias.name}")
                if root == "os" and alias.asname:
                    os_aliases.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level == 0 and root in _BANNED_MODULES:
                violations.append(f"from {node.module} import ...")
            if node.level == 0 and root == "os":
                for alias in node.names:
                    if alias.name in _BANNED_OS_CALLS:
                        banned_names.add(alias.asname or alias.name)
                        violations.append(f"from os import {alias.name}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in _BANNED_OS_CALLS
            ):
                violations.append(f"{node.value.id}.{node.attr}(...)")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in banned_names:
                violations.append(f"{func.id}(...)")
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

    def __init__(
        self, activity: list, spill_path: Optional[str],
        max_spill: int = MAX_SPILL_BYTES,
    ):
        self.activity = activity
        self.spill_path = spill_path
        self.total = 0
        self.original = sys.stdout
        self._spill = None
        self._closed = False
        self._head = bytearray()
        self._tail = bytearray()
        self._max_spill = max(0, int(max_spill))
        #: A04-G3: whether the run blew the output budget.
        self.cap_exceeded = False

    # file-object surface used by print()
    def write(self, s) -> int:
        if not s:
            return 0
        data = s.encode("utf-8", "replace") if isinstance(s, str) else bytes(s)
        # A04-G3: output counts as activity only while the run is still
        # inside its output budget. A script printing in a tight loop
        # kept refreshing its own liveness stamp, so the inactivity
        # deadline never fired -- the loop was, in the watchdog's eyes,
        # working the whole time.
        self.total += len(data)
        if self._max_spill and self.total > self._max_spill:
            if not self.cap_exceeded:
                self.cap_exceeded = True
                self._close_spill()
            # Not even the write that crosses the cap counts: once the
            # run is over budget, output is no longer evidence that it is
            # doing something worth waiting for.
            return len(s)
        self.activity[0] = time.monotonic()
        # A worker wedged in C code can outlive the run; once the run is
        # over and the spill deleted, a late write must not resurrect it.
        if self._spill is None and self.spill_path and not self._closed:
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

    def _close_spill(self) -> None:
        if self._spill is not None:
            try:
                self._spill.flush()
                self._spill.close()
            except Exception:
                pass
            self._spill = None

    def flush(self) -> None:
        if self._spill is not None:
            self._spill.flush()

    def isatty(self) -> bool:
        return False

    def close(self) -> None:
        self._closed = True
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


#: A04-G11 + bug 4: one script at a time in this process. The run
#: mutates ``sys.stdout``, ``sys.stderr``, ``sys.path`` and
#: ``sys.modules["halbert_tools"]`` -- all process-wide. Two overlapping
#: runs corrupted each other's capture (each seeing the other's print
#: output) and raced the stub module. The in-process execution model is
#: accepted (F-1), so serialising is the fix rather than isolating.
_RUN_LOCK = asyncio.Lock()


def _stop_requested() -> bool:
    """Whether the turn running this script has been stopped (A04-G9).

    Reads the machine's own cancelled flag through the ContextVar the
    executor binds for the turn, so a user stop ends the SCRIPT and not
    only the turn wrapped around it. Nothing beyond that ContextVar is
    reached for -- the packet's STOP condition.
    """
    try:
        from ..tools.executor import current_agent_session
        session_id = current_agent_session.get()
    except Exception:
        return False
    if not session_id:
        return False
    try:
        from ..dashboard.routes.agent import _agent_instance
        agent = _agent_instance
    except Exception:
        return False
    try:
        return bool(getattr(agent, "cancelled", {}).get(session_id))
    except Exception:
        return False


async def run_script(
    executor,
    args: Dict,
    inactivity_seconds: float = INACTIVITY_SECONDS,
    grace_seconds: float = GRACE_SECONDS,
) -> Dict:
    """Execute one script run; the registered tool's handler body.

    Serialised process-wide (``_RUN_LOCK``): the run owns ``sys.stdout``,
    ``sys.stderr``, ``sys.path`` and the stub module for its duration,
    and two overlapping runs corrupted each other's capture.
    """
    async with _RUN_LOCK:
        return await _run_script_locked(
            executor, args, inactivity_seconds, grace_seconds)


async def _run_script_locked(
    executor, args: Dict, inactivity_seconds: float, grace_seconds: float,
) -> Dict:
    script = args.get("script")
    if not isinstance(script, str) or not script.strip():
        raise ValueError("execute_code requires a non-empty 'script' string")
    if len(script.encode("utf-8", "replace")) > MAX_SCRIPT_BYTES:
        raise ValueError(
            f"script too large ({MAX_SCRIPT_BYTES} byte cap) — split the work"
        )
    budget = resolve_budget(args)

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
    stderr_capture = _OutputCapture(activity, None)
    done = threading.Event()
    outcome: Dict = {}

    def worker() -> None:
        original_stderr = sys.stderr
        try:
            sys.stdout = capture
            # A04-G8: stderr was not captured at all, so a script's
            # warnings and its own diagnostics went to the daemon's
            # stderr and were lost to the caller entirely.
            sys.stderr = stderr_capture
            # A04-G5 (FD-18): ``__name__`` was "__halbert_script__", so
            # every ``if __name__ == "__main__":`` block a person pasted
            # in silently did nothing. The marker stays available as its
            # own name, so a script CAN still tell where it is running.
            g: Dict = {"__name__": "__main__", "__halbert_script__": True}
            exec(compile(script, "<halbert_script>", "exec"), g)
            outcome["exc"] = None
        except BaseException as e:  # the script's failure is data, not ours
            outcome["exc"] = e
        finally:
            if sys.stdout is capture:
                sys.stdout = capture.original
            if sys.stderr is stderr_capture:
                sys.stderr = original_stderr
            capture.close()
            stderr_capture.close()
            done.set()

    thread = threading.Thread(target=worker, daemon=True, name="halbert-script")
    result: Optional[Dict] = None
    timed_out = False
    abandoned = False
    cap_exceeded = False
    stopped = False
    try:
        thread.start()
        # A04-G1 + bug 2 (fix-first row 12): this loop used to run
        # ``while not done.is_set()`` with the grace loop AFTER it, so
        # the grace was only ever entered once the worker had already
        # finished. An ``except BaseException`` retry wrapper, an
        # ``input()``, or an ``Event().wait()`` swallowed every injection
        # and run_script NEVER RETURNED -- the turn hung holding the turn
        # lock. The deadline breaks the first loop; the grace follows;
        # then the daemon thread is abandoned and the run returns.
        while not done.is_set() and not timed_out:
            await asyncio.sleep(0.25)
            if capture.cap_exceeded and not cap_exceeded:
                cap_exceeded = True
                timed_out = True
                _interrupt_worker(thread)
                break
            # A04-G9: a user stop ends a script, not just the turn around
            # it. The predicate is the machine's own cancelled flag,
            # read through the ContextVar the executor already binds.
            if _stop_requested():
                stopped = True
                timed_out = True
                _interrupt_worker(thread)
                break
            if time.monotonic() - activity[0] > inactivity_seconds:
                timed_out = True
                _interrupt_worker(thread)
                break
        if timed_out:
            # Keep nudging until the injection lands or the grace runs out.
            grace_deadline = time.monotonic() + grace_seconds
            while not done.is_set() and time.monotonic() < grace_deadline:
                _interrupt_worker(thread)
                await asyncio.sleep(0.25)
            abandoned = not done.is_set()
            if abandoned:
                logger.warning(
                    "execute_code: worker did not settle within %.0fs of the "
                    "interrupt; abandoning the daemon thread and returning",
                    grace_seconds,
                )

        calls = host.calls_dispatched
        remaining = host.budget_remaining

        # A04-G4: everything below crosses to the MODEL and the store, so
        # it goes through the shared redaction core -- the packet-05 open
        # item 05-C, resolved for scripts (FD-24).
        stdout, truncated = capture.assemble()
        stderr_text, _ = stderr_capture.assemble()
        if timed_out:
            if cap_exceeded:
                reason = (
                    f"script stopped: output exceeded the {MAX_SPILL_BYTES} "
                    f"byte cap. Print what matters, not everything."
                )
            elif stopped:
                reason = "script stopped: you asked me to stop."
            else:
                reason = (
                    f"script stopped: {inactivity_seconds:g}s with no tool "
                    f"call or output byte. If the work needs longer "
                    f"stretches of silence, print progress as you go."
                )
            if abandoned:
                reason += (
                    " The script did not respond to the interrupt and was "
                    "abandoned; anything it started may still be running."
                )
            result = {
                "error": reason,
                # FD-17: the partial stdout survives. A script that
                # printed for two minutes and then hung used to return
                # nothing at all, which is the least useful moment to
                # discard the output.
                "stdout": stdout,
                "stderr": stderr_text,
                "truncated": truncated,
                "spill_path": spill_path if truncated else None,
                "tool_calls_made": calls,
                "budget_remaining": remaining,
            }
        elif outcome.get("exc") is None:
            result = {
                "stdout": stdout,
                "stderr": stderr_text,
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
                # FD-17: partial stdout on failure, and the spill kept.
                # The error stays its own structured field, so nothing
                # has to guess which half is which.
                "error": f"script raised {type(exc).__name__}: {exc}",
                "traceback_tail": tb_tail,
                "stdout": stdout,
                "stderr": stderr_text,
                "truncated": truncated,
                "spill_path": spill_path if truncated else None,
                "tool_calls_made": calls,
                "budget_remaining": remaining,
            }
        # A04-G4: the TEXT fields only. Running the whole dict through
        # the redactor rewrote ``spill_path`` -- a temp filename whose
        # random segment reads like a token -- into "<token>.txt", which
        # broke the one field a caller needs in order to re-read the
        # output the cap elided. Structural fields are not prose.
        try:
            from ..security.result_redaction import redact_string
            for field in ("stdout", "stderr", "error", "traceback_tail"):
                value = result.get(field)
                if isinstance(value, str) and value:
                    result[field] = redact_string(value)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("execute_code result redaction failed: %s", e)
    finally:
        # Per-run hygiene. The worker's finally restores stdout, but a
        # thread wedged in C code may never reach it, so the async side
        # restores too — idempotently, and A04 bug 4: UNCONDITIONALLY.
        # ``if sys.stdout is capture`` left the process's stdout pointing
        # at a dead run's capture whenever an abandoned worker had
        # already swapped it for something else.
        sys.stdout = capture.original
        sys.stderr = stderr_capture.original
        capture.close()
        stderr_capture.close()
        # A04-G2 (fix-first row 11): the host retires. The hook used to
        # stay wired, so a thread the script left behind could dispatch
        # tools under the old session and role after the run returned.
        host.retire()
        sys.modules.pop("halbert_tools", None)
        if tmpdir in sys.path:
            sys.path.remove(tmpdir)
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
        # FD-17: the spill is kept on a FAILED run too -- that is the
        # run whose output someone most needs.
        keep_spill = capture.total > STDOUT_HEAD_BYTES + STDOUT_TAIL_BYTES
        if not keep_spill and os.path.exists(spill_path):
            try:
                os.remove(spill_path)
            except OSError:
                pass
        logger.info(
            "execute_code run finished: tool_calls=%d budget_remaining=%d",
            host.calls_dispatched, host.budget_remaining,
        )

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

    # A04-G7: the schema NAMES the stub set this executor actually
    # offers, instead of describing "Halbert tools" in the abstract. A
    # model writing a script had to guess which functions exist, and a
    # guess that misses fails at import time with a NameError the model
    # then has to debug from a traceback tail.
    schema = dict(EXECUTE_CODE_SCHEMA)
    try:
        stub_set, _allow = derive_script_tool_sets(executor)
        if stub_set:
            names = ", ".join(sorted(stub_set))
            schema["description"] = (
                schema["description"]
                + f" Available in halbert_tools: {names}."
            )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("execute_code schema stub list unavailable: %s", e)

    executor.register(TOOL_NAME, _execute_code, schema)