# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-07: the script run always returns, and never runs under stale authority.

- **A04-G1 + bug 2** (fix-first row 12) -- the loop ran ``while not
  done.is_set()``, and the ten-second grace loop was only entered AFTER
  ``done`` was set. An ``except BaseException`` retry wrapper, an
  ``input()``, or an ``Event().wait()`` therefore made ``run_script``
  never return: the turn hung, holding the turn lock.
- **A04-G2** (row 11) -- ``host.dispatch_hook`` was never cleared, so a
  thread the script left behind could dispatch tools under the old
  session and role after the run returned.
- **A04-G3** (row 13) -- the spill file was unbounded and every byte
  written counted as activity, so ``while True: print('x'*4096)`` never
  timed out and filled the volume.
- **A04 bugs 1, 4, 6** (row 34) -- the AST gate missed ``from os import
  system`` and ``import os as o``; two overlapping runs corrupted each
  other's ``sys.stdout``/``sys.path``; and ``max_tool_calls=0`` became 25.
- **A04-G5 / G6 (FD-17, FD-18)** -- ``__name__`` was
  ``"__halbert_script__"``, so ``if __name__ == "__main__":`` never fired;
  and a raising script lost its partial stdout.
"""

import asyncio

import pytest

from halbert_core.tools.execute_code import (
    MAX_SPILL_BYTES,
    scan_script_text,
)


# ---------------------------------------------------------------------------
# A04 bug 1: the AST gate resolves aliases and ImportFrom names
# ---------------------------------------------------------------------------

def test_a_plain_subprocess_import_is_refused():
    assert scan_script_text("import subprocess")


def test_from_os_import_system_is_refused():
    assert scan_script_text("from os import system\nsystem('ls')")


def test_an_aliased_os_import_is_refused():
    assert scan_script_text("import os as o\no.system('ls')")


def test_an_aliased_subprocess_import_is_refused():
    assert scan_script_text("import subprocess as sp\nsp.run(['ls'])")


def test_from_subprocess_import_run_is_refused():
    assert scan_script_text("from subprocess import run")


def test_ordinary_script_text_is_clean():
    assert scan_script_text("import json\nprint(json.dumps({'a': 1}))") == []


def test_os_path_is_not_a_shell_out():
    assert scan_script_text("import os\nprint(os.path.join('a', 'b'))") == []


# ---------------------------------------------------------------------------
# A04-G3: the spill is bounded and output stops counting as activity
# ---------------------------------------------------------------------------

def test_the_spill_cap_is_bounded():
    assert MAX_SPILL_BYTES >= 1 << 20
    assert MAX_SPILL_BYTES <= 64 << 20


def test_output_past_the_cap_stops_counting_as_activity():
    from halbert_core.tools.execute_code import _OutputCapture

    activity = [0.0]
    capture = _OutputCapture(activity, None, max_spill=64)
    capture.write("a" * 32)
    first = activity[0]
    assert first > 0
    activity[0] = 0.0
    capture.write("b" * 200)          # past the cap
    capture.write("c" * 200)          # and again
    assert activity[0] == 0.0, "output past the cap must not keep a run alive"


def test_the_capture_reports_the_cap_was_hit():
    from halbert_core.tools.execute_code import _OutputCapture

    capture = _OutputCapture([0.0], None, max_spill=64)
    capture.write("x" * 500)
    assert capture.cap_exceeded is True


def test_an_under_cap_capture_reports_nothing():
    from halbert_core.tools.execute_code import _OutputCapture

    capture = _OutputCapture([0.0], None, max_spill=1024)
    capture.write("small")
    assert capture.cap_exceeded is False


# ---------------------------------------------------------------------------
# A04-G2: the host retires
# ---------------------------------------------------------------------------

def test_a_retired_host_refuses_a_late_dispatch():
    from halbert_core.tools.script_rpc_host import ScriptRpcHost

    host = ScriptRpcHost(allowed_tools={"read_file"}, budget=5)
    host.reveal_token_for_test = True
    token = host.issue_token()
    host.dispatch_hook = lambda name, args: {"ok": True}
    assert host.handle(token, "read_file", {"path": "/x"}) == {"ok": True}

    host.retire()
    late = host.handle(token, "read_file", {"path": "/x"})
    assert late.get("refusal") == "retired"
    assert "ok" not in late


def test_handle_never_raises_into_the_script():
    from halbert_core.tools.script_rpc_host import ScriptRpcHost

    host = ScriptRpcHost(allowed_tools={"read_file"}, budget=5)
    host.reveal_token_for_test = True
    token = host.issue_token()

    def _boom(name, args):
        raise RuntimeError("dispatch exploded")

    host.dispatch_hook = _boom
    out = host.handle(token, "read_file", {"path": "/x"})
    assert isinstance(out, dict)
    assert "error" in out


# ---------------------------------------------------------------------------
# A04 bug 6: a zero budget is zero
# ---------------------------------------------------------------------------

def test_a_zero_budget_dispatches_nothing():
    from halbert_core.tools.script_rpc_host import ScriptRpcHost

    host = ScriptRpcHost(allowed_tools={"read_file"}, budget=0)
    host.reveal_token_for_test = True
    token = host.issue_token()
    host.dispatch_hook = lambda name, args: {"ok": True}
    out = host.handle(token, "read_file", {"path": "/x"})
    assert "ok" not in out
    assert host.calls_dispatched == 0


def test_the_budget_argument_reads_zero_as_zero():
    from halbert_core.tools.execute_code import resolve_budget

    assert resolve_budget({"max_tool_calls": 0}) == 0
    assert resolve_budget({}) > 0
    assert resolve_budget({"max_tool_calls": None}) > 0


# ---------------------------------------------------------------------------
# A04-G5 / G6 under FD-17 and FD-18
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_script_runs_as_main():
    from halbert_core.tools.execute_code import run_script

    out = await run_script(_executor(), {
        "script": "print('main' if __name__ == '__main__' else 'not')",
    })
    assert "main" in out.get("stdout", "")


@pytest.mark.asyncio
async def test_the_script_marker_is_still_available():
    from halbert_core.tools.execute_code import run_script

    out = await run_script(_executor(), {
        "script": "print(__halbert_script__)",
    })
    assert "True" in out.get("stdout", "")


@pytest.mark.asyncio
async def test_a_raising_script_keeps_its_partial_stdout():
    from halbert_core.tools.execute_code import run_script

    out = await run_script(_executor(), {
        "script": "print('got this far')\nraise ValueError('nope')",
    })
    assert "got this far" in out.get("stdout", "")
    assert "ValueError" in out.get("error", "")


@pytest.mark.asyncio
async def test_stderr_is_captured():
    from halbert_core.tools.execute_code import run_script

    out = await run_script(_executor(), {
        "script": "import sys\nsys.stderr.write('warned\\n')",
    })
    assert "warned" in out.get("stderr", "")


# ---------------------------------------------------------------------------
# A04-G1 + bug 2: the run always returns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_wedged_script_still_returns():
    """The reproduction: a BaseException retry wrapper swallows every
    interrupt injection, so ``done`` is never set."""
    import halbert_core.tools.execute_code as ec

    out = await asyncio.wait_for(
        ec.run_script(_executor(), {
            "script": (
                "import time\n"
                "while True:\n"
                "    try:\n"
                "        time.sleep(0.01)\n"
                "    except BaseException:\n"
                "        pass\n"
            ),
        }, inactivity_seconds=0.3, grace_seconds=0.5),
        timeout=20,
    )
    assert "error" in out
    assert "stopped" in out["error"] or "abandoned" in out["error"]


def _executor():
    from halbert_core.tools import ToolExecutor, ToolSafetyFramework

    return ToolExecutor(safety=ToolSafetyFramework())


# ---------------------------------------------------------------------------
# A04-G7: the schema names what a script can actually call
# ---------------------------------------------------------------------------

def test_the_schema_names_the_available_stubs():
    """A model writing a script had to guess which functions exist, and a
    guess that misses fails at import with a NameError it then debugs
    from a traceback tail."""
    from halbert_core.tools.execute_code import TOOL_NAME, register_execute_code

    executor = _executor()
    register_execute_code(executor)
    description = executor.schemas[TOOL_NAME]["description"]
    assert "Available in halbert_tools:" in description


def test_the_schema_says_scripts_run_as_main():
    from halbert_core.tools.execute_code import TOOL_NAME, register_execute_code

    executor = _executor()
    register_execute_code(executor)
    script_desc = executor.schemas[TOOL_NAME]["parameters"]["properties"]["script"]
    assert "__main__" in script_desc["description"]


def test_the_module_schema_constant_is_not_mutated():
    """The per-executor list must not leak into the module constant --
    two executors with different stub sets would then describe each
    other's."""
    from halbert_core.tools.execute_code import (
        EXECUTE_CODE_SCHEMA, register_execute_code,
    )

    before = EXECUTE_CODE_SCHEMA["description"]
    register_execute_code(_executor())
    assert EXECUTE_CODE_SCHEMA["description"] == before
