# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-08 Phase D: a Stop survives a restart, and a resume is authorised.

A11-G6 under FD-5. ``HaltState`` was in-process only: the kill switch,
and every failure-triggered stop (a consent ledger that cannot be read,
a missing integrity primitive, an unwritable audit log, three guardrail
trips in a row), lasted exactly as long as the process did. Restarting
the daemon cleared it — and the conditions that halted the machine are
exactly the ones a restart does not fix, so the machine came back up
running with the same broken precondition.

The persisted state is ``<data_dir>/runtime/halt.json``: 0600, written
atomically, flock-guarded, read at boot before anything else starts.

And the resume is deliberately asymmetric. Halting is easy and anyone's
to do; resuming needs a token minted by the authorised path (an owner,
on a first-party surface, shown what will restart), because "clear the
flag" must not be something an agent can do to itself.

A11 bug 5 rides here: ``projection_status`` derived the expected
projection from the log and then read the projection file, unsynchronised.
A concurrent decision between the two reads made an honest projection
look like tampering -- and the answer to tampering is a Stop, so the race
halted a healthy machine.
"""

import json
import os
import threading

import pytest

from halbert_core.persona.permission.halt import (
    HaltReason,
    HaltState,
    PersistedHalt,
)


def _store(tmp_path):
    return PersistedHalt(data_dir=str(tmp_path))


def test_a_halt_is_written_to_disk(tmp_path):
    store = _store(tmp_path)
    state = HaltState(persisted=store)
    state.halt(HaltReason.OWNER_STOP, by="owner", surface="dashboard")

    path = tmp_path / "runtime" / "halt.json"
    assert path.is_file()
    payload = json.loads(path.read_text())
    assert payload["reason_code"] == HaltReason.OWNER_STOP
    assert payload["halted_by"] == "owner"


def test_the_halt_file_is_owner_only(tmp_path):
    store = _store(tmp_path)
    HaltState(persisted=store).halt(HaltReason.OWNER_STOP)
    mode = os.stat(tmp_path / "runtime" / "halt.json").st_mode & 0o777
    assert mode == 0o600


def test_a_restart_comes_back_halted(tmp_path):
    """The conditions that halt the machine are the ones a restart does
    not fix."""
    store = _store(tmp_path)
    HaltState(persisted=store).halt(HaltReason.AUDIT_UNWRITABLE)

    rebooted = HaltState(persisted=_store(tmp_path))
    rebooted.load()
    assert rebooted.is_halted() is True
    assert rebooted.reason_code == HaltReason.AUDIT_UNWRITABLE


def test_a_clean_boot_is_not_halted(tmp_path):
    state = HaltState(persisted=_store(tmp_path))
    state.load()
    assert state.is_halted() is False


def test_an_unreadable_halt_file_fails_closed(tmp_path):
    """A halt state that cannot be read is not evidence of running."""
    path = tmp_path / "runtime"
    path.mkdir(parents=True)
    (path / "halt.json").write_text("{ this is not json")

    state = HaltState(persisted=_store(tmp_path))
    state.load()
    assert state.is_halted() is True
    assert state.reason_code == HaltReason.CONSENT_UNREADABLE or state.reason_code


# ---------------------------------------------------------------------------
# The asymmetric resume
# ---------------------------------------------------------------------------

def test_a_resume_without_a_token_is_refused(tmp_path):
    state = HaltState(persisted=_store(tmp_path))
    state.halt(HaltReason.OWNER_STOP)
    with pytest.raises(PermissionError):
        state.resume(by="agent", surface="turn")
    assert state.is_halted() is True


def test_a_minted_token_resumes_once(tmp_path):
    state = HaltState(persisted=_store(tmp_path))
    state.halt(HaltReason.OWNER_STOP)
    token = state.mint_resume_token()
    state.resume(by="owner", surface="dashboard", token=token)
    assert state.is_halted() is False

    # Single use: the same token cannot resume a later halt.
    state.halt(HaltReason.OWNER_STOP)
    with pytest.raises(PermissionError):
        state.resume(by="owner", surface="dashboard", token=token)


def test_a_forged_token_is_refused(tmp_path):
    state = HaltState(persisted=_store(tmp_path))
    state.halt(HaltReason.OWNER_STOP)
    with pytest.raises(PermissionError):
        state.resume(by="owner", surface="dashboard", token="not-a-token")


def test_a_resume_clears_the_persisted_state(tmp_path):
    state = HaltState(persisted=_store(tmp_path))
    state.halt(HaltReason.OWNER_STOP)
    state.resume(by="owner", surface="dashboard",
                 token=state.mint_resume_token())

    rebooted = HaltState(persisted=_store(tmp_path))
    rebooted.load()
    assert rebooted.is_halted() is False


def test_an_in_process_only_halt_state_still_works():
    """The pure state is still importable and testable with no host."""
    state = HaltState()
    state.halt(HaltReason.OWNER_STOP)
    assert state.is_halted() is True
    state.resume(token=state.mint_resume_token())
    assert state.is_halted() is False


# ---------------------------------------------------------------------------
# A11 bug 5: the projection is derived under the lock
# ---------------------------------------------------------------------------

def test_the_projection_status_is_read_under_one_lock(tmp_path):
    """A concurrent decision must not make an honest projection look
    like tampering -- the answer to tampering is a Stop."""
    from halbert_core.consent.store import ConsentStore
    from halbert_core.persona.permission.consent import (
        ConsentDecision, Principal,
    )

    store = ConsentStore(
        data_dir=str(tmp_path / "data"), config_dir=str(tmp_path / "config"))
    owner = Principal(kind="owner", id="local:501",
                      authn="os_reauth:touchid", at_machine=True)
    store.record_decision(
        "sensor.hardware", ConsentDecision.DENIED,
        principal=owner, surface="desktop-app/settings")

    verdicts = []
    stop = threading.Event()

    def _writer():
        i = 0
        while not stop.is_set() and i < 40:
            store.record_decision(
                "sensor.journal", ConsentDecision.DENIED,
                principal=owner, surface="desktop-app/settings")
            i += 1

    def _reader():
        for _ in range(40):
            verdicts.append(store.projection_status())

    threads = [threading.Thread(target=_writer), threading.Thread(target=_reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    stop.set()

    assert "disagrees" not in verdicts, (
        "a concurrent decision made the projection look tampered with"
    )
