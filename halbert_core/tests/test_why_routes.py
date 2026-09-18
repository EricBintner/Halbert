# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""POST/GET/DELETE /api/why and GET /api/why/by-type.

The operator's own note on one item, and the store underneath it. Routed
through ``create_app()`` so a missing ``include_router`` fails here rather
than in the browser.

Most of what follows is one assertion in several costumes: the surface must
never say "nothing recorded" when it means "I could not look", and must never
say "saved" when nothing reached the disk. Both were true of this store
before — ``_save_to_disk`` logged its failures and returned, so ``add()``
handed back an id for a note that did not exist; ``_load_from_disk``
swallowed its own, so a corrupt file read as empty forever and the next save
replaced it with an empty one.
"""
from __future__ import annotations

import json
import os
import stat

import pytest

from halbert_core.knowledge import self_knowledge as sk_mod
from halbert_core.knowledge.self_knowledge import (
    KnowledgeEntry,
    KnowledgeType,
    KnowledgeUnavailable,
    SelfKnowledge,
    get_self_knowledge,
)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from halbert_core.dashboard.app import create_app

    return TestClient(create_app())


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A rationale store of this test's own, under tmp_path.

    ``HALBERT_DATA_DIR`` is the only thing that decides where the store
    lives, which is the point: the getter used to hardcode ``Path.home()``,
    so running this suite wrote the developer's real knowledge file.

    ChromaDB indexing is switched off. It is a semantic index over the same
    entries, not the record of truth, and building a fresh persistent client
    per test costs about a second and reaches for an embedding model that may
    not be on the machine. Nothing here asks a question it answers.

    Returns the path the store should end up at.
    """
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(SelfKnowledge, "_init_chromadb", lambda self: None)
    sk_mod.reset_self_knowledge()
    return tmp_path / "data" / "knowledge" / "self_knowledge.json"


def _note(item_id="gpu:0", item_name="NVIDIA RTX 4090", item_type="gpu",
          why="it drives the two left displays"):
    return {"item_id": item_id, "item_name": item_name,
            "item_type": item_type, "why": why}


def _corrupt(path):
    """Leave a file that exists, is not empty, and is not readable as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"entries": [{"id": "half a re')
    sk_mod.reset_self_knowledge()


class TestRoundTrip:

    def test_what_was_saved_is_what_comes_back(self, client, store):
        saved = client.post("/api/why", json=_note())
        assert saved.status_code == 200
        body = saved.json()
        assert body["item_id"] == "gpu:0"
        assert body["saved"] is True
        assert body["updated_at"]

        read = client.get("/api/why", params={"item_id": "gpu:0"}).json()
        assert read["found"] is True
        assert read["why"] == "it drives the two left displays"
        assert read["item_name"] == "NVIDIA RTX 4090"
        assert read["item_type"] == "gpu"
        assert read["updated_at"]

    def test_it_actually_reached_the_disk(self, client, store):
        client.post("/api/why", json=_note())
        on_disk = json.loads(store.read_text())
        ids = [e["id"] for e in on_disk["entries"]]
        assert ids == ["rationale:gpu:0"]

    def test_the_store_is_under_the_data_dir_not_the_real_home(self, client, store):
        client.post("/api/why", json=_note())
        assert store.exists()
        # The one that matters: nothing was written next to the operator's
        # own records. _get_data_path hardcoded Path.home() until it didn't.
        resolved = get_self_knowledge()._data_path
        assert str(resolved) == str(store)
        assert str(resolved).startswith(os.environ["HALBERT_DATA_DIR"])

    def test_re_saving_replaces_the_note_and_keeps_one_entry(self, client, store):
        client.post("/api/why", json=_note(why="first reason"))
        client.post("/api/why", json=_note(why="second reason"))

        read = client.get("/api/why", params={"item_id": "gpu:0"}).json()
        assert read["why"] == "second reason"
        assert len(json.loads(store.read_text())["entries"]) == 1

    def test_re_saving_keeps_the_original_created_at(self, client, store):
        client.post("/api/why", json=_note(why="first reason"))
        first = get_self_knowledge().get("rationale:gpu:0").created_at
        client.post("/api/why", json=_note(why="second reason"))
        # When a person first wrote something down is a fact about them, not
        # about the last edit.
        assert get_self_knowledge().get("rationale:gpu:0").created_at == first


class TestNothingRecorded:

    def test_an_unknown_item_is_found_false_not_an_error(self, client, store):
        resp = client.get("/api/why", params={"item_id": "gpu:9"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is False
        assert body["why"] is None
        assert body["item_name"] is None
        assert body["item_type"] is None

    def test_an_empty_store_answers_found_false(self, client, store):
        assert not store.exists()
        assert client.get("/api/why", params={"item_id": "gpu:0"}).json()["found"] is False


class TestCouldNotLook:
    """An unreadable store is a 503. It is never found=false.

    The distinction is the whole reason this route exists as its own module:
    a person told "nothing recorded" about a note they know they wrote will
    write it again, over the top of the file that still has it.
    """

    def test_an_unreadable_store_is_503(self, client, store):
        _corrupt(store)
        resp = client.get("/api/why", params={"item_id": "gpu:0"})
        assert resp.status_code == 503
        assert "could not be read" in resp.json()["detail"]

    def test_by_type_on_an_unreadable_store_is_503(self, client, store):
        _corrupt(store)
        assert client.get("/api/why/by-type", params={"item_type": "gpu"}).status_code == 503

    def test_saving_into_an_unreadable_store_is_503(self, client, store):
        _corrupt(store)
        assert client.post("/api/why", json=_note()).status_code == 503

    def test_a_failed_read_does_not_get_overwritten_by_the_next_save(self, client, store):
        _corrupt(store)
        before = store.read_text()
        client.post("/api/why", json=_note())
        # The recoverable file is still there. Replacing it with an empty
        # store would have destroyed the only copy of the operator's notes.
        assert store.read_text() == before

    def test_deleting_from_an_unreadable_store_is_503(self, client, store):
        _corrupt(store)
        assert client.delete("/api/why", params={"item_id": "gpu:0"}).status_code == 503


class TestCouldNotWrite:
    """A write that did not land is a 503, never a 200 saying saved."""

    def test_a_failed_write_is_503_and_never_claims_saved(
            self, client, store, monkeypatch):
        def refuse(self):
            raise KnowledgeUnavailable("the disk said no")

        monkeypatch.setattr(SelfKnowledge, "_save_to_disk", refuse)
        resp = client.post("/api/why", json=_note())
        assert resp.status_code == 503
        assert "not recorded" in resp.json()["detail"]
        assert "saved" not in resp.json()

    @pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="root can write a read-only directory, so there is no failure to observe",
    )
    def test_a_real_unwritable_directory_is_503_and_leaves_the_first_note(
            self, client, store):
        assert client.post("/api/why", json=_note()).status_code == 200
        directory = store.parent
        original_mode = stat.S_IMODE(directory.stat().st_mode)
        directory.chmod(0o500)
        try:
            resp = client.post("/api/why", json=_note(item_id="gpu:1"))
            assert resp.status_code == 503
        finally:
            directory.chmod(original_mode)

        # The failed write left the previous file intact and no debris.
        assert client.get("/api/why", params={"item_id": "gpu:0"}).json()["found"] is True
        assert client.get("/api/why", params={"item_id": "gpu:1"}).json()["found"] is False
        assert [p.name for p in directory.iterdir()] == ["self_knowledge.json"]


class TestTwoThingsWithTheSameName:
    """The smart_add regression, in the shape that produced it.

    ``smart_add`` compares entries by CONTENT, and content here is the item's
    display name. Two identical GPUs are two different things with one name;
    routing this surface through ``smart_add`` made the second note a
    "duplicate" and dropped it with nothing but a log line.
    """

    def test_identical_names_keep_two_distinct_notes(self, client, store):
        client.post("/api/why", json=_note(
            item_id="gpu:0", item_name="NVIDIA RTX 4090", why="drives the displays"))
        client.post("/api/why", json=_note(
            item_id="gpu:1", item_name="NVIDIA RTX 4090", why="reserved for inference"))

        first = client.get("/api/why", params={"item_id": "gpu:0"}).json()
        second = client.get("/api/why", params={"item_id": "gpu:1"}).json()
        assert first["why"] == "drives the displays"
        assert second["why"] == "reserved for inference"
        assert len(json.loads(store.read_text())["entries"]) == 2

    def test_both_survive_a_by_type_listing(self, client, store):
        client.post("/api/why", json=_note(
            item_id="gpu:0", item_name="NVIDIA RTX 4090", why="drives the displays"))
        client.post("/api/why", json=_note(
            item_id="gpu:1", item_name="NVIDIA RTX 4090", why="reserved for inference"))

        body = client.get("/api/why/by-type", params={"item_type": "gpu"}).json()
        assert body["count"] == 2
        assert set(body["rationales"]) == {"gpu:0", "gpu:1"}


class TestByType:

    def test_it_returns_only_that_type(self, client, store):
        client.post("/api/why", json=_note(item_id="gpu:0", item_type="gpu"))
        client.post("/api/why", json=_note(
            item_id="net:eth0", item_name="eth0", item_type="network",
            why="the only wired link"))

        body = client.get("/api/why/by-type", params={"item_type": "gpu"}).json()
        assert body["item_type"] == "gpu"
        assert body["count"] == 1
        assert set(body["rationales"]) == {"gpu:0"}
        row = body["rationales"]["gpu:0"]
        assert row["why"] == "it drives the two left displays"
        assert row["item_name"] == "NVIDIA RTX 4090"
        assert row["updated_at"]

    def test_an_unused_type_is_an_empty_listing_not_an_error(self, client, store):
        client.post("/api/why", json=_note())
        body = client.get("/api/why/by-type", params={"item_type": "service"}).json()
        assert body["count"] == 0
        assert body["rationales"] == {}

    def test_it_ignores_the_machines_own_config_rationales(self, client, store):
        """The bootstrap writes CONFIG_RATIONALE entries into the same store.

        Those are the machine's inferences about itself, not a person's note,
        and a listing that mixed them in would attribute the machine's
        reasoning to the operator.
        """
        client.post("/api/why", json=_note())
        get_self_knowledge().add(KnowledgeEntry(
            id="config:filesystem_bcachefs",
            type=KnowledgeType.CONFIG_RATIONALE,
            subject="gpu:0",
            content="bcachefs usage",
            rationale="inferred by the profile scan",
            source="system",
            tags=["gpu", "storage"],
        ))

        body = client.get("/api/why/by-type", params={"item_type": "gpu"}).json()
        assert set(body["rationales"]) == {"gpu:0"}
        assert body["rationales"]["gpu:0"]["why"] == "it drives the two left displays"


class TestRejectedInput:

    @pytest.mark.parametrize("why", ["", "   ", "\n\t "])
    def test_a_blank_note_is_400(self, client, store, why):
        resp = client.post("/api/why", json=_note(why=why))
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"]

    def test_a_blank_note_records_nothing(self, client, store):
        client.post("/api/why", json=_note(why="   "))
        assert not store.exists()

    def test_a_blank_item_id_is_400(self, client, store):
        assert client.post("/api/why", json=_note(item_id="  ")).status_code == 400


class TestDelete:

    def test_it_removes_the_note(self, client, store):
        client.post("/api/why", json=_note())
        resp = client.delete("/api/why", params={"item_id": "gpu:0"})
        assert resp.status_code == 200
        assert resp.json() == {"item_id": "gpu:0", "deleted": True}
        assert client.get("/api/why", params={"item_id": "gpu:0"}).json()["found"] is False

    def test_it_reaches_the_disk(self, client, store):
        client.post("/api/why", json=_note())
        client.delete("/api/why", params={"item_id": "gpu:0"})
        assert json.loads(store.read_text())["entries"] == []

    def test_a_second_delete_is_a_no_op_not_an_error(self, client, store):
        client.post("/api/why", json=_note())
        client.delete("/api/why", params={"item_id": "gpu:0"})
        resp = client.delete("/api/why", params={"item_id": "gpu:0"})
        assert resp.status_code == 200
        assert resp.json()["deleted"] is False

    def test_deleting_something_never_recorded_is_a_no_op(self, client, store):
        resp = client.delete("/api/why", params={"item_id": "gpu:9"})
        assert resp.status_code == 200
        assert resp.json()["deleted"] is False

    def test_it_leaves_the_other_notes_alone(self, client, store):
        client.post("/api/why", json=_note(item_id="gpu:0"))
        client.post("/api/why", json=_note(item_id="gpu:1"))
        client.delete("/api/why", params={"item_id": "gpu:0"})
        assert client.get("/api/why", params={"item_id": "gpu:1"}).json()["found"] is True


class TestTheStoreItself:
    """The claims the route rests on, asserted against the store directly."""

    def test_add_raises_rather_than_returning_an_id_for_a_lost_write(
            self, store, monkeypatch):
        sk = get_self_knowledge()
        sk.add(KnowledgeEntry(
            id="rationale:gpu:0", type=KnowledgeType.CONFIG_RATIONALE,
            subject="gpu:0", content="RTX 4090", rationale="first",
            source="user", tags=["gpu", "rationale"]))

        directory = store.parent
        original_mode = stat.S_IMODE(directory.stat().st_mode)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("root can write a read-only directory")
        directory.chmod(0o500)
        try:
            with pytest.raises(KnowledgeUnavailable):
                sk.add(KnowledgeEntry(
                    id="rationale:gpu:1", type=KnowledgeType.CONFIG_RATIONALE,
                    subject="gpu:1", content="RTX 4090", rationale="second",
                    source="user", tags=["gpu", "rationale"]))
        finally:
            directory.chmod(original_mode)

        # Rolled back: memory does not hold a note the disk never got, and a
        # later successful write must not smuggle it in.
        assert sk.get("rationale:gpu:1") is None

    def test_an_unreadable_store_reports_itself_unreadable(self, store):
        _corrupt(store)
        sk = get_self_knowledge()
        assert sk.readable is False
        assert sk.load_error

    def test_an_unreadable_store_refuses_to_be_written(self, store):
        _corrupt(store)
        sk = get_self_knowledge()
        with pytest.raises(KnowledgeUnavailable):
            sk.add(KnowledgeEntry(
                id="rationale:gpu:0", type=KnowledgeType.CONFIG_RATIONALE,
                subject="gpu:0", content="RTX 4090", rationale="why",
                source="user", tags=["gpu", "rationale"]))

    def test_constructing_the_store_writes_nothing(self, store):
        """A read must not leave a directory behind on a machine that has
        never recorded anything. The path getter used to mkdir."""
        data_root = store.parent.parent
        assert not data_root.exists()
        get_self_knowledge()
        assert not data_root.exists()

    def test_the_singleton_can_be_reset(self, store):
        first = get_self_knowledge()
        sk_mod.reset_self_knowledge()
        assert get_self_knowledge() is not first


class TestRecoveringFromAFailedRead:
    """Both 503 texts say "repair it, then try again". That has to be true."""

    def test_a_repaired_store_answers_without_a_restart(self, client, store):
        client.post("/api/why", json=_note())
        good = store.read_text()

        _corrupt(store)
        assert client.get("/api/why", params={"item_id": "gpu:0"}).status_code == 503

        # Exactly what the message tells the operator to do, and nothing else:
        # no restart, no reset_self_knowledge(), just the file put back.
        store.write_text(good)

        read = client.get("/api/why", params={"item_id": "gpu:0"})
        assert read.status_code == 200
        assert read.json()["found"] is True
        assert read.json()["why"] == _note()["why"]

    def test_a_still_broken_store_stays_503(self, client, store):
        _corrupt(store)
        assert client.get("/api/why", params={"item_id": "gpu:0"}).status_code == 503
        assert client.get("/api/why", params={"item_id": "gpu:0"}).status_code == 503

    def test_a_retry_that_fails_leaves_nothing_half_loaded(self, client, store):
        client.post("/api/why", json=_note())

        # A file whose first entry parses and whose second does not.
        store.write_text('{"entries": [{"id": "a", "type": "identity", "subject": "s",'
                         ' "content": "c"}, {"id": "b", "brok')
        sk_mod.reset_self_knowledge()
        sk = sk_mod.get_self_knowledge()

        assert sk.readable is False
        assert sk.retry_load() is False
        # Not "one entry recorded" — a partial load presented as the whole
        # store is the same lie as an empty one, one degree quieter.
        assert sk._knowledge == {}


class TestAStoreThatCannotBeSearched:
    """Path.exists() answers False for a directory this uid cannot search."""

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can search any directory")
    def test_an_unsearchable_directory_is_unreadable_not_empty(self, client, store):
        client.post("/api/why", json=_note())
        assert store.exists()

        sk_mod.reset_self_knowledge()
        os.chmod(store.parent, 0o000)
        try:
            # The bug this pins: .exists() swallows the OSError and answers
            # False, so the store reported "nothing recorded" and the next
            # save wrote an empty file over a note that was still there.
            read = client.get("/api/why", params={"item_id": "gpu:0"})
            assert read.status_code == 503, "an unsearchable store must not read as empty"

            save = client.post("/api/why", json=_note(why="overwrite"))
            assert save.status_code == 503
            assert "saved" not in save.json()
        finally:
            os.chmod(store.parent, stat.S_IRWXU)

        # The original note is still on disk, untouched.
        sk_mod.reset_self_knowledge()
        assert client.get("/api/why", params={"item_id": "gpu:0"}).json()["why"] == _note()["why"]


class TestDeletingThroughTheKnowledgeSettingsRoute:
    """The neighbouring delete route called a method that never existed."""

    def test_it_deletes_and_persists_instead_of_500ing(self, client, store):
        client.post("/api/why", json=_note())

        gone = client.delete("/api/settings/knowledge/rationale:gpu:0")
        assert gone.status_code == 200, gone.text
        assert gone.json()["success"] is True

        # It reached the disk, not just memory — the old handler popped the
        # entry, raised AttributeError on sk._save(), returned 500, and let
        # the next unrelated save persist a deletion it had denied.
        sk_mod.reset_self_knowledge()
        assert client.get("/api/why", params={"item_id": "gpu:0"}).json()["found"] is False

    def test_deleting_something_absent_is_404_not_500(self, client, store):
        assert client.delete("/api/settings/knowledge/rationale:nope").status_code == 404
