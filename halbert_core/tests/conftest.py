# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Shared fixtures."""
import pytest

from halbert_core.model.config_locator import ENV_VAR, WORKSPACE_ENV_VAR


@pytest.fixture(autouse=True)
def _isolated_config_canon_store(monkeypatch, tmp_path):
    """No suite writes to the real ~/.local/share/halbert/config/{canon,snapshots} store.

    CANON_DIR/SNAP_DIR/RAW_DIR are plain strings computed once at import
    in config/snapshot.py; config/queries.py, config/drift.py,
    config/edge_extractor.py, and config/indexer.py each hold their OWN
    copy (either their own independent ``data_subdir(...)`` call, or a
    ``from .snapshot import CANON_DIR``-style binding) — patching
    snapshot.py's globals alone does not reach any of those. Without
    this, any test that exercises the real code path (not the handful
    that already patch these themselves) writes pytest tmp paths into
    the developer's actual canon DB — which is exactly how it ended up
    holding nothing but junk records (SEC-03/04/11's operational rebuild
    gate found ``latest.json`` full of stale tmp-path entries).

    A test that wants a specific canon/snapshot layout still overrides
    these itself (see test_config_queries.py, test_config_snapshot_redacted.py,
    test_security_roles.py) — those explicit ``monkeypatch.setattr`` calls
    simply run after this fixture, on the same ``monkeypatch`` instance,
    and win.
    """
    from halbert_core.config import snapshot as snapshot_mod
    from halbert_core.config import queries as queries_mod
    from halbert_core.config import drift as drift_mod
    from halbert_core.config import edge_extractor as edge_extractor_mod
    from halbert_core.config import indexer as indexer_mod

    store = tmp_path / "_conftest_config_canon"
    raw_dir, canon_dir, snap_dir = str(store / "raw"), str(store / "canon"), str(store / "snapshots")

    monkeypatch.setattr(snapshot_mod, "RAW_DIR", raw_dir)
    monkeypatch.setattr(snapshot_mod, "CANON_DIR", canon_dir)
    monkeypatch.setattr(snapshot_mod, "SNAP_DIR", snap_dir)
    monkeypatch.setattr(queries_mod, "CANON_DIR", canon_dir)
    monkeypatch.setattr(queries_mod, "SNAP_DIR", snap_dir)
    monkeypatch.setattr(drift_mod, "CANON_DIR", canon_dir)
    monkeypatch.setattr(edge_extractor_mod, "CANON_DIR", canon_dir)
    monkeypatch.setattr(indexer_mod, "CANON_DIR", canon_dir)


@pytest.fixture(autouse=True)
def _reset_capability_registry(monkeypatch):
    """No test's capability probe survives into the next test (U6-TEST-01).

    ``capabilities.py`` holds a process-wide ``CapabilityRegistry`` singleton
    that probes once and is never reset. ``_probe_secure_model`` in
    particular reads whatever the process's models.yml resolves to at the
    moment it first runs — the developer's REAL models.yml when no test-level
    isolation (``models_config_dir``/``HALBERT_CONFIG_DIR``) is active yet.
    Without a reset, whichever test happens to run first "wins" the probe
    for the rest of the suite: test_agent_model_override.py priming a real
    secure endpoint made test_llm_routes.py and test_llm_config_layers.py
    order-dependent, and made test_auto_provision.py pass in the full suite
    only because the pollution masked its own gating bug (U4-18).

    The llm_config parse cache is reset alongside it: it is keyed by file
    identity (path/mtime/size/inode), not content, so a probe that resolves
    a slot through it should not be able to serve a stale parse either.
    """
    from halbert_core import capabilities as caps_mod
    from halbert_core.model import llm_config as llm_config_mod

    caps_mod.reset_registry()
    llm_config_mod.invalidate_cache()


@pytest.fixture(autouse=True)
def _no_declared_workspace_layer(monkeypatch):
    """No suite inherits a workspace layer from the developer's shell.

    Unlike $HALBERT_MODELS_CONFIG this one is *additive*: an exported overlay
    does not have to be the file under test to reach it, it only has to declare
    a pin, and every reader that resolves the layers then sees it. So it is
    cleared for every test, not only the ones that ask for a temp config dir.
    """
    monkeypatch.delenv(WORKSPACE_ENV_VAR, raising=False)


@pytest.fixture
def models_config_dir(monkeypatch, tmp_path):
    """Point every models.yml reader/writer at an empty temp user config dir.

    Nothing under test may touch the developer's real models.yml.
    """
    user = tmp_path / "user"
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: user)
    monkeypatch.setattr("halbert_core.model.config_locator.repo_root", lambda: tmp_path / "repo")
    monkeypatch.delenv(ENV_VAR, raising=False)
    return user


@pytest.fixture
def capability_registry(monkeypatch):
    """Isolated capability registry (F5): probes off, preset-driven.

    The variant gates these suites used to patch
    (``cognition_wiring._get_variant``, ``config_wizard._is_home_variant``)
    became *presets* when F5 converted gating to capability probing: the
    decision now reads this registry, and the registry's probes read the
    developer's real being.yml/models.yml. Tests that pin
    variant-conditional behavior control it here instead — deterministically,
    on any machine.

    Returns a controller: ``set_variant("home" | "sysadmin")`` re-probes
    from that variant's preset; ``set_capability(name, bool)`` pins one
    capability explicitly (the being.yml ``capabilities:`` override path).
    """
    import halbert_core.capabilities as caps

    reg = caps.CapabilityRegistry()
    state = {"variant": "sysadmin", "overrides": {}}
    reg._load_config = lambda: (state["variant"], dict(state["overrides"]))

    monkeypatch.setattr(caps, "_PROBES", {})
    monkeypatch.setattr(caps, "_registry", reg)

    class _Controller:
        def set_variant(self, variant):
            state["variant"] = variant
            self._reprobe()

        def set_capability(self, name, value):
            state["overrides"][name] = value
            self._reprobe()

        @staticmethod
        def _reprobe():
            # Drop the cache so the next has_capability() re-probes with
            # the new preset/override state.
            reg._probed = False
            reg._capabilities.clear()

    return _Controller()


@pytest.fixture(autouse=True)
def _isolated_data_and_log_dirs(monkeypatch, tmp_path):
    """No suite writes the real change ledger or the real audit chain.

    ``continuity/state_store.default_state_db_path`` and ``obs/audit``
    resolve through ``utils.paths.data_dir()`` / ``log_dir()`` at call time,
    so without this every test that exercises a write path -- ``write_config``,
    the diff-apply route, an editor save, a chmod by proposal, a thread close
    -- appends to the developer's own ``~/.local/share/halbert/state_ledger.db``
    and to the tamper-evident audit log.

    That is worse than ordinary test pollution. The ledger's whole purpose is
    to be a trustworthy record of why things changed; filling it with pytest
    tmp paths and fixture reasons corrupts exactly the thing the feature
    exists to make trustworthy, and appends to a hash chain that is meant to
    be evidence. The canon-store fixture above exists because the same class
    of bug already happened once to a different store.

    A test wanting a specific layout still overrides these itself: its own
    ``monkeypatch.setenv`` runs after this fixture and wins.
    """
    monkeypatch.setenv("HALBERT_DATA_DIR", str(tmp_path / "_data"))
    monkeypatch.setenv("HALBERT_LOG_DIR", str(tmp_path / "_logs"))


#: The credential every test client presents. Fixed rather than random so a
#: failure message is reproducible, and obviously fake so it can never be
#: mistaken for a real one in a log.
TEST_API_TOKEN = "test-token-not-a-real-credential"


@pytest.fixture(scope="session", autouse=True)
def _authenticated_test_clients():
    """Give every TestClient in the suite a valid credential (SEC-1).

    Every dashboard route now sits behind ``require_owner``. Suites that
    exercise business logic should not each have to re-learn how to
    authenticate, and threading a header through several hundred call sites
    would bury the change that matters in noise.

    **Session-scoped on purpose.** Several suites build their client in a
    ``scope="module"`` fixture, which runs before any function-scoped fixture —
    so a function-scoped version of this patched nothing for them, and the app
    they built had already minted a different token.

    This does not weaken the tests that check the boundary:
    ``tests/test_route_auth_census.py`` asserts on anonymous callers by passing
    its own headers, and an explicit ``headers=`` from a test still wins over
    the default set here.
    """
    import os

    previous = os.environ.get("HALBERT_API_TOKEN")
    os.environ["HALBERT_API_TOKEN"] = TEST_API_TOKEN

    try:
        from starlette.testclient import TestClient
    except ImportError:  # pragma: no cover - dashboard extra not installed
        yield
        return

    original_init = TestClient.__init__
    original_ws = TestClient.websocket_connect

    def init(self, *args, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("Authorization", f"Bearer {TEST_API_TOKEN}")
        original_init(self, *args, headers=headers, **kwargs)

    def websocket_connect(self, url, *args, **kwargs):
        # A browser cannot set a header on a handshake, so the WebSocket door
        # also accepts ?token=. Use that path here, because it is the one a
        # real client takes.
        if "token=" not in url:
            url = f"{url}{'&' if '?' in url else '?'}token={TEST_API_TOKEN}"
        return original_ws(self, url, *args, **kwargs)

    TestClient.__init__ = init
    TestClient.websocket_connect = websocket_connect
    try:
        yield
    finally:
        TestClient.__init__ = original_init
        TestClient.websocket_connect = original_ws
        if previous is None:
            os.environ.pop("HALBERT_API_TOKEN", None)
        else:
            os.environ["HALBERT_API_TOKEN"] = previous


@pytest.fixture(scope="session", autouse=True)
def _skills_user_root_is_not_the_developers(tmp_path_factory):
    """A13 bug 10: the suite read the developer's real skill directory.

    ``daemon_skill_dirs()`` is ``[BUILTIN_DIR, ~/.config/halbert/skills]``
    and nine test call sites go through it. On a machine with skills in
    that directory the suite ran against a different set from CI's, and
    neither run knew: a bundled-set assertion could pass locally because
    an operator skill happened to fill a gap, or fail because one shadowed
    a name. The root points at an empty scratch directory for the session,
    so "the bundled set" means the bundled set.

    A test that wants an operator root builds one and passes ``dirs=``.
    """
    from halbert_core.skills import loader

    scratch = tmp_path_factory.mktemp("user-skills")
    original = loader.USER_SKILL_DIR
    loader.USER_SKILL_DIR = scratch
    try:
        yield scratch
    finally:
        loader.USER_SKILL_DIR = original
