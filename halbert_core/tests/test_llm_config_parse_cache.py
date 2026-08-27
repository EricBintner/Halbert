# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""models.yml is parsed once per turn, not twenty times (post-merge follow-up,
issue 2).

Every model getter — ``get_configured_model``, ``get_specialist_model``,
``get_vision_model``, ``get_ollama_endpoint``, ``provider_for``, ``api_key_for``
— resolves against the store per call, deliberately: one ``LLMClientAdapter`` is
shared by every concurrent request, so caching a *decision* on it would leak a
model choice across sessions. Combined with ``tools_supported`` being a property
that re-resolves on every read, one turn opened and fully parsed models.yml a
dozen-plus times, synchronously, on the event loop, inside the turn lock.

Measured before the fix on a representative turn (see the counts below): 12
parses at ~1.3ms each, ~15ms of blocking YAML per turn — and that turn is a
floor, not a ceiling: a pinned model routes through ``tools_supported_for``,
which costs 6 more.

The fix caches the *parse*, never a decision, keyed on the file's own identity
(path, mtime_ns, size, inode) with a short TTL as a backstop for filesystems
whose timestamps are coarser than a turn. Resolution semantics are untouched:
every getter still resolves per call, against current file contents.
"""
import copy
from pathlib import Path

import pytest
import yaml

from halbert_core.model import llm_config as store

OLLAMA = "http://localhost:11434"

FILE = {
    "compression": {"enabled": True, "threshold": 4000},
    "llm_config": {
        "saved_endpoints": [
            {"id": "ep_1", "name": "Local", "provider": "ollama", "url": OLLAMA, "api_key": "k1"},
        ],
        "chat_model": {"enabled": True, "endpoint_id": "ep_1", "model": "guide-a"},
        "specialist_model": {"enabled": True, "endpoint_id": "ep_1", "model": "spec-a"},
        "vision_model": {"enabled": False, "endpoint_id": "", "model": ""},
    },
}


def _write(user: Path, data: dict) -> Path:
    p = user / "models.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data))
    return p


@pytest.fixture
def parses(monkeypatch):
    """Count full YAML parses of models.yml, and start from a cold cache."""
    store.invalidate_cache()
    counter = {"n": 0}
    original = yaml.safe_load

    def counting(stream):
        counter["n"] += 1
        return original(stream)

    monkeypatch.setattr(store.yaml, "safe_load", counting)
    yield counter
    store.invalidate_cache()


class TestOneTurnParsesOnce:

    def test_a_turns_worth_of_model_resolution_parses_the_file_once(
        self, models_config_dir, parses
    ):
        """The measurement this issue is about, over the real call graph a turn
        runs: the route picks the turn's model, the state machine reads
        ``tools_supported`` for the planning prompt, for the response prompt and
        again when persisting, and the streaming path looks up auth and provider.
        Before the fix this was 12 parses."""
        pytest.importorskip("fastapi")
        _write(models_config_dir, FILE)
        from halbert_core.dashboard.routes import agent as agent_routes
        from halbert_core.model.client import api_key_for, provider_for

        adapter = agent_routes.LLMClientAdapter()
        agent_routes._resolve_turn_model("hello", None, None, None, None, None)
        adapter.tools_supported
        adapter.tools_supported
        adapter.tools_supported
        api_key_for(OLLAMA)
        provider_for(OLLAMA)

        assert parses["n"] == 1

    def test_a_pinned_turn_parses_once_too(self, models_config_dir, parses):
        pytest.importorskip("fastapi")
        _write(models_config_dir, FILE)
        from halbert_core.dashboard.routes import agent as agent_routes

        adapter = agent_routes.LLMClientAdapter()
        agent_routes._resolve_turn_model("hello", None, None, "pinned:3b", None, None)
        adapter.tools_supported_for(model_override="pinned:3b")
        assert parses["n"] == 1

    def test_the_getters_still_answer_correctly(self, models_config_dir, parses):
        _write(models_config_dir, FILE)
        from halbert_core.model.client import (
            api_key_for, get_configured_model, get_ollama_endpoint,
            get_specialist_model, provider_for,
        )
        assert get_configured_model() == "guide-a"
        assert get_specialist_model()[0] == "spec-a"
        assert get_ollama_endpoint() == OLLAMA
        assert provider_for(OLLAMA) == "ollama"
        assert api_key_for(OLLAMA) == "k1"
        assert parses["n"] == 1


class TestLiveEditingStillWorks:
    """Live editing of models.yml is existing behaviour and must survive the
    cache: a stale read here would send a turn to the model the user just
    replaced."""

    def test_an_edit_between_reads_is_seen(self, models_config_dir, parses):
        _write(models_config_dir, FILE)
        assert store.load()["chat_model"]["model"] == "guide-a"

        edited = copy.deepcopy(FILE)   # not yaml.safe_load: it would count
        edited["llm_config"]["chat_model"]["model"] = "guide-b"
        _write(models_config_dir, edited)

        assert store.load()["chat_model"]["model"] == "guide-b"
        assert parses["n"] == 2

    def test_an_edit_that_does_not_change_the_file_size_is_seen(
        self, models_config_dir, parses
    ):
        """mtime is the primary signal precisely because a one-character swap
        leaves the size identical."""
        path = _write(models_config_dir, FILE)
        assert store.load()["chat_model"]["model"] == "guide-a"

        before = path.read_text()
        path.write_text(before.replace("model: guide-a", "model: guide-z"))
        assert len(path.read_text()) == len(before)

        assert store.load()["chat_model"]["model"] == "guide-z"

    def test_a_deleted_file_is_seen(self, models_config_dir):
        path = _write(models_config_dir, FILE)
        assert store.load()["chat_model"]["model"] == "guide-a"
        path.unlink()
        assert store.load() == store.default_llm_config()

    def test_a_file_appearing_on_a_fresh_install_is_seen(self, models_config_dir):
        assert store.load() == store.default_llm_config()
        _write(models_config_dir, FILE)
        assert store.load()["chat_model"]["model"] == "guide-a"

    def test_a_write_through_the_store_is_seen_by_the_next_read(self, models_config_dir):
        _write(models_config_dir, FILE)
        store.set_slot("chat_model", "guide-written", "ep_1")
        assert store.load()["chat_model"]["model"] == "guide-written"
        assert store.load_global()["chat_model"]["model"] == "guide-written"


class TestTheCacheCannotCorruptTheFile:

    def test_an_unreadable_file_is_never_cached_and_never_overwritten(
        self, models_config_dir
    ):
        """"Never overwrite an unreadable models.yml" is existing behaviour and
        the reason ``_read_raw`` distinguishes {} from None. A cached failure
        could outlive the repair, so failures are not cached at all."""
        path = models_config_dir / "models.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        broken = "llm_config: {: : :\n  - [unclosed\n"
        path.write_text(broken)

        assert store.load() == store.default_llm_config()   # defaults for the session
        with pytest.raises(store.ConfigUnreadableError):
            store.save(store.default_llm_config())
        assert path.read_text() == broken                    # untouched

        _write(models_config_dir, FILE)                      # repaired in place
        assert store.load()["chat_model"]["model"] == "guide-a"

    def test_a_caller_mutating_what_it_got_cannot_poison_the_cache(
        self, models_config_dir
    ):
        """``save()`` mutates the dict it is handed. Handing out the cached
        object itself would let one writer's edit become every later reader's
        truth without ever reaching disk."""
        _write(models_config_dir, FILE)
        first = store.load_global_file()
        first["llm_config"]["chat_model"]["model"] = "mutated-in-place"
        first["compression"]["threshold"] = 999_999
        first.pop("compression", None)

        again = store.load_global_file()
        assert again["llm_config"]["chat_model"]["model"] == "guide-a"
        assert again["compression"]["threshold"] == 4000


class TestNoWriteRestsOnTheCache:
    """A write is refused over a models.yml this process cannot parse — and
    that has to be a statement about the file, not about a snapshot of it.

    ``update()`` calls ``load_global()`` (which warms the cache) and then
    ``save()`` microseconds later, so routing the write path through the cache
    left the guarantee resting on the filesystem's ability to distinguish two
    instants. The stamp and the clock are frozen below to stand in for a
    filesystem that cannot: 1-second timestamp granularity is what NFS/SMB home
    directories, HFS+ and exFAT actually give you, and a self-hosted sysadmin
    tool lands on all three. There the cache is not *raced* on the write path,
    it is served every single time.
    """

    @pytest.fixture
    def coarse_filesystem(self, monkeypatch):
        store.invalidate_cache()
        monkeypatch.setattr(store, "_cache_stamp", lambda path: ("coarse", str(path)))
        monkeypatch.setattr(store.time, "monotonic", lambda: 1000.0)
        yield
        store.invalidate_cache()

    def test_a_file_that_broke_after_the_last_read_is_still_never_written_over(
        self, models_config_dir, coarse_filesystem
    ):
        path = _write(models_config_dir, FILE)
        assert store.load()["chat_model"]["model"] == "guide-a"     # warms the cache
        broken = "llm_config: {: : :\n  - [unclosed\n"
        path.write_text(broken)

        with pytest.raises(store.ConfigUnreadableError):
            store.update({"chat_model": {"enabled": True, "endpoint_id": "ep_1",
                                         "model": "guide-b"}})
        assert path.read_text() == broken

    def test_an_edit_made_after_the_last_read_is_not_written_back_over(
        self, models_config_dir, coarse_filesystem
    ):
        """The same defect without a broken file: a write rebased on a cached
        parse silently reverts whatever the human changed in between."""
        _write(models_config_dir, FILE)
        assert store.load()["chat_model"]["model"] == "guide-a"     # warms the cache

        edited = copy.deepcopy(FILE)
        edited["llm_config"]["specialist_model"]["model"] = "spec-edited-by-hand"
        path = _write(models_config_dir, edited)

        store.set_top_level("compression", {"enabled": True, "threshold": 222})

        on_disk = yaml.safe_load(path.read_text())
        assert on_disk["llm_config"]["specialist_model"]["model"] == "spec-edited-by-hand"
        assert on_disk["compression"]["threshold"] == 222

    def test_updates_payload_comes_from_the_file_not_the_cache(
        self, models_config_dir, coarse_filesystem
    ):
        """``save()`` validating fresh bytes is only half the guarantee.

        ``update()`` builds the dict it persists from ``load_global()``. When
        that read came from the cache, the validation read sees the human's
        edit, waves it through, and then the write puts the pre-edit snapshot
        back over it — the edit is lost just as completely as if nothing had
        been validated at all. The payload has to come from the file too.
        """
        path = _write(models_config_dir, FILE)
        assert store.load()["chat_model"]["model"] == "guide-a"     # warms the cache

        edited = copy.deepcopy(FILE)
        edited["llm_config"]["specialist_model"]["model"] = "spec-edited-by-hand"
        _write(models_config_dir, edited)

        store.update({"chat_model": {"enabled": True, "endpoint_id": "ep_1",
                                     "model": "guide-b"}})

        on_disk = yaml.safe_load(path.read_text())["llm_config"]
        # The update landed ...
        assert on_disk["chat_model"]["model"] == "guide-b"
        # ... without reverting the edit it never saw.
        assert on_disk["specialist_model"]["model"] == "spec-edited-by-hand"

    def test_a_cached_parse_does_not_outlive_the_files_health(
        self, models_config_dir, coarse_filesystem
    ):
        """A cached SUCCESS is as dangerous as a cached failure would be: once
        a read has found the file unparsable, no reader may go on being served
        the parse taken before it broke."""
        path = _write(models_config_dir, FILE)
        assert store.load()["chat_model"]["model"] == "guide-a"     # warms the cache
        path.write_text("llm_config: {: : :\n  - [unclosed\n")

        with pytest.raises(store.ConfigUnreadableError):
            store.save(store.default_llm_config())
        assert store.load() == store.default_llm_config()

    def test_the_migration_rewrite_does_not_rest_on_the_cache_either(
        self, models_config_dir, monkeypatch, coarse_filesystem
    ):
        """``load_global_file()`` writes too — when the file it read has to be
        migrated, or has an endpoint with no id — and that write is a write.

        A rewrite that fails (a read-only config dir, a full disk) is what
        leaves a needs-rewrite parse sitting in the cache: the invalidation
        lives inside ``_write_raw``, past the point that raised. The next read
        must not then migrate that snapshot over whatever is on disk by then.
        """
        legacy = {"orchestrator": {"model": "legacy-guide", "endpoint": OLLAMA},
                  "saved_endpoints": [{"name": "Local", "provider": "ollama", "url": OLLAMA}]}
        path = _write(models_config_dir, legacy)

        write_fails = {"now": True}
        real_write_raw = store._write_raw

        def _write_raw(data):
            if write_fails["now"]:
                raise OSError("No space left on device")
            real_write_raw(data)

        monkeypatch.setattr(store, "_write_raw", _write_raw)
        assert store.load()["chat_model"]["model"] == "legacy-guide"   # warms the cache
        assert path.read_text() == yaml.safe_dump(legacy)              # nothing written
        write_fails["now"] = False

        broken = "llm_config: {: : :\n  - [unclosed\n"
        path.write_text(broken)

        assert store.load() == store.default_llm_config()   # defaults for the session
        assert path.read_text() == broken                   # and untouched
