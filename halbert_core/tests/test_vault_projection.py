# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""LEDGER-1 step 8: the vault is a projection with no authority (MEM-03).

Both acceptance tests pass trivially on an empty vault — delete nothing,
rebuild nothing, compare two empty trees, green. So every test here first
asserts that specific notes exist. That is the "beautiful empty vault" the
build order warns about.
"""

import hashlib
import shutil

import pytest

from halbert_core.continuity.provenance import record_file_change
from halbert_core.continuity.state_store import (
    ACTOR_AGENT,
    ACTOR_SYSTEM,
    ACTOR_USER,
    UNRECORDED,
    StateStore,
    default_state_db_path,
)
from halbert_core.continuity.vault import VaultProjector, vault_root
from halbert_core.obs.audit import set_audit_signer


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("HALBERT_PERSONA_ID", "testpersona")
    set_audit_signer(None)
    yield
    set_audit_signer(None)


def _store():
    return StateStore(db_path=str(default_state_db_path()))


def _seed(n=3):
    """Notes across every admitted category, plus rows the gate must reject."""
    for i in range(n):
        record_file_change(
            path=f"/etc/app{i}.conf", reason=f"the admin asked for change {i}",
            actor=ACTOR_USER, request_id=f"req-{i}", tool="editor",
            after_text=f"setting = {i}\n",
        )
    s = _store()
    s.record_state("file:/etc/keys/id_rsa", "mode_octal", "600", "chmod",
                   reason="permissions hygiene", actor=ACTOR_USER, request_id="req-m")
    s.record_state("domain:samba", "preferred_entity", "smb.conf", "consolidation",
                   reason="consolidation: seen in 4 of 6 samba threads",
                   actor=ACTOR_SYSTEM, request_id="req-c")
    # rejected by the gate: re-derivable, and churns every consolidation run
    s.record_state("service:nginx", "service_status", "running", "tracker",
                   reason="tracker: sweep", actor=ACTOR_SYSTEM)
    s.record_state("domain:samba", "thread_count", "6", "consolidation",
                   reason="consolidation: count", actor=ACTOR_SYSTEM)
    s.close()


def _snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


class TestRebuildIsByteIdentical:
    def test_delete_the_directory_and_rebuild(self):
        _seed()
        first = VaultProjector().rebuild()
        assert first.written >= 5, "nothing was projected; the test proves nothing"
        before = _snapshot(vault_root())
        assert any("app0" in k for k in before), "expected a named note"

        shutil.rmtree(vault_root())
        VaultProjector().rebuild()

        assert _snapshot(vault_root()) == before

    def test_a_second_rebuild_in_place_rewrites_nothing(self):
        _seed()
        VaultProjector().rebuild()
        mtimes = {p: p.stat().st_mtime_ns
                  for p in vault_root().rglob("*.md")}

        second = VaultProjector().rebuild()

        assert second.written == 0 and second.unchanged >= 5
        assert {p: p.stat().st_mtime_ns for p in vault_root().rglob("*.md")} == mtimes

    def test_no_wall_clock_value_reaches_a_note(self):
        """A composite score's freshness term reads time.time() and drifts
        every few minutes, so it would break byte-identity."""
        _seed()
        VaultProjector().rebuild()
        for note in vault_root().rglob("*.md"):
            assert "composite" not in note.read_text(encoding="utf-8")

    def test_timestamps_are_utc_at_fixed_precision(self):
        _seed(1)
        VaultProjector().rebuild()
        text = next(vault_root().joinpath("notes").glob("*.md")).read_text()
        assert "valid_from: '20" in text and "Z'" in text


class TestReconcileNotJustWrite:
    def test_a_rebuild_in_place_unlinks_orphans(self):
        """The delete-then-rebuild test cannot catch this: a projector that
        only writes leaves a forgotten fact's note on disk forever."""
        _seed()
        VaultProjector().rebuild()
        notes = sorted(p.name for p in (vault_root() / "notes").glob("*.md"))
        assert len(notes) >= 5

        s = _store()
        s._conn.execute("DELETE FROM state_triples WHERE subject = 'file:/etc/app0.conf'")
        s._conn.commit()
        s.close()

        result = VaultProjector().rebuild()   # in place, no rmtree
        assert result.unlinked == 1
        assert not any("app0" in p.name for p in (vault_root() / "notes").glob("*.md"))


class TestForgetting:
    def test_forget_removes_the_words_and_a_rebuild_never_brings_them_back(self):
        record_file_change(path="/etc/private.conf",
                           reason="because I am hiding it from my flatmate",
                           actor=ACTOR_USER, request_id="req-9", tool="editor",
                           after_text="x\n")
        VaultProjector().rebuild()
        assert any("flatmate" in p.read_text() for p in vault_root().rglob("*.md"))

        VaultProjector().forget("req-9")
        assert not any("flatmate" in p.read_text() for p in vault_root().rglob("*.md"))

        VaultProjector().rebuild()
        assert not any("flatmate" in p.read_text() for p in vault_root().rglob("*.md"))

    def test_the_fact_and_its_timeline_survive_the_forgetting(self):
        """What was true and when is not the thing being forgotten."""
        record_file_change(path="/etc/private.conf", reason="a private reason",
                           actor=ACTOR_USER, request_id="req-9", tool="editor",
                           after_text="x\n")
        VaultProjector().forget("req-9")

        notes = list((vault_root() / "notes").glob("*private*"))
        assert len(notes) == 1
        text = notes[0].read_text()
        assert "no reason was recorded" in text

    def test_forgetting_one_request_leaves_another_untouched(self):
        record_file_change(path="/etc/a.conf", reason="keep this one",
                           actor=ACTOR_USER, request_id="req-1", tool="editor",
                           after_text="a\n")
        record_file_change(path="/etc/b.conf", reason="forget this one",
                           actor=ACTOR_USER, request_id="req-2", tool="editor",
                           after_text="b\n")
        VaultProjector().forget("req-2")

        blob = "".join(p.read_text() for p in vault_root().rglob("*.md"))
        assert "keep this one" in blob
        assert "forget this one" not in blob


class TestTheAdmissionGate:
    @pytest.mark.parametrize("predicate", ["service_status", "disk_health",
                                           "cpu_load", "admin_presence"])
    def test_re_observable_facts_are_never_projected(self, predicate):
        """§4d: if a command re-derives it in under a second, store the
        command, not the answer."""
        s = _store()
        s.record_state(f"service:x", predicate, "v", "tracker",
                       reason="tracker: sweep", actor=ACTOR_SYSTEM)
        s.close()
        result = VaultProjector().rebuild()
        assert result.written == 0 and result.rejected >= 1

    def test_thread_count_is_rejected(self):
        """Re-derivable, and it churns a new value every consolidation run."""
        s = _store()
        s.record_state("domain:x", "thread_count", "6", "consolidation",
                       reason="consolidation: count", actor=ACTOR_SYSTEM)
        s.close()
        assert VaultProjector().rebuild().written == 0

    def test_an_unknown_predicate_defaults_to_rejected(self):
        s = _store()
        s.record_state("file:/etc/x", "something_new", "v", "t",
                       reason="r", actor=ACTOR_SYSTEM)
        s.close()
        assert VaultProjector().rebuild().written == 0

    def test_every_admitted_triple_gets_its_own_file(self):
        """A byte-compare cannot catch two subjects overwriting each other."""
        _seed()
        planned, _ = VaultProjector().plan()
        s = _store()
        admitted = [t for t in s.current_state()
                    if t.predicate in ("content_sha256", "mode_octal",
                                       "preferred_entity")]
        s.close()
        assert len(planned) == len(admitted)

    def test_subjects_that_slugify_alike_get_distinct_files(self):
        record_file_change(path="/etc/a b", reason="one", actor=ACTOR_USER,
                           request_id="r1", tool="editor", after_text="1\n")
        record_file_change(path="/etc/a-b", reason="two", actor=ACTOR_USER,
                           request_id="r2", tool="editor", after_text="2\n")
        planned, _ = VaultProjector().plan()
        assert len(planned) == 2


class TestProvenanceRendering:
    def test_unrecorded_says_so_and_is_never_filled_in(self):
        record_file_change(path="/etc/x.conf", reason=UNRECORDED,
                           actor=ACTOR_USER, request_id="r1", tool="editor",
                           after_text="x\n")
        VaultProjector().rebuild()
        text = next((vault_root() / "notes").glob("*.md")).read_text()
        assert "no reason was recorded" in text
        assert "reason: unrecorded" in text

    def test_only_a_persons_words_are_quoted(self):
        """A deterministic rule's self-naming string is not a quotation."""
        record_file_change(path="/etc/a.conf", reason="I wanted it that way",
                           actor=ACTOR_USER, request_id="r1", tool="editor",
                           after_text="a\n")
        record_file_change(path="/etc/b.conf", reason="watcher: changed on disk",
                           actor=ACTOR_SYSTEM, request_id="r2",
                           tool="config_watcher", after_text="b\n")
        VaultProjector().rebuild()

        a = next((vault_root() / "notes").glob("*a-conf*")).read_text()
        b = next((vault_root() / "notes").glob("*b-conf*")).read_text()
        assert '*"I wanted it that way"*' in a
        assert '*"' not in b


class TestSiting:
    def test_the_vault_honours_halbert_data_dir(self, tmp_path):
        assert str(tmp_path / "data") in str(vault_root())

    def test_the_persona_keys_the_directory(self, monkeypatch):
        _seed(1)
        VaultProjector().rebuild()
        alpha = vault_root()
        assert alpha.name == "testpersona"

        monkeypatch.setenv("HALBERT_PERSONA_ID", "other")
        VaultProjector().rebuild()
        assert vault_root().name == "other"
        assert alpha.exists(), "the first persona's vault was disturbed"

    def test_the_readme_says_it_is_generated(self):
        _seed(1)
        VaultProjector().rebuild()
        readme = (vault_root() / "README.md").read_text()
        assert "projection" in readme
        assert "overwrites" in readme


class TestDegradation:
    def test_it_still_projects_when_the_audit_log_is_unavailable(self, monkeypatch):
        """A projector that dies without haloysius.integrity is worse than
        one that stamps notes ledger_only."""
        import halbert_core.obs.audit as audit_mod

        monkeypatch.setattr(audit_mod, "EventLog", None)
        _seed(1)
        result = VaultProjector().rebuild()

        assert result.written >= 1
        text = next((vault_root() / "notes").glob("*.md")).read_text()
        assert "ledger_only" in text
