# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The one-turn pipeline tool: script runs in-process with the generated stub
on sys.path; the stub's _call is routed through ToolExecutor.execute() — the
SAME policy pipeline as interactive turns; only capped stdout enters the
result.

Pins (Packet 06 verification gates):
- one policy pipeline: stub calls traverse ToolExecutor.execute();
- the guest floor: execute_code is off for the guest persona by default,
  and a fronting guest's script cannot reach any write-plane tool while
  refusals are audited exactly as interactive attempts are;
- write-plane stubs stay deferred behind the PACKET-02 lattice;
- budget is enforced across the whole script; the run is killed on
  inactivity, not wall clock;
- sys.path / sys.modules manipulation is per-run and always restored.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

from halbert_core.persona import guest
from halbert_core.persona.guest_tools import (
    GUEST_ALLOWED_TOOLS,
    guest_allowed_tools,
    RECALL_GUEST_MEMORY_TOOL_NAME,
)
from halbert_core.tools import execute_code as execute_code_mod
from halbert_core.tools.executor import ToolExecutor


@pytest.fixture(autouse=True)
def _fresh_guest_state():
    guest.reset_for_tests()
    yield
    guest.reset_for_tests()


def _front(name="Marnie"):
    persona, _ = guest.GuestPersona.from_payload({"name": name})
    return guest.offer(persona, offered_by="h2-node", offered_by_name="H2")


def _executor(audits=None):
    """An executor with execute_code registered (it is a builtin) and a
    cheap fake recall_memory so tests do not touch the real ledger."""
    async def fake_recall(args):
        return {"records": [], "query": args.get("query")}

    if audits is None:
        executor = ToolExecutor(web_search=True)
    else:
        executor = ToolExecutor(web_search=True, audit_fn=lambda **kw: audits.append(kw))
    executor.register("recall_memory", fake_recall, {"name": "recall_memory", "parameters": {}})
    return executor


async def _run(executor, script, **extra):
    return await executor.execute("execute_code", {"script": script, **extra})


# ---------------------------------------------------------------------------
# The one-policy-pipeline pin
# ---------------------------------------------------------------------------

class TestOnePolicyPipeline:

    async def test_stub_calls_traverse_executor_execute(self):
        executor = _executor()
        seen = []
        original = executor.execute

        async def spy(tool_name, args, **kw):
            seen.append((tool_name, args))
            return await original(tool_name, args, **kw)

        executor.execute = spy
        result = await _run(
            executor,
            "import halbert_tools\n"
            "r = halbert_tools.recall_memory(query='scanner')\n"
            "print(r['query'])\n",
        )
        assert result.success, result.error
        # The stub call went through ToolExecutor.execute, after the outer
        # execute_code call that started the run.
        assert seen[0][0] == "execute_code"
        assert ("recall_memory", {"query": "scanner"}) in seen
        # ...and the script received the tool's real result dict.
        assert result.result["stdout"].strip() == "scanner"
        assert result.result["tool_calls_made"] == 1

    async def test_tool_result_dicts_reach_the_script_whole(self):
        executor = _executor()
        result = await _run(
            executor,
            "import halbert_tools\n"
            "r = halbert_tools.recall_memory(query='x')\n"
            "print(sorted(r.keys()))\n",
        )
        assert "records" in result.result["stdout"]


# ---------------------------------------------------------------------------
# Stub set derivation and the guest floor
# ---------------------------------------------------------------------------

class TestStubSetDerivation:

    def test_owner_stub_set_is_read_only_intersection(self):
        executor = _executor()
        stub, allow = execute_code_mod.derive_script_tool_sets(executor)
        expected = {
            "recall_memory", "read_file", "list_directory", "web_search",
        }
        assert stub == expected
        assert allow == expected  # write-plane deferred for the owner too
        assert "execute_code" not in stub  # re-entrancy: by construction
        assert not (stub & {"run_command", "write_file", "terminal_blocks"})

    def test_guest_stub_set_is_allowed_intersect_read_only(self):
        executor = _executor()
        async def fake_look(args):
            return {"seen": True}
        executor.register("capture_webcam", fake_look, {"name": "capture_webcam", "parameters": {}})
        _front()
        stub, allow = execute_code_mod.derive_script_tool_sets(executor)
        assert stub <= guest_allowed_tools()
        assert "capture_webcam" in stub
        assert RECALL_GUEST_MEMORY_TOOL_NAME in stub
        assert "write_file" not in stub and "read_file" not in stub
        # While a guest fronts, the RPC boundary defers to the executor's
        # per-call policy so refusals carry the interactive audit shape.
        assert "write_file" in allow
        assert "execute_code" not in allow

    async def test_generated_module_hides_non_stub_tools(self):
        executor = _executor()
        result = await _run(
            executor,
            "import halbert_tools\n"
            "print(hasattr(halbert_tools, 'recall_memory'), "
            "hasattr(halbert_tools, 'write_file'))\n",
        )
        assert result.result["stdout"].strip() == "True False"


class TestGuestFloor:

    async def test_execute_code_is_off_for_the_guest_persona(self):
        """The gate pin: execute_code is not in GUEST_ALLOWED_TOOLS, so it is
        absent from the schemas a fronting guest is offered and refused by
        the executor if named anyway."""
        from halbert_core.persona.guest_tools import GUEST_DENIED_TOOLS

        executor = _executor()
        _front()
        assert "execute_code" not in GUEST_ALLOWED_TOOLS
        assert "execute_code" in GUEST_DENIED_TOOLS
        offered = {s["function"]["name"] for s in executor.get_schemas()}
        assert "execute_code" not in offered
        result = await executor.execute("execute_code", {"script": "pass"})
        assert result.success is False
        assert "not available while" in result.error

    async def test_guest_script_write_plane_refusal_is_audited_like_interactive(self):
        audits = []
        executor = _executor(audits)
        _front()

        # The interactive refusal, for shape comparison.
        interactive = await executor.execute(
            "write_file", {"path": "/tmp/nope", "content": "x"}, session_id="s1")
        assert interactive.success is False

        # The handler is driven directly: the outer execute() would (correctly)
        # refuse execute_code itself while a guest fronts; this test proves the
        # layers *inside* the run hold the floor without the outer gate. The
        # session id rides the ContextVar exactly as it does in production.
        from halbert_core.streaming.terminal_bridge import current_agent_session

        handler = executor.tools["execute_code"]
        token = current_agent_session.set("s1")
        try:
            result = await handler({
                "script": (
                    "import halbert_tools\n"
                    "r = halbert_tools._call('write_file', "
                    "{'path': '/tmp/nope', 'content': 'x'})\n"
                    "print(r['error'])\n"
                ),
            })
        finally:
            current_agent_session.reset(token)
        script_audits = [a for a in audits if a["tool"] == "write_file"]
        assert len(script_audits) == 2
        assert script_audits[0] == script_audits[1]  # same record shape
        for a in script_audits:
            assert a["success"] is False
            assert "not available while Marnie fronts" in a["error"]
        # And the script received the same refusal text the model would see.
        assert "not available while Marnie is fronting" in result["stdout"]

    async def test_guest_script_can_use_an_allowed_read_tool(self):
        executor = _executor()

        async def fake_look(args):
            return {"seen": True}

        executor.register("capture_webcam", fake_look, {"name": "capture_webcam", "parameters": {}})
        _front()
        handler = executor.tools["execute_code"]
        result = await handler({
            "script": (
                "import halbert_tools\n"
                "r = halbert_tools.capture_webcam()\n"
                "print(r['seen'])\n"
            ),
        })
        assert result["stdout"].strip() == "True"
        assert result["tool_calls_made"] == 1


# ---------------------------------------------------------------------------
# Write-plane deferral (behind the PACKET-02 lattice)
# ---------------------------------------------------------------------------

# The PACKET-02 lattice (persona/policy.py, persona/admission.py,
# persona/claims.py) is merged on this branch, so the deferral it gates is
# now asserted unconditionally: an owner script still cannot reach the
# write plane. If this test fails because the lattice is missing, that is
# a real regression — the skipif that used to guard it was retired when
# wave 1 merged the lattice in.
class TestWritePlaneStubsDeferredBehindLattice:
    """The per-call write-plane gate the lattice provides is what keeps
    write-plane stubs out of scripts; this class asserts it holds."""

    async def test_owner_script_cannot_reach_write_plane(self):
        executor = _executor()
        result = await _run(
            executor,
            "import halbert_tools\n"
            "r = halbert_tools._call('write_file', "
            "{'path': '/tmp/nope', 'content': 'x'})\n"
            "print(r['error'])\n",
        )
        assert result.success, result.error
        assert "not available in scripts" in result.result["stdout"]


# ---------------------------------------------------------------------------
# Stdout cap and spill
# ---------------------------------------------------------------------------

class TestStdoutCap:

    async def test_big_output_is_capped_with_head_and_tail(self):
        executor = _executor()
        result = await _run(executor, "print('X' * 300_000)\n")
        assert result.success, result.error
        out = result.result
        assert out["truncated"] is True
        head, tail = 50 * 1024, 50 * 1024
        assert out["stdout"].startswith("X" * 1024)
        assert out["stdout"].rstrip("\n").endswith("X" * 1024)
        assert len(out["stdout"]) < head + tail + 2048  # head+tail+marker only
        assert "read(offset=" in out["stdout"]
        # The spill file was written BEFORE the cap was applied: it holds the
        # full output, so the model recovers rather than reruns.
        assert out["spill_path"] and os.path.exists(out["spill_path"])
        assert os.path.getsize(out["spill_path"]) >= 300_000

    async def test_small_output_is_returned_whole_with_no_spill(self):
        executor = _executor()
        result = await _run(executor, "print('hello')\n")
        out = result.result
        assert out["truncated"] is False
        assert out["stdout"].strip() == "hello"
        assert out["spill_path"] is None


# ---------------------------------------------------------------------------
# Errors: structured, never raw stdout
# ---------------------------------------------------------------------------

class TestScriptAndToolErrors:

    async def test_tool_errors_surface_as_error_dicts_to_the_script(self):
        executor = _executor()

        async def boom(args):
            raise ValueError("ledger is on fire")

        executor.register("recall_memory", boom, {"name": "recall_memory", "parameters": {}})
        result = await _run(
            executor,
            "import halbert_tools\n"
            "r = halbert_tools.recall_memory(query='x')\n"
            "print('error' in r, r['error'])\n",
        )
        assert result.success, result.error
        assert "ledger is on fire" in result.result["stdout"]

    async def test_unhandled_script_exception_keeps_its_partial_stdout(self):
        """R-07 (A04-G6, FD-17): this used to assert ``"stdout" not in
        out`` -- "never raw stdout on failure". A script that printed for
        two minutes and then raised returned nothing at all, which is the
        least useful moment to discard the output. The error stays its
        own structured field, so nothing has to guess which half is
        which, and the stdout goes through the shared redaction core on
        the way out (A04-G4)."""
        executor = _executor()
        result = await _run(
            executor,
            "print('partial output someone will want')\n"
            "raise RuntimeError('the script went wrong')\n",
        )
        out = result.result
        assert "error" in out
        assert "the script went wrong" in out["error"]
        assert "Traceback" in out["traceback_tail"]
        assert "RuntimeError" in out["traceback_tail"]
        assert "partial output someone will want" in out["stdout"]
        assert out["tool_calls_made"] == 0


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

class TestBudget:

    async def test_default_budget_is_enforced_across_the_whole_script(self):
        executor = _executor()
        result = await _run(
            executor,
            "import halbert_tools\n"
            "ok = 0\n"
            "for i in range(30):\n"
            "    r = halbert_tools.recall_memory(query='q')\n"
            "    if 'error' not in r:\n"
            "        ok += 1\n"
            "print(ok)\n",
        )
        out = result.result
        assert out["stdout"].strip() == "25"
        assert out["tool_calls_made"] == 25
        assert out["budget_remaining"] == 0

    async def test_budget_override_is_honoured_and_capped(self):
        executor = _executor()
        result = await _run(
            executor,
            "import halbert_tools\n"
            "r = halbert_tools.recall_memory(query='q')\n"
            "print(r['query'])\n",
            max_tool_calls=2,
        )
        assert result.result["budget_remaining"] == 1
        result = await _run(
            executor, "pass\n", max_tool_calls=10_000,
        )
        assert result.result["budget_remaining"] == execute_code_mod.MAX_TOOL_CALL_BUDGET


# ---------------------------------------------------------------------------
# Re-entrancy: a script must not be able to start another script run
# ---------------------------------------------------------------------------

class TestReEntrancy:

    async def test_execute_code_is_not_callable_from_inside_a_script(self):
        executor = _executor()
        result = await _run(
            executor,
            "import halbert_tools\n"
            "r = halbert_tools._call('execute_code', {'script': 'pass'})\n"
            "print(r['error'])\n",
        )
        assert "not available in scripts" in result.result["stdout"]
        assert result.result["tool_calls_made"] == 0  # refused free, at the boundary


# ---------------------------------------------------------------------------
# Deterministic script-text gate (founder posture: deterministic-first)
# ---------------------------------------------------------------------------

class TestScriptTextGate:

    async def test_subprocess_import_is_refused(self):
        executor = _executor()
        result = await _run(
            executor,
            "import subprocess\n"
            "subprocess.run(['ls'])\n",
        )
        assert result.success is False
        assert "subprocess" in result.error
        assert "not part of the script contract" in result.error

    async def test_from_subprocess_import_is_refused(self):
        executor = _executor()
        result = await _run(executor, "from subprocess import run\nrun(['ls'])\n")
        assert result.success is False
        assert "subprocess" in result.error

    async def test_os_system_and_os_popen_are_refused(self):
        executor = _executor()
        for call in ("os.system('ls')", "os.popen('ls')"):
            result = await _run(executor, f"import os\n{call}\n")
            assert result.success is False, call
            assert "os.system" in result.error or "os.popen" in result.error, call

    async def test_dunder_import_of_subprocess_is_refused(self):
        executor = _executor()
        result = await _run(executor, "__import__('subprocess').run(['ls'])\n")
        assert result.success is False
        assert "subprocess" in result.error

    async def test_plain_os_use_is_fine(self):
        executor = _executor()
        result = await _run(
            executor,
            "import os\nprint(os.path.join('a', 'b'))\n",
        )
        assert result.success, result.error
        assert result.result["stdout"].strip() == "a/b"

    async def test_syntax_error_in_script_is_a_structured_error(self):
        """A script that does not parse is the script's failure, not the
        tool's: the run returns a structured error dict with the parse error."""
        executor = _executor()
        result = await _run(executor, "def broken(:\n")
        assert result.success is True
        assert "invalid syntax" in result.result["error"]
        assert "SyntaxError" in result.result["traceback_tail"]
        assert result.result["tool_calls_made"] == 0


# ---------------------------------------------------------------------------
# Inactivity-based timeout (not a flat wall clock)
# ---------------------------------------------------------------------------

class TestInactivityTimeout:

    async def test_a_silent_busy_loop_is_killed(self, monkeypatch):
        monkeypatch.setattr(execute_code_mod, "INACTIVITY_SECONDS", 0.5)
        executor = _executor()
        result = await _run(executor, "while True:\n    pass\n")
        out = result.result
        assert "error" in out
        assert "no tool call or output" in out["error"]

    async def test_ongoing_output_keeps_a_longer_run_alive(self, monkeypatch):
        monkeypatch.setattr(execute_code_mod, "INACTIVITY_SECONDS", 0.75)
        executor = _executor()
        result = await _run(
            executor,
            "import time\n"
            "for i in range(5):\n"
            "    print('tick')\n"
            "    time.sleep(0.3)\n",
        )
        assert result.success, result.error
        assert result.result["stdout"].count("tick") == 5


# ---------------------------------------------------------------------------
# Per-run sys.path / sys.modules hygiene
# ---------------------------------------------------------------------------

class TestRunHygiene:

    async def test_sys_path_and_modules_are_restored(self):
        executor = _executor()
        path_before = list(sys.path)
        assert "halbert_tools" not in sys.modules
        result = await _run(executor, "import halbert_tools\nprint('ok')\n")
        assert result.success, result.error
        assert sys.path == path_before, "a leaked sys.path entry is a failure, not a warning"
        assert "halbert_tools" not in sys.modules

    async def test_script_runs_as_main(self):
        """R-07 (A04-G5, FD-18): ``__name__`` was "__halbert_script__", so
        every ``if __name__ == "__main__":`` block a person pasted in
        silently did nothing -- which is the commonest shape of Python
        script there is. The marker stays available under its own name."""
        executor = _executor()
        result = await _run(executor, "print(__name__)\n")
        assert result.result["stdout"].strip() == "__main__"

    async def test_the_script_marker_is_still_available(self):
        executor = _executor()
        result = await _run(executor, "print(__halbert_script__)\n")
        assert result.result["stdout"].strip() == "True"

    async def test_stdout_of_the_run_is_restored_afterwards(self):
        executor = _executor()
        import io
        sentinel = io.StringIO()
        old, sys.stdout = sys.stdout, sentinel
        try:
            result = await _run(executor, "print('captured')\n")
        finally:
            sys.stdout = old
        assert result.result["stdout"].strip() == "captured"
        assert sentinel.getvalue() == ""  # nothing leaked to the real stdout