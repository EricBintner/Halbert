# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The audit log's hash chain, and what it can actually detect.

The chain used to restart at ``prev_hash = None`` in every new
``YYYY/MM/DD/<tool>.jsonl``, which means it could see an edit *inside* a
file and nothing else: deleting a file, or trimming records off the end of
one, left a log that still verified.  These tests are written around that
gap -- most of them tamper with the log and assert the tamper is *found*,
because a chain that cannot fail a bad log is decoration.

Integrity handoff §3.3 / §3.4.
"""
from __future__ import annotations

import json
import os

import pytest

from haloysius.integrity import verify as verify_signature

from halbert_core.obs.audit import (
    audit_log,
    set_audit_signer,
    verify_audit,
    write_audit,
)


@pytest.fixture(autouse=True)
def _isolated_audit_log(tmp_path, monkeypatch):
    """Every test gets its own log dir, and none of them signs by default."""
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
    set_audit_signer(None)
    yield
    set_audit_signer(None)


def _records(path):
    return [json.loads(line) for line in
            open(path, encoding="utf-8").read().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Continuity -- the fix itself.
# ---------------------------------------------------------------------------


def test_the_chain_continues_across_tool_boundaries():
    """The original bug: each tool's file started its own chain."""
    write_audit(tool="write_config", mode="apply", request_id="r1", ok=True)
    path = write_audit(tool="schedule_cron", mode="apply", request_id="r2", ok=True)

    first, second = _records(path)[-2:]

    assert second["prev_hash"] == first["hash"]


def test_the_chain_continues_across_day_boundaries(monkeypatch):
    """A new day used to mean a new directory and a fresh chain."""
    from haloysius.integrity import eventlog

    monkeypatch.setattr(eventlog.time, "time", lambda: 1_756_000_000.0)
    write_audit(tool="write_config", mode="apply", request_id="r1", ok=True)
    monkeypatch.setattr(eventlog.time, "time", lambda: 1_756_000_000.0 + 86_400)
    write_audit(tool="write_config", mode="apply", request_id="r2", ok=True)

    events = audit_log().read_all()

    assert len(events) == 2
    assert events[1].prev_hash == events[0].hash
    assert len({e.seq for e in events}) == 2


def test_records_land_in_one_shard_per_day_not_one_per_tool():
    write_audit(tool="write_config", mode="apply", request_id="r1", ok=True)
    write_audit(tool="schedule_cron", mode="apply", request_id="r2", ok=True)

    shards = sorted(audit_log().directory.glob("*.jsonl"))

    assert len(shards) == 1


# ---------------------------------------------------------------------------
# What write_audit still owes its callers.
# ---------------------------------------------------------------------------


def test_write_audit_returns_the_path_it_wrote():
    path = write_audit(tool="write_config", mode="apply", request_id="r1", ok=True)

    assert _records(path)


def test_the_audited_fields_survive_the_round_trip():
    write_audit(
        tool="write_config", mode="dry_run", request_id="r1", ok=False,
        summary="backup not found", path="/etc/hosts",
    )

    payload = audit_log().read_all()[-1].payload

    assert payload["tool"] == "write_config"
    assert payload["mode"] == "dry_run"
    assert payload["request_id"] == "r1"
    assert payload["ok"] is False
    assert payload["summary"] == "backup not found"
    assert payload["path"] == "/etc/hosts"


def test_a_float_valued_extra_does_not_break_the_log():
    """Canonicalization rejects floats; an audit call must not explode."""
    write_audit(
        tool="write_config", mode="apply", request_id="r1", ok=True,
        duration_seconds=1.5,
    )

    assert len(audit_log().read_all()) == 1


def test_write_audit_never_raises_into_its_caller(monkeypatch):
    """An audit write is a side effect of a tool call, not its purpose."""
    from halbert_core.obs import audit as audit_mod

    monkeypatch.setattr(audit_mod, "audit_log", lambda: (_ for _ in ()).throw(OSError("disk full")))

    assert write_audit(tool="t", mode="apply", request_id="r1", ok=True) == ""


# ---------------------------------------------------------------------------
# Detection -- §3.4's requirement, stated as failures we must catch.
# ---------------------------------------------------------------------------


def test_a_clean_log_verifies():
    for i in range(3):
        write_audit(tool="write_config", mode="apply", request_id=f"r{i}", ok=True)

    result = verify_audit()

    assert result.ok is True
    assert result.checked == 3
    assert result.signed == 0
    assert result.problems == []


def test_truncating_the_last_record_is_detected():
    """The old per-file chain passed this: a shorter chain is still a chain."""
    for i in range(3):
        path = write_audit(tool="write_config", mode="apply", request_id=f"r{i}", ok=True)
    lines = open(path, encoding="utf-8").read().splitlines()
    open(path, "w", encoding="utf-8").write("\n".join(lines[:-1]) + "\n")

    result = verify_audit()

    assert result.ok is False
    assert any(p.kind == "truncated" for p in result.problems)


def test_deleting_a_whole_shard_is_detected(monkeypatch):
    from haloysius.integrity import eventlog

    monkeypatch.setattr(eventlog.time, "time", lambda: 1_756_000_000.0)
    write_audit(tool="write_config", mode="apply", request_id="r1", ok=True)
    monkeypatch.setattr(eventlog.time, "time", lambda: 1_756_000_000.0 + 86_400)
    write_audit(tool="write_config", mode="apply", request_id="r2", ok=True)
    sorted(audit_log().directory.glob("*.jsonl"))[-1].unlink()

    result = verify_audit()

    assert result.ok is False
    assert any(p.kind == "truncated" for p in result.problems)


def test_editing_a_record_in_place_is_detected():
    path = write_audit(
        tool="write_config", mode="apply", request_id="r1", ok=False,
        summary="permission denied",
    )
    write_audit(tool="write_config", mode="apply", request_id="r2", ok=True)
    text = open(path, encoding="utf-8").read().replace(
        "permission denied", "completed cleanly"
    )
    open(path, "w", encoding="utf-8").write(text)

    result = verify_audit()

    assert result.ok is False
    assert any(p.kind == "commitment_mismatch" for p in result.problems)


def test_a_removed_middle_record_is_detected():
    for i in range(3):
        path = write_audit(tool="write_config", mode="apply", request_id=f"r{i}", ok=True)
    lines = open(path, encoding="utf-8").read().splitlines()
    open(path, "w", encoding="utf-8").write("\n".join([lines[0], lines[2]]) + "\n")

    result = verify_audit()

    assert result.ok is False
    assert {p.kind for p in result.problems} & {"chain_break", "sequence_gap"}


# ---------------------------------------------------------------------------
# Signing -- only after continuity works.
# ---------------------------------------------------------------------------


def test_records_are_signed_when_a_signer_is_registered(tmp_path):
    from halbert_core.crypto.storage import FileKeyStore, resolve_signer

    signer = resolve_signer(stores=[FileKeyStore(tmp_path / "keys")])
    set_audit_signer(signer)

    write_audit(tool="write_config", mode="apply", request_id="r1", ok=True)

    event = audit_log().read_all()[-1]
    assert event.author_did == signer.did
    assert verify_signature(
        event.author_did, event.signing_bytes(), bytes.fromhex(event.signature)
    )


def test_verify_counts_signed_records(tmp_path):
    from halbert_core.crypto.storage import FileKeyStore, resolve_signer

    set_audit_signer(resolve_signer(stores=[FileKeyStore(tmp_path / "keys")]))
    for i in range(2):
        write_audit(tool="write_config", mode="apply", request_id=f"r{i}", ok=True)

    result = verify_audit()

    assert result.ok is True
    assert result.signed == 2


def test_a_forged_record_signed_by_nobody_fails_verification(tmp_path):
    """Re-signing a tampered record needs the key, which is the point."""
    from halbert_core.crypto.storage import FileKeyStore, resolve_signer

    signer = resolve_signer(stores=[FileKeyStore(tmp_path / "keys")])
    set_audit_signer(signer)
    path = write_audit(tool="write_config", mode="apply", request_id="r1", ok=True)
    record = _records(path)[0]
    record["signature"] = "00" * 64
    open(path, "w", encoding="utf-8").write(json.dumps(record) + "\n")

    result = verify_audit()

    assert result.ok is False
    assert any(p.kind == "bad_signature" for p in result.problems)


def test_the_log_runs_unsigned_when_no_signer_is_registered():
    """§5: a body with no custody story still audits, and says so."""
    write_audit(tool="write_config", mode="apply", request_id="r1", ok=True)

    event = audit_log().read_all()[-1]
    assert event.author_did is None
    assert event.signature is None
    assert verify_audit().ok is True


# ---------------------------------------------------------------------------
# The core must still import without haloysius installed.
# ---------------------------------------------------------------------------


def test_write_audit_degrades_loudly_when_the_integrity_layer_is_absent(
    monkeypatch, caplog
):
    """halbert_core's core is meant to run without haloysius installed.

    It degrades to writing *nothing*, noisily, rather than falling back to
    a chain nobody can verify -- an audit log that only looks tamper-proof
    is the failure this whole change exists to remove.
    """
    import logging

    from halbert_core.obs import audit as audit_mod

    monkeypatch.setattr(audit_mod, "EventLog", None)

    with caplog.at_level(logging.ERROR):
        path = write_audit(tool="write_config", mode="apply", request_id="r1", ok=True)

    assert path == ""
    assert "haloysius" in caplog.text


def test_verify_audit_names_the_missing_dependency(monkeypatch):
    from halbert_core.obs import audit as audit_mod

    monkeypatch.setattr(audit_mod, "EventLog", None)

    with pytest.raises(audit_mod.AuditUnavailable) as excinfo:
        verify_audit()

    assert "haloysius" in str(excinfo.value)


def test_the_module_imports_with_no_haloysius_on_the_path():
    """Import-time, not call-time: tools/base.py imports this unconditionally."""
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        """
        import sys
        class Blocker:
            def find_module(self, name, path=None):
                if name == "haloysius" or name.startswith("haloysius."):
                    return self
            def load_module(self, name):
                raise ImportError("no haloysius here")
        sys.meta_path.insert(0, Blocker())
        for mod in [m for m in sys.modules if m.startswith("haloysius")]:
            del sys.modules[mod]
        import halbert_core.obs.audit as audit
        assert audit.EventLog is None
        print("imported")
        """
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)

    assert "imported" in result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Concurrency -- a false alarm is as bad as a missed one.
# ---------------------------------------------------------------------------


def test_concurrent_writes_do_not_forge_a_broken_chain():
    """Two tools finishing at once must not look like tampering.

    ``EventLog.append`` reads the head, writes a record, then writes the
    head back -- a read-modify-write with no lock.  Halbert runs tool calls
    concurrently (async handlers, the scheduler, guardrails), so without
    serialization two appends take the same seq and the same prev_hash, and
    ``audit-verify`` then reports tampering on a log nobody touched.  An
    audit check that cries wolf gets ignored, which is the same outcome as
    not having one.
    """
    import threading

    threads = [
        threading.Thread(
            target=write_audit,
            kwargs=dict(tool="t", mode="apply", request_id=f"r{i}", ok=True),
        )
        for i in range(24)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result = verify_audit()

    assert result.checked == 24
    assert result.ok is True, result.problems


def test_concurrent_writes_from_separate_processes_do_not_break_the_chain():
    """The lock has to be a file lock: the daemon and the CLI are not one process."""
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        f"""
        import os
        os.environ["HALBERT_LOG_DIR"] = {os.environ["HALBERT_LOG_DIR"]!r}
        from halbert_core.obs.audit import write_audit
        for i in range(8):
            write_audit(tool="t", mode="apply", request_id=str(i), ok=True)
        """
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        for _ in range(3)
    ]
    for p in procs:
        p.wait()

    result = verify_audit()

    assert result.checked == 24
    assert result.ok is True, result.problems


# ---------------------------------------------------------------------------
# Adversarial pass, 2026-09-02.
# ---------------------------------------------------------------------------


def test_write_audit_survives_a_value_whose_str_raises():
    """"Never raises" has to hold for the payload too, not just the append.

    ``tools/base.py`` calls write_audit on its *failure* path, so an audit
    call that raises converts a handled tool error into an unhandled crash.
    """
    class Hostile:
        def __str__(self):
            raise RuntimeError("boom")

        __repr__ = __str__

    path = write_audit(tool="t", mode="apply", request_id="r1", ok=True, thing=Hostile())

    assert path != "", "the record should survive one unrenderable field"
    assert "unrenderable" in audit_log().read_all()[-1].payload["thing"]


def test_a_hostile_value_does_not_lose_the_rest_of_the_record():
    """One bad extra must not cost the whole audit record."""
    class Hostile:
        def __str__(self):
            raise RuntimeError("boom")

        __repr__ = __str__

    write_audit(
        tool="write_config", mode="apply", request_id="r1", ok=True,
        path="/etc/hosts", thing=Hostile(),
    )

    payload = audit_log().read_all()[-1].payload
    assert payload["tool"] == "write_config"
    assert payload["path"] == "/etc/hosts"


def test_an_extra_cannot_forge_an_audited_field():
    """A caller must not be able to rewrite what the record says it is.

    ``ok``, ``tool`` and ``ts`` are the fields an audit log exists to state.
    A keyword argument that lands on top of one of them lets whatever
    produced that value -- a tool result, a model-supplied string -- decide
    what the log claims happened.
    """
    write_audit(
        tool="real_tool", mode="apply", request_id="r1", ok=False,
        ts="1999-01-01T00:00:00+00:00", tool_="x",
    )

    payload = audit_log().read_all()[-1].payload
    assert payload["tool"] == "real_tool"
    assert payload["ok"] is False
    assert payload["ts"] != "1999-01-01T00:00:00+00:00"
    assert payload["shadowed"]["ts"] == "1999-01-01T00:00:00+00:00"


def test_verifying_a_directory_that_does_not_exist_is_not_a_clean_result(tmp_path):
    """A typo in --dir must not read as "no tampering detected"."""
    missing = tmp_path / "definitely-not-here"

    with pytest.raises(audit_mod_error()):
        verify_audit(directory=missing)

    assert not missing.exists(), "verifying must not create the log it checks"


def audit_mod_error():
    from halbert_core.obs import audit as audit_mod

    return audit_mod.AuditUnavailable


def test_verifying_while_writing_does_not_report_tampering():
    """The reader side of the race the append lock only half-fixed.

    A record is appended and *then* the head is written. A verify landing
    between the two sees a log one record ahead of its head and calls it
    truncated. `halbert audit-verify` on a live machine would cry wolf.
    """
    import threading
    import time

    write_audit(tool="t", mode="apply", request_id="seed", ok=True)
    state = {"stop": False, "alarms": []}

    def writer():
        i = 0
        while not state["stop"]:
            write_audit(tool="t", mode="apply", request_id=f"w{i}", ok=True)
            i += 1

    def verifier():
        while not state["stop"]:
            result = verify_audit()
            if not result.ok:
                state["alarms"].append([p.kind for p in result.problems])

    threads = [threading.Thread(target=writer), threading.Thread(target=verifier)]
    for t in threads:
        t.start()
    time.sleep(2.0)
    state["stop"] = True
    for t in threads:
        t.join()

    assert state["alarms"] == [], f"{len(state['alarms'])} false tamper reports"


# ---------------------------------------------------------------------------
# Provenance -- reason/actor/digests are stated by the record, not by an extra.
# ---------------------------------------------------------------------------


def test_provenance_fields_round_trip():
    write_audit(
        tool="write_config", mode="apply", request_id="r1", ok=True,
        reason="user asked to raise the worker count",
        actor="user",
        before_sha256="a" * 64,
        after_sha256="b" * 64,
    )

    payload = audit_log().read_all()[-1].payload
    assert payload["reason"] == "user asked to raise the worker count"
    assert payload["actor"] == "user"
    assert payload["before_sha256"] == "a" * 64
    assert payload["after_sha256"] == "b" * 64


def test_a_stray_extra_cannot_overwrite_a_stated_provenance_field():
    """Another extra must not get to rewrite who changed something, or why."""
    write_audit(
        tool="write_config", mode="apply", request_id="r1", ok=True,
        reason="the real reason", actor="agent",
        detail="a tool result string", ts="1999-01-01T00:00:00+00:00",
    )

    payload = audit_log().read_all()[-1].payload
    assert payload["reason"] == "the real reason"
    assert payload["actor"] == "agent"
    assert payload["detail"] == "a tool result string"
    assert payload["shadowed"]["ts"] == "1999-01-01T00:00:00+00:00"


def test_naming_reason_twice_is_an_error_not_a_silent_pick():
    """Promotion to a named parameter turns a collision into a hard failure.

    While ``reason`` rode ``**extra`` a duplicate was resolved silently. Now
    Python refuses the call, which is the outcome we want for a field the
    record exists to state.
    """
    with pytest.raises(TypeError):
        write_audit(
            tool="write_config", mode="apply", request_id="r1", ok=True,
            reason="the real reason", **{"reason": "a nicer story"},
        )


def test_splatting_an_untrusted_dict_binds_its_reason_to_the_parameter():
    """The residual hazard, pinned so it stays visible.

    A named keyword-only parameter is bound by ``**result_dict`` just as an
    explicit keyword is, so a stray ``reason`` key inside a tool result
    would become the audit's provenance. Nothing in the signature can stop
    that -- binding happens before the body runs -- so the rule is a caller
    rule: never splat an unvetted dict into write_audit. This test exists so
    that anyone who changes the behaviour has to change the statement of it.
    """
    untrusted = {"reason": "whatever the tool happened to return"}
    write_audit(tool="probe", mode="read", request_id="r1", ok=True, **untrusted)

    payload = audit_log().read_all()[-1].payload
    assert payload["reason"] == "whatever the tool happened to return"
    assert "shadowed" not in payload


def test_provenance_is_absent_rather_than_null_when_not_stated():
    """An absent field says "not stated"; a null would look like an answer."""
    write_audit(tool="probe", mode="read", request_id="r1", ok=True)

    payload = audit_log().read_all()[-1].payload
    assert "reason" not in payload
    assert "actor" not in payload
    assert "before_sha256" not in payload


def test_request_id_joins_the_audit_record_to_the_ledger_row(tmp_path):
    """The join key across both planes -- never an event seq.

    A seq is not unique under a concurrent append, so a seq-keyed join can
    silently point at the wrong record.
    """
    from halbert_core.continuity.state_store import ACTOR_USER, StateStore

    store = StateStore(db_path=str(tmp_path / "state.db"))
    store.record_state(
        "config:/etc/nginx.conf", "worker_processes", "4", "write_config",
        reason="user asked to raise the worker count", actor=ACTOR_USER,
        request_id="req-7",
    )
    write_audit(
        tool="write_config", mode="apply", request_id="req-7", ok=True,
        reason="user asked to raise the worker count", actor=ACTOR_USER,
    )

    payload = audit_log().read_all()[-1].payload
    rows = store.by_request(payload["request_id"])
    assert len(rows) == 1
    assert rows[0].reason == payload["reason"]
    assert rows[0].actor == payload["actor"]
    store.close()
