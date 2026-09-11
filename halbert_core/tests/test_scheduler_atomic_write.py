# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Scheduler per-job JSON writes go through temp-file + atomic rename.

A torn per-job JSON (the interpreter dying mid-``json.dump``) previously
read back as an empty/missing job: ``_load_jobs`` swallowed the
``JSONDecodeError`` and the job silently vanished from the queue. The
write is now staged to a sibling temp file and ``os.replace``d over the
record, so a reader sees either the whole old state or the whole new one
-- never a half-written file.
"""

import json
import os

import pytest

from halbert_core.scheduler.engine import SchedulerEngine
from halbert_core.scheduler.job import Job


@pytest.fixture
def engine(tmp_path):
    e = SchedulerEngine(persist_dir=str(tmp_path))
    yield e


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_persist_leaves_no_temp_files(engine):
    engine.add_job(Job(id="j1", task="t", schedule="* * * * *"))
    names = [n for n in os.listdir(engine.persist_dir) if n.endswith(".json")]
    assert names == ["j1.json"]
    assert _read(os.path.join(engine.persist_dir, "j1.json"))["id"] == "j1"


def test_mid_dump_failure_leaves_previous_record_intact(engine, monkeypatch):
    engine.add_job(Job(id="j2", task="t", schedule="* * * * *"))
    path = engine._job_path("j2")
    before = _read(path)

    real_dump = json.dump

    def exploding_dump(obj, fh, **kw):
        fh.write('{"id": "j2", "task": "half-wr')
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(json, "dump", exploding_dump)
    with pytest.raises(RuntimeError):
        engine.update_job_state("j2", "running")
    monkeypatch.setattr(json, "dump", real_dump)

    # The on-disk record is the previous whole state, not the partial one.
    assert _read(path)["state"] == "pending"


def test_load_ignores_temp_files(tmp_path):
    leftover = tmp_path / ".j3.json.tmp"
    leftover.write_text('{"id": "j3", "task": "residue"', encoding="utf-8")
    engine = SchedulerEngine(persist_dir=str(tmp_path))
    assert "j3" not in engine.jobs


class TestAddJobPreservesLastRunFacts:
    """R-03 own-bug 1: add_job replaced the whole record, so re-registering
    the same job id at every boot (jobs are re-registered at every boot,
    C4-01) blanked started_at/completed_at/state -- a boot catch-up decision
    made right after registration reads the correct prior facts (captured
    before registration runs), but the FILE itself is now blanked, so a
    SECOND reboot before the next real fire sees no last-run facts at all
    and re-serves an already-served slot."""

    def test_reregistering_the_same_id_keeps_the_last_run_facts(self, engine):
        engine.add_job(Job(id="morning_report", task="t", schedule="cron"))
        engine.update_job_state("morning_report", "completed")
        completed_at = engine.get_job("morning_report").completed_at
        assert completed_at

        # Boot: the job is re-registered with a fresh Job() (registration's
        # own shape -- state='pending', no timestamps).
        engine.add_job(Job(id="morning_report", task="t", schedule="cron"))

        reregistered = engine.get_job("morning_report")
        assert reregistered.state == "completed"
        assert reregistered.completed_at == completed_at

    def test_the_preserved_facts_survive_a_reload_from_disk(self, engine, tmp_path):
        engine.add_job(Job(id="morning_report", task="t", schedule="cron"))
        engine.update_job_state("morning_report", "completed")
        completed_at = engine.get_job("morning_report").completed_at
        engine.add_job(Job(id="morning_report", task="t", schedule="cron"))

        reloaded = SchedulerEngine(persist_dir=str(tmp_path))
        assert reloaded.get_job("morning_report").completed_at == completed_at

    def test_a_genuinely_new_id_is_unaffected(self, engine):
        engine.add_job(Job(id="brand_new", task="t", schedule="cron"))
        job = engine.get_job("brand_new")
        assert job.state == "pending"
        assert job.completed_at is None