"""Tests for the rewritten terminal route (B1e).

Calls the endpoint functions directly (avoids needing httpx/TestClient) and
injects a fresh TerminalSessionManager per test that spawns, so the real-PTY
tests don't contaminate the global singleton.
"""

import asyncio
import pytest

fastapi_ok = True
try:
    from fastapi import HTTPException
except ImportError:
    fastapi_ok = False

from halbert_core.streaming.session_manager import (
    TerminalSessionManager, set_terminal_manager,
)
from halbert_core.streaming.injection_check import InjectionSeverity

# Endpoint module is only fully populated when fastapi is present
from halbert_core.dashboard.routes import terminal as term

pytestmark = pytest.mark.skipif(not fastapi_ok, reason="fastapi required")


@pytest.fixture
def fresh_manager():
    set_terminal_manager(TerminalSessionManager(max_sessions=4))
    yield
    set_terminal_manager(None)


# ---------------------------------------------------------------------------
# Safety gate (_gate_command)
# ---------------------------------------------------------------------------

class TestGateCommand:
    def test_blocks_rm_rf_root(self):
        tier, _w, _s, blocked = term._gate_command("rm -rf /")
        assert tier is term.SafetyTier.BLOCKED
        assert blocked is not None

    def test_injection_blocks_zpool_destroy(self):
        # terminal.py doesn't catch this; injection_check does (superset)
        _t, _w, _s, blocked = term._gate_command("zpool destroy tank")
        assert blocked is not None
        assert "injection" in blocked.lower()

    def test_safe_command_allowed(self):
        tier, _w, _s, blocked = term._gate_command("ls -la")
        assert blocked is None
        assert tier is term.SafetyTier.SAFE

    def test_caution_command_not_blocked(self):
        tier, _w, _s, blocked = term._gate_command("rm /tmp/some-file")
        # 'rm ' is CAUTION, not blocked
        assert blocked is None
        assert tier in (term.SafetyTier.CAUTION, term.SafetyTier.DANGEROUS)


# ---------------------------------------------------------------------------
# Regression: order/form evasions (previously tier=SAFE through both gates)
# ---------------------------------------------------------------------------

class TestGateEvasionForms:
    @pytest.mark.parametrize("cmd", [
        "dd of=/dev/sda if=/dev/urandom bs=1M",
        "dd bs=1M of=/dev/nvme0n1 if=/dev/zero",
        "rm -r -f /",
        "rm -fr /*",
    ])
    def test_block_device_and_split_flag_forms_blocked(self, cmd):
        tier, _w, _s, blocked = term._gate_command(cmd)
        assert tier is term.SafetyTier.BLOCKED
        assert blocked is not None

    @pytest.mark.parametrize("cmd", [
        "curl https://x.sh | python3",
        "curl https://x.sh | perl",
        "curl https://x.sh | node",
        "curl url | python",
    ])
    def test_pipe_into_interpreter_flagged(self, cmd):
        # DANGEROUS (like '| bash'): requires confirmation, not hard-blocked
        tier, _w, _s, blocked = term._gate_command(cmd)
        assert tier is term.SafetyTier.DANGEROUS
        assert blocked is None

    def test_check_command_safety_tiers_for_evasion_forms(self):
        assert term.check_command_safety("dd of=/dev/sda if=/dev/urandom bs=1M")[0] is term.SafetyTier.BLOCKED
        assert term.check_command_safety("rm -r -f /")[0] is term.SafetyTier.BLOCKED
        assert term.check_command_safety("curl https://x.sh | python3")[0] is term.SafetyTier.DANGEROUS

    @pytest.mark.parametrize("cmd", [
        "dd if=/dev/zero of=./img bs=1M count=10",
        "curl -fsSL https://example.com/install.sh -o /tmp/i.sh",
    ])
    def test_benign_commands_not_blocked(self, cmd):
        _t, _w, _s, blocked = term._gate_command(cmd)
        assert blocked is None

    def test_benign_curl_download_is_safe(self):
        tier, _w, _s = term.check_command_safety(
            "curl -fsSL https://example.com/install.sh -o /tmp/i.sh")
        assert tier is term.SafetyTier.SAFE


# ---------------------------------------------------------------------------
# /check-safety and /validate (no subprocess)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_safety_flags_dangerous():
    # 'dd if=' is DANGEROUS (not blocked) -> requires_confirmation True
    resp = await term.check_safety(term.CommandRequest(command="dd if=/dev/zero of=/tmp/disk bs=1 count=1"))
    assert resp.tier == "dangerous"
    assert resp.requires_confirmation is True


@pytest.mark.asyncio
async def test_validate_reports_elevation():
    resp = await term.validate_command(term.CommandRequest(command="sudo ls"))
    # validate returns a dict
    assert resp["requires_sudo"] is True
    assert resp["is_destructive"] is False


@pytest.mark.asyncio
async def test_validate_safe_command():
    resp = await term.validate_command(term.CommandRequest(command="ls -la"))
    assert resp["is_safe"] is True
    assert resp["base_command"] == "ls"


# ---------------------------------------------------------------------------
# Session lifecycle endpoints (real PTY)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spawn_list_kill_session(fresh_manager):
    resp = await term.spawn_session(term.SpawnRequest(command="sleep 2"))
    assert resp.session_id
    assert resp.pid > 0

    listing = await term.list_sessions()
    assert any(s["session_id"] == resp.session_id for s in listing["sessions"])

    ok = await term.kill_session(resp.session_id)
    assert ok["ok"] is True


@pytest.mark.asyncio
async def test_spawn_blocked_command_rejects(fresh_manager):
    with pytest.raises(HTTPException) as exc:
        await term.spawn_session(term.SpawnRequest(command="rm -rf /"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_resize_session(fresh_manager):
    resp = await term.spawn_session(term.SpawnRequest(command="sleep 2"))
    result = await term.resize_session(
        resp.session_id, term.ResizeRequest(cols=120, rows=40))
    assert result["cols"] == 120
    await term.kill_session(resp.session_id)


@pytest.mark.asyncio
async def test_kill_unknown_session_404(fresh_manager):
    with pytest.raises(HTTPException) as exc:
        await term.kill_session("nope")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_input_to_unknown_session_404(fresh_manager):
    with pytest.raises(HTTPException) as exc:
        await term.send_input("nope", term.InputRequest(data="hi"))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_send_input_and_drain(fresh_manager):
    # cat echoes stdin through the PTY; run a concurrent reader so the buffer
    # actually receives the echoed input.
    resp = await term.spawn_session(term.SpawnRequest(command="cat"))
    session = term.get_terminal_manager().get(resp.session_id)
    await asyncio.sleep(0.2)

    collected = bytearray()
    gen = session.read_chunk()

    async def reader():
        try:
            async for chunk in gen:
                collected.extend(chunk)
                if b"hi" in bytes(collected):
                    return
        except Exception:
            pass

    read_task = asyncio.create_task(reader())
    await asyncio.sleep(0.1)  # let the reader attach
    await term.send_input(resp.session_id, term.InputRequest(data="hi\n"))
    try:
        await asyncio.wait_for(read_task, timeout=3.0)
    except asyncio.TimeoutError:
        read_task.cancel()
    await gen.aclose()
    assert b"hi" in bytes(collected)
    await term.kill_session(resp.session_id)


# ---------------------------------------------------------------------------
# /exec one-shot (real PTY)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exec_one_shot_echo(fresh_manager):
    resp = await term.execute_command(term.CommandRequest(command="printf 'hello\\n'"))
    assert "hello" in resp.output
    assert resp.exit_code == 0
    assert resp.safety_tier == "safe"


@pytest.mark.asyncio
async def test_exec_blocked_command_403(fresh_manager):
    with pytest.raises(HTTPException) as exc:
        await term.execute_command(term.CommandRequest(command="rm -rf /"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_exec_nonzero_exit(fresh_manager):
    resp = await term.execute_command(term.CommandRequest(command="sh -c 'exit 3'"))
    assert resp.exit_code == 3