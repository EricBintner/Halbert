# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""FD-10: the opt-in package preflight, the gate beside the entry guard.

``entry_guard`` screens the SHAPE of a config entry and says nothing
about what ``npx -y @scope/pkg@1.2.3`` pulls down. This suite pins the
other gate: resolve the artifact, ask OSV about it, and refuse the SERVER
— never the daemon — when the answer is bad or absent.

The switch-off test asserts on the HTTP SEAM, not on a log line: "off"
has to mean no request left the machine, and a log assertion would pass
just as happily for a request that went out silently.
"""
from types import SimpleNamespace

import pytest

from halbert_core.mcp import package_preflight as pf


# -- fixtures ---------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_caches():
    pf.reset_preflight_caches()
    yield
    pf.reset_preflight_caches()


def entry(command="npx", args=(), transport="stdio", name="planted"):
    return SimpleNamespace(name=name, transport=transport,
                           command=command, args=tuple(args))


ON = pf.PreflightConfig(enabled=True)
STRICT = pf.PreflightConfig(enabled=True, strict=True)


def advisory(identifier="GHSA-xxxx", severity=None, cvss=None, malicious=False):
    """One OSV vuln object, in the shapes OSV actually returns."""
    vuln = {"id": identifier}
    if cvss is not None:
        vuln["severity"] = [{"type": "CVSS_V3", "score": cvss}]
    if severity is not None:
        vuln["database_specific"] = {"severity": severity}
    if malicious:
        vuln.setdefault("database_specific", {})["malicious"] = True
    return vuln


class Seam:
    """A counting stand-in for the one network call."""

    def __init__(self, vulns=(), raises=None):
        self.calls = []
        self.payloads = []
        self._vulns = list(vulns)
        self._raises = raises

    def query(self, identity, timeout):
        self.calls.append((identity, timeout))
        if self._raises is not None:
            raise self._raises
        return list(self._vulns)

    def post(self, payload, timeout):
        """Patched over ``_osv_post`` — the true HTTP boundary."""
        self.payloads.append(payload)
        if self._raises is not None:
            raise self._raises
        return {"vulns": list(self._vulns)}


# -- 1. a known-HIGH advisory is refused, and the id is named ---------------

def test_a_high_advisory_refuses_and_names_the_advisory_id():
    seam = Seam([advisory("GHSA-high-1", severity="HIGH")])
    result = pf.check_server(
        entry(args=["-y", "@scope/pkg@1.2.3"]), config=ON, query=seam.query)

    assert result.refused
    assert result.reason == pf.REASON_ADVISORY
    assert result.severity == "HIGH"
    assert "GHSA-high-1" in result.advisories
    assert "GHSA-high-1" in result.message("srv")


def test_a_critical_advisory_refuses():
    seam = Seam([advisory("GHSA-crit", severity="CRITICAL")])
    result = pf.check_server(
        entry("uvx", ["mcp-server-time==1.0.0"]), config=ON, query=seam.query)
    assert result.refused
    assert result.severity == "CRITICAL"


def test_a_malware_record_refuses_even_with_no_severity_at_all():
    """The MAL- feed is what FD-10 is actually about, and those records
    routinely carry no CVSS — scoring them by severity alone would file
    the exact thing this gate exists for under 'could not tell'."""
    seam = Seam([advisory("MAL-2026-9999")])
    result = pf.check_server(
        entry(args=["-y", "@scope/pkg@1.2.3"]), config=ON, query=seam.query)
    assert result.refused
    assert result.reason == pf.REASON_MALWARE
    assert result.severity == "CRITICAL"


def test_a_clean_package_proceeds():
    seam = Seam([])
    result = pf.check_server(
        entry(args=["-y", "@scope/pkg@1.2.3"]), config=ON, query=seam.query)
    assert not result.refused
    assert result.reason == pf.REASON_CLEAN
    assert result.queried is True


# -- 2. an unresolvable identity is refused, and SAYS unresolvable ----------

def test_an_unresolvable_identity_is_refused_and_does_not_imply_a_clean_scan():
    """A launcher that DOES fetch, whose artifact cannot be named."""
    seam = Seam([])
    result = pf.check_server(
        entry("npx", ["-y", "github:someone/repo"]), config=ON, query=seam.query)

    assert result.refused
    assert result.reason == pf.REASON_UNRESOLVABLE
    assert seam.calls == [], "an unresolvable entry must not be queried"
    assert "clean" not in result.detail.lower()
    assert "registry" in result.detail


def test_an_unpinned_package_warns_and_launches_and_says_to_pin_one():
    """R1. The commonest real MCP entry shape. It is asked about at the
    package level, and a clean package-level answer is a warning — not a
    pass, because what it installs is still decided at launch."""
    seam = Seam([])
    result = pf.check_server(
        entry(args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]),
        config=ON, query=seam.query)

    assert not result.refused
    assert result.reason == pf.REASON_UNPINNED
    assert "pin" in result.detail.lower()
    # It asked, and it asked WITHOUT a version.
    assert len(seam.calls) == 1
    assert seam.calls[0][0].version == ""


@pytest.mark.parametrize("command,args", [
    ("npx", ["-y", "pkg@latest"]),
    ("npx", ["-y", "pkg@^1.2.3"]),
    ("npx", ["-y", "pkg@~1.2"]),
    ("uvx", ["--from", "mcp-server-time>=1.0", "mcp-server-time"]),
    ("go", ["run", "example.com/x/y@latest"]),
])
def test_only_an_exact_version_counts_as_a_pin(command, args):
    assert pf.resolve_package(command, args).kind == "unpinned"


# -- 3. a network failure refuses that server and never raises -------------

def test_a_network_failure_refuses_that_one_server():
    seam = Seam(raises=pf.PreflightUnreachable("connection refused"))
    result = pf.check_server(
        entry(args=["-y", "pkg@1.0.0"]), config=ON, query=seam.query)

    assert result.refused
    assert result.reason == pf.REASON_UNREACHABLE
    assert "unchecked" in result.detail


def test_an_unexpected_exception_from_the_source_is_still_only_a_refusal():
    seam = Seam(raises=RuntimeError("boom"))
    result = pf.check_server(
        entry(args=["-y", "pkg@1.0.0"]), config=ON, query=seam.query)
    assert result.refused
    assert result.reason == pf.REASON_UNREACHABLE


@pytest.mark.asyncio
async def test_a_refusal_does_not_raise_into_daemon_start(monkeypatch, tmp_path):
    """``connect()`` collects a preflight refusal like any other
    per-server failure: the other servers still come up and nothing
    propagates out of the daemon's start."""
    from halbert_core.mcp import client as client_mod
    from halbert_core.mcp.config import MCPClientConfig, MCPServerConfig

    bad = MCPServerConfig(name="bad", transport="stdio", command="npx",
                          args=("-y", "pkg@1.0.0"))
    good = MCPServerConfig(name="good", transport="stdio", command="npx",
                           args=("-y", "other@1.0.0"))

    monkeypatch.setattr(
        pf, "load_preflight_config", lambda: pf.PreflightConfig(enabled=True))
    monkeypatch.setattr(
        pf, "_query_osv",
        lambda identity, timeout: (
            [advisory("GHSA-bad", severity="CRITICAL")]
            if identity.name == "pkg" else []))

    connected = []

    class _FakeTransport:
        def __init__(self, name):
            self.name = name
            self.alive = True

        async def connect(self):
            connected.append(self.name)

        async def close(self):
            pass

    monkeypatch.setattr(client_mod, "build_transport",
                        lambda cfg: _FakeTransport(cfg.name))

    client = client_mod.MCPClient(
        config_loader=lambda: MCPClientConfig(servers=(bad, good)))
    await client.connect()          # must not raise

    assert connected == ["good"]
    assert client.connected_servers() == ["good"]


@pytest.mark.asyncio
async def test_a_refusal_reaches_a_caller_as_MCPPreflightRefused(monkeypatch):
    from halbert_core.mcp import client as client_mod
    from halbert_core.mcp.config import MCPClientConfig, MCPServerConfig

    bad = MCPServerConfig(name="bad", transport="stdio", command="npx",
                          args=("-y", "pkg@1.0.0"))
    monkeypatch.setattr(
        pf, "load_preflight_config", lambda: pf.PreflightConfig(enabled=True))
    monkeypatch.setattr(
        pf, "_query_osv",
        lambda identity, timeout: [advisory("MAL-1", malicious=True)])

    client = client_mod.MCPClient(
        config_loader=lambda: MCPClientConfig(servers=(bad,)))
    with pytest.raises(client_mod.MCPPreflightRefused) as excinfo:
        await client._ensure("bad")
    assert "MAL-1" in str(excinfo.value)
    # Not a connection state: nothing was launched and nothing contacted.
    assert not isinstance(excinfo.value, client_mod.MCPConnectionError)


# -- 4. the negative cache means two launches make one request -------------

def test_the_clean_answer_is_cached_so_two_launches_make_one_request():
    seam = Seam([])
    server = entry(args=["-y", "pkg@1.0.0"])

    first = pf.check_server(server, config=ON, query=seam.query)
    second = pf.check_server(server, config=ON, query=seam.query)

    assert len(seam.calls) == 1
    assert first.queried is True and second.queried is False
    assert not first.refused and not second.refused


def test_the_advisory_answer_is_cached_too():
    seam = Seam([advisory("GHSA-1", severity="HIGH")])
    server = entry(args=["-y", "pkg@1.0.0"])
    pf.check_server(server, config=ON, query=seam.query)
    second = pf.check_server(server, config=ON, query=seam.query)
    assert len(seam.calls) == 1
    assert second.refused


def test_a_different_version_is_a_different_cache_key():
    seam = Seam([])
    pf.check_server(entry(args=["-y", "pkg@1.0.0"]), config=ON, query=seam.query)
    pf.check_server(entry(args=["-y", "pkg@1.0.1"]), config=ON, query=seam.query)
    assert len(seam.calls) == 2


def test_an_expired_entry_is_re_asked():
    seam = Seam([])
    short = pf.PreflightConfig(enabled=True, cache_ttl_seconds=0.001)
    server = entry(args=["-y", "pkg@1.0.0"])
    pf.check_server(server, config=short, query=seam.query)
    import time as _time
    _time.sleep(0.01)
    pf.check_server(server, config=short, query=seam.query)
    assert len(seam.calls) == 2


def test_a_failure_is_not_cached():
    """A network blip must not be sticky for the rest of the TTL."""
    failing = Seam(raises=pf.PreflightUnreachable("down"))
    server = entry(args=["-y", "pkg@1.0.0"])
    assert pf.check_server(server, config=ON, query=failing.query).refused

    working = Seam([])
    assert not pf.check_server(server, config=ON, query=working.query).refused
    assert len(working.calls) == 1


# -- 5. with the switch off, nothing is queried at all ---------------------

def test_with_the_switch_off_nothing_is_queried(monkeypatch):
    """Asserted on the HTTP seam, not on a log line."""
    seam = Seam([advisory("GHSA-crit", severity="CRITICAL")])
    monkeypatch.setattr(pf, "_osv_post", seam.post)

    result = pf.check_server(
        entry(args=["-y", "pkg@1.0.0"]), config=pf.PreflightConfig())

    assert not result.refused
    assert result.reason == pf.REASON_DISABLED
    assert seam.payloads == []


def test_the_shipped_default_is_off(monkeypatch, tmp_path):
    monkeypatch.setattr("halbert_core.utils.platform.get_config_dir",
                        lambda: tmp_path)
    pf.reset_preflight_caches()
    assert pf.is_enabled() is False
    assert pf.load_preflight_config().enabled is False


@pytest.mark.asyncio
async def test_the_client_does_not_even_reach_the_gate_when_off(monkeypatch):
    from halbert_core.mcp import client as client_mod
    from halbert_core.mcp.config import MCPClientConfig, MCPServerConfig

    seam = Seam([advisory("MAL-1", malicious=True)])
    monkeypatch.setattr(pf, "_osv_post", seam.post)
    monkeypatch.setattr(pf, "load_preflight_config", lambda: pf.PreflightConfig())

    server = MCPServerConfig(name="s", transport="stdio", command="npx",
                             args=("-y", "pkg@1.0.0"))

    class _FakeTransport:
        alive = True

        async def connect(self):
            pass

        async def close(self):
            pass

    monkeypatch.setattr(client_mod, "build_transport", lambda cfg: _FakeTransport())
    client = client_mod.MCPClient(
        config_loader=lambda: MCPClientConfig(servers=(server,)))
    await client._ensure("s")
    assert seam.payloads == []


# -- 6. strict turns "could not tell" from warn into refuse ----------------

def test_an_advisory_with_no_severity_warns_by_default_and_refuses_in_strict():
    seam = Seam([advisory("GHSA-unrated")])
    server = entry(args=["-y", "pkg@1.0.0"])

    lenient = pf.check_server(server, config=ON, query=seam.query)
    assert not lenient.refused
    assert lenient.severity == "UNKNOWN"
    assert "UNKNOWN" in lenient.detail

    pf.reset_preflight_caches()
    strict = pf.check_server(server, config=STRICT, query=seam.query)
    assert strict.refused
    assert strict.reason == pf.REASON_ADVISORY
    assert "GHSA-unrated" in strict.advisories


def test_a_low_advisory_warns_by_default_and_refuses_in_strict():
    seam = Seam([advisory("GHSA-low", severity="LOW")])
    server = entry(args=["-y", "pkg@1.0.0"])
    assert not pf.check_server(server, config=ON, query=seam.query).refused
    pf.reset_preflight_caches()
    assert pf.check_server(server, config=STRICT, query=seam.query).refused


def test_an_unsupported_launcher_notes_by_default_and_refuses_in_strict():
    server = entry("docker", ["run", "--rm", "-i", "ghcr.io/x/y:1.0"])
    lenient = pf.check_server(server, config=ON, query=Seam([]).query)
    assert not lenient.refused
    assert lenient.reason == pf.REASON_UNSUPPORTED_LAUNCHER
    assert "docker" in lenient.detail

    strict = pf.check_server(server, config=STRICT, query=Seam([]).query)
    assert strict.refused
    assert strict.reason == pf.REASON_UNSUPPORTED_LAUNCHER


# -- what goes on the wire -------------------------------------------------

def test_only_the_package_coordinates_leave_the_machine(monkeypatch):
    """Halbert's MCP surface is a cloud pipeline: the entry, its env and
    its command line carry paths and sometimes tokens, and none of them
    may reach the advisory source."""
    seam = Seam([])
    monkeypatch.setattr(pf, "_osv_post", seam.post)

    pf.check_server(entry("npx", [
        "-y", "@scope/pkg@1.2.3", "/Users/eric/private",
        "--token", "sk-live-secret",
    ]), config=ON)

    assert seam.payloads == [{
        "package": {"name": "@scope/pkg", "ecosystem": "npm"},
        "version": "1.2.3",
    }]
    body = repr(seam.payloads[0])
    assert "eric" not in body and "sk-live" not in body and "npx" not in body


def test_a_pypi_name_is_normalized_before_it_goes_on_the_wire(monkeypatch):
    seam = Seam([])
    monkeypatch.setattr(pf, "_osv_post", seam.post)
    pf.check_server(entry("uvx", ["--from", "MCP_Server.Time==1.0.0", "x"]),
                    config=ON)
    assert seam.payloads[0]["package"] == {
        "name": "mcp-server-time", "ecosystem": "PyPI"}


# -- resolution ------------------------------------------------------------

@pytest.mark.parametrize("command,args,ecosystem,name,version", [
    ("npx", ["-y", "@scope/pkg@1.2.3"], "npm", "@scope/pkg", "1.2.3"),
    ("npx", ["pkg@0.1.0"], "npm", "pkg", "0.1.0"),
    ("npx", ["-p", "@scope/pkg@2.0.0", "server"], "npm", "@scope/pkg", "2.0.0"),
    ("npx", ["--package=@scope/pkg@2.0.0", "server"], "npm", "@scope/pkg", "2.0.0"),
    ("/usr/local/bin/npx", ["-y", "pkg@1.0.0"], "npm", "pkg", "1.0.0"),
    ("bunx", ["pkg@1.0.0"], "npm", "pkg", "1.0.0"),
    ("pnpm", ["dlx", "pkg@1.0.0"], "npm", "pkg", "1.0.0"),
    ("npm", ["exec", "pkg@1.0.0"], "npm", "pkg", "1.0.0"),
    ("uvx", ["mcp-server-time@1.2.0"], "PyPI", "mcp-server-time", "1.2.0"),
    ("uvx", ["--from", "mcp-server-time==1.2.0", "cmd"], "PyPI",
     "mcp-server-time", "1.2.0"),
    ("uvx", ["--from=pkg==1.0", "cmd"], "PyPI", "pkg", "1.0"),
    ("uvx", ["--python", "3.12", "pkg==1.0"], "PyPI", "pkg", "1.0"),
    ("uvx", ["pkg[extra]==1.0"], "PyPI", "pkg", "1.0"),
    ("uv", ["tool", "run", "pkg==1.0"], "PyPI", "pkg", "1.0"),
    ("pipx", ["run", "--spec", "pkg==1.0", "cmd"], "PyPI", "pkg", "1.0"),
    ("pipx", ["run", "pkg==1.0"], "PyPI", "pkg", "1.0"),
])
def test_resolvers(command, args, ecosystem, name, version):
    resolution = pf.resolve_package(command, args)
    assert resolution.kind == "package", resolution.detail
    assert resolution.identity == pf.PackageIdentity(ecosystem, name, version)


@pytest.mark.parametrize("command,args,kind", [
    # A local file: no registry has a record, so absent proceeds.
    ("/opt/thing/mcp-server", [], "no_package"),
    ("python3", ["/opt/thing/server.py"], "no_package"),
    ("node", ["/opt/thing/server.js"], "no_package"),
    # A package is right there and cannot be named: unobservable.
    ("python3", ["-m", "mcp_server_git"], "no_package"),
    ("npx", ["-y", "github:someone/repo"], "unresolvable"),
    ("npx", ["-y", "file:../local"], "unresolvable"),
    ("npx", [], "unresolvable"),
    ("uvx", ["git+https://example.invalid/x.git"], "unresolvable"),
    ("npx", ["-y", "NOT A NAME@1.0.0"], "unresolvable"),
    # A real ecosystem this module has no source for.
    ("docker", ["run", "x"], "unsupported_launcher"),
    ("go", ["run", "x"], "unresolvable"),
    ("cargo", ["install", "x"], "unsupported_launcher"),
])
def test_resolution_kinds(command, args, kind):
    assert pf.resolve_package(command, args).kind == kind


def test_the_scope_at_is_not_mistaken_for_a_version_separator():
    resolution = pf.resolve_package("npx", ["-y", "@scope/pkg"])
    assert resolution.kind == "unpinned"
    assert "@scope/pkg" in resolution.detail


def test_an_http_server_installs_nothing():
    result = pf.check_server(
        SimpleNamespace(name="linear", transport="http",
                        command="", args=(), url="https://example.invalid"),
        config=ON, query=Seam([]).query)
    assert not result.refused
    assert result.reason == pf.REASON_NO_PACKAGE


# -- severity --------------------------------------------------------------

@pytest.mark.parametrize("vector,expected", [
    # The v3.1 specification's own worked examples.
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H", 7.5),
    ("CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:N/A:N", 5.5),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1),
    ("CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0),
])
def test_cvss_v3_base_score(vector, expected):
    assert pf.cvss_v3_base_score(vector) == pytest.approx(expected, abs=0.05)


def test_a_v4_vector_is_not_scored_and_lands_in_could_not_tell():
    assert pf.cvss_v3_base_score("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N") is None
    assert pf.severity_of(advisory(cvss="CVSS:4.0/AV:N/AC:L")) == "UNKNOWN"


def test_a_cvss_vector_outranks_the_database_word():
    """The numeric score is the precise answer; the word is the fallback."""
    vuln = advisory(severity="LOW",
                    cvss="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
    assert pf.severity_of(vuln) == "CRITICAL"


def test_moderate_is_medium():
    assert pf.severity_of(advisory(severity="MODERATE")) == "MEDIUM"


def test_severity_is_taken_from_an_affected_range_when_that_is_where_it_is():
    vuln = {"id": "GHSA-x",
            "affected": [{"database_specific": {"severity": "HIGH"}}]}
    assert pf.severity_of(vuln) == "HIGH"


def test_the_worst_advisory_decides():
    seam = Seam([advisory("GHSA-a", severity="LOW"),
                 advisory("GHSA-b", severity="HIGH")])
    result = pf.check_server(
        entry(args=["-y", "pkg@1.0.0"]), config=ON, query=seam.query)
    assert result.refused
    assert result.severity == "HIGH"


# -- the entry controls these strings --------------------------------------

def test_a_planted_name_cannot_forge_a_log_record():
    resolution = pf.resolve_package(
        "npx", ["-y", "evil\n2026-01-01 CRITICAL cleared@1.0.0"])
    assert resolution.kind == "unresolvable"
    assert "\n" not in resolution.detail


def test_a_planted_advisory_id_is_flattened_and_capped():
    seam = Seam([advisory("GHSA-" + "x" * 500 + "\x1b[31m", severity="HIGH")])
    result = pf.check_server(
        entry(args=["-y", "pkg@1.0.0"]), config=ON, query=seam.query)
    assert result.refused
    identifier = result.advisories[0]
    assert len(identifier) <= 41
    assert "\x1b" not in identifier


def test_the_two_gates_read_differently():
    """entry_guard says 'this entry is not a server'; this one says
    'this server's package has a known problem'."""
    from halbert_core.mcp.entry_guard import validate_server_entry

    guard = validate_server_entry("s", {
        "transport": "stdio", "command": "sh", "args": ["-c", "curl x | sh"]})
    assert guard and all("entry" in f for f in guard)

    seam = Seam([advisory("GHSA-1", severity="HIGH")])
    result = pf.check_server(
        entry(args=["-y", "pkg@1.0.0"]), config=ON, query=seam.query)
    assert "package" in result.message("s")


# -- the operator's file ---------------------------------------------------

def _write_config(tmp_path, monkeypatch, text):
    monkeypatch.setattr("halbert_core.utils.platform.get_config_dir",
                        lambda: tmp_path)
    (tmp_path / pf.PREFLIGHT_CONFIG_NAME).write_text(text, encoding="utf-8")
    pf.reset_preflight_caches()


def test_the_switch_is_read_from_the_operators_file(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, "enabled: true\nstrict: true\n")
    config = pf.load_preflight_config()
    assert config.enabled is True and config.strict is True


def test_an_edit_lands_without_a_restart(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, "enabled: false\n")
    assert pf.is_enabled() is False
    import os
    path = tmp_path / pf.PREFLIGHT_CONFIG_NAME
    path.write_text("enabled: true\n", encoding="utf-8")
    os.utime(path, (0, 0))          # a changed signature, not a changed clock
    assert pf.is_enabled() is True


def test_a_malformed_file_leaves_the_gate_off_rather_than_killing_the_daemon(
        tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, "enabled: [this is not a bool\n")
    config = pf.load_preflight_config()
    assert config.enabled is False


def test_a_nonsense_timeout_falls_back_to_the_default(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch,
                  "enabled: true\ntimeout_seconds: -4\n")
    assert pf.load_preflight_config().timeout_seconds == 6.0


# -- the advisory source's own contract ------------------------------------
#
# Off unless HALBERT_LIVE_OSV=1. Everything above runs against fixtures, so
# the suite makes no network call — but the fixtures are only worth what
# they resemble, and the shapes here were taken from real answers on
# 2026-09-10 (lodash@4.17.20: five advisories, CVSS_V3 vectors, worst HIGH;
# left-pad@1.3.0: no 'vulns' key at all; requests@2.19.0 PyPI: MODERATE in
# database_specific). Run it when OSV's response shape is in question.

import os

live_only = pytest.mark.skipif(
    os.environ.get("HALBERT_LIVE_OSV") != "1",
    reason="set HALBERT_LIVE_OSV=1 to query the real advisory source")


@live_only
def test_live_a_known_vulnerable_npm_release_comes_back_high():
    identity = pf.PackageIdentity(pf.ECOSYSTEM_NPM, "lodash", "4.17.20")
    vulns = pf._query_osv(identity, 15.0)
    assert vulns, "lodash 4.17.20 has advisories on record"
    worst, _ = pf._worst(vulns)
    assert pf._SEVERITY_RANK[worst] >= pf._SEVERITY_RANK["HIGH"]


@live_only
def test_live_a_clean_release_comes_back_with_nothing():
    identity = pf.PackageIdentity(pf.ECOSYSTEM_NPM, "left-pad", "1.3.0")
    assert pf._query_osv(identity, 15.0) == []


@live_only
def test_live_pypi_is_spelled_the_way_osv_spells_it():
    identity = pf.PackageIdentity(pf.ECOSYSTEM_PYPI, "requests", "2.19.0")
    assert pf._query_osv(identity, 15.0), "OSV matched the PyPI coordinates"


@pytest.mark.parametrize("command,args,kind,phrase", [
    # `uv run` is not `uv tool run`; "pin it with ==" would be wrong advice.
    ("uv", ["run", "my-server"], "unresolvable", "project environment"),
    ("bun", ["run", "server.ts"], "no_package", "local script"),
    ("npm", ["start"], "no_package", "local script"),
    ("cargo", ["run"], "unsupported_launcher", "cargo"),
])
def test_the_refusal_says_which_one_it_was(command, args, kind, phrase):
    """'Say which it was' — a refusal that gives the wrong remedy is worse
    than one that gives none."""
    resolution = pf.resolve_package(command, args)
    assert resolution.kind == kind
    assert phrase in resolution.detail


# -- the launch-time gate's own three properties ---------------------------

@pytest.mark.asyncio
async def test_a_hung_advisory_source_cannot_hold_a_connect_open(monkeypatch):
    """Bounded by wall clock, not by whatever the socket decides."""
    import asyncio

    from halbert_core.mcp import client as client_mod
    from halbert_core.mcp.config import MCPServerConfig

    monkeypatch.setattr(
        pf, "load_preflight_config",
        lambda: pf.PreflightConfig(enabled=True, timeout_seconds=0.01))
    monkeypatch.setattr(client_mod, "PREFLIGHT_WALL_CLOCK_MARGIN", 0.0)

    async def _never(*args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(asyncio, "to_thread", _never)

    server = MCPServerConfig(name="s", transport="stdio", command="npx",
                             args=("-y", "pkg@1.0.0"))
    with pytest.raises(client_mod.MCPPreflightRefused) as excinfo:
        await asyncio.wait_for(
            client_mod.run_package_preflight(server), timeout=10)
    assert "timed out" in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_planted_server_name_cannot_forge_a_log_record(monkeypatch):
    from halbert_core.mcp import client as client_mod
    from halbert_core.mcp.config import MCPServerConfig

    monkeypatch.setattr(
        pf, "load_preflight_config", lambda: pf.PreflightConfig(enabled=True))
    monkeypatch.setattr(
        pf, "_query_osv",
        lambda identity, timeout: [advisory("GHSA-1", severity="HIGH")])

    server = MCPServerConfig(
        name="evil\n2026-01-01 INFO cleared", transport="stdio",
        command="npx", args=("-y", "pkg@1.0.0"))
    with pytest.raises(client_mod.MCPPreflightRefused) as excinfo:
        await client_mod.run_package_preflight(server)
    assert "\n" not in str(excinfo.value)


@pytest.mark.asyncio
async def test_a_module_that_cannot_even_run_is_the_switch_being_off(monkeypatch):
    """The gate's OFF state is the shipped one: a broken config file must
    not take the whole MCP surface down with it."""
    from halbert_core.mcp import client as client_mod
    from halbert_core.mcp.config import MCPServerConfig

    def _explode():
        raise RuntimeError("the config plane is on fire")

    monkeypatch.setattr(pf, "load_preflight_config", _explode)
    server = MCPServerConfig(name="s", transport="stdio", command="npx",
                             args=("-y", "pkg@1.0.0"))
    await client_mod.run_package_preflight(server)      # must not raise


@pytest.mark.asyncio
async def test_the_gate_runs_again_when_the_pinned_version_changes(monkeypatch):
    """'On a first launch and on a version change' — and a version change
    in the entry IS a config-signature change, which is what _ensure
    already rebuilds on."""
    from halbert_core.mcp import client as client_mod
    from halbert_core.mcp.config import MCPClientConfig, MCPServerConfig

    monkeypatch.setattr(
        pf, "load_preflight_config", lambda: pf.PreflightConfig(enabled=True))

    asked = []

    def _query(identity, timeout):
        asked.append(identity.version)
        return [advisory("GHSA-1", severity="HIGH")] if identity.version == "2.0.0" else []

    monkeypatch.setattr(pf, "_query_osv", _query)

    class _FakeTransport:
        alive = True

        async def connect(self):
            pass

        async def close(self):
            pass

    monkeypatch.setattr(client_mod, "build_transport", lambda cfg: _FakeTransport())

    version = {"v": "1.0.0"}

    def _load():
        return MCPClientConfig(servers=(MCPServerConfig(
            name="s", transport="stdio", command="npx",
            args=("-y", f"pkg@{version['v']}")),))

    client = client_mod.MCPClient(config_loader=_load)
    await client._ensure("s")
    await client._ensure("s")           # same signature: reused, not re-asked
    assert asked == ["1.0.0"]

    version["v"] = "2.0.0"              # the operator bumps the pin
    with pytest.raises(client_mod.MCPPreflightRefused):
        await client._ensure("s")
    assert asked == ["1.0.0", "2.0.0"]


# ==========================================================================
# The Fable review, 2026-09-10: R1, R2, R4, R5, R7, R8, R9, R10.
# ==========================================================================

def _ranged(identifier, severity, introduced="0", fixed=None,
            last_affected=None, versions=None, withdrawn=None):
    """One OSV record with a real ``affected`` shape."""
    events = [{"introduced": introduced}]
    if fixed:
        events.append({"fixed": fixed})
    if last_affected:
        events.append({"last_affected": last_affected})
    affected = {"database_specific": {"severity": severity}}
    if versions is not None:
        affected["versions"] = versions          # a closed enumeration
    else:
        affected["ranges"] = [{"type": "SEMVER", "events": events}]
    vuln = {"id": identifier, "affected": [affected]}
    if withdrawn:
        vuln["withdrawn"] = withdrawn
    return vuln


# -- R1: the unpinned entry gets a package-level answer ---------------------

def test_unpinned_refuses_on_a_malware_record():
    """The one thing a package-level answer settles outright."""
    seam = Seam([advisory("MAL-2026-1", malicious=True)])
    result = pf.check_server(entry(args=["-y", "pkg"]), config=ON,
                             query=seam.query)
    assert result.refused
    assert result.reason == pf.REASON_MALWARE
    assert "unpinned" in result.detail


def test_unpinned_refuses_on_an_open_range_high():
    """An open range means the launch-time release is affected by
    construction, so this is not a guess."""
    seam = Seam([_ranged("GHSA-open", "HIGH")])
    result = pf.check_server(entry(args=["-y", "pkg"]), config=ON,
                             query=seam.query)
    assert result.refused
    assert result.reason == pf.REASON_ADVISORY
    assert "open" in result.detail


def test_unpinned_only_warns_when_the_high_advisory_is_already_fixed():
    """Measured against the real API: a package-level hit is routinely true
    of a package whose current release is clean. Refusing on it would be a
    false alarm on the commonest real MCP entry."""
    seam = Seam([_ranged("GHSA-fixed", "CRITICAL", fixed="2.0.0")])
    result = pf.check_server(entry(args=["-y", "pkg"]), config=ON,
                             query=seam.query)
    assert not result.refused
    assert result.reason == pf.REASON_UNPINNED
    assert "pin" in result.detail.lower()


def test_unpinned_warns_when_the_open_advisory_is_below_high():
    seam = Seam([_ranged("GHSA-lowopen", "LOW")])
    assert not pf.check_server(entry(args=["-y", "pkg"]), config=ON,
                               query=seam.query).refused


def test_the_package_level_query_carries_no_version_at_all(monkeypatch):
    seam = Seam([])
    monkeypatch.setattr(pf, "_osv_post", seam.post)
    pf.check_server(entry(args=["-y", "@scope/pkg"]), config=ON)
    assert seam.payloads == [
        {"package": {"name": "@scope/pkg", "ecosystem": "npm"}}]


def test_the_package_level_answer_has_its_own_cache_key():
    seam = Seam([])
    pf.check_server(entry(args=["-y", "pkg"]), config=ON, query=seam.query)
    pf.check_server(entry(args=["-y", "pkg@1.0.0"]), config=ON, query=seam.query)
    assert [c[0].version for c in seam.calls] == ["", "1.0.0"]


# -- R7: the range test reads ranges, not severity -------------------------

@pytest.mark.parametrize("vuln,expected", [
    (_ranged("a", "HIGH"), True),                                # open
    (_ranged("b", "HIGH", fixed="2.0.0"), False),                # fixed
    (_ranged("c", "HIGH", last_affected="1.9.9"), False),        # capped
    (_ranged("d", "HIGH", versions=["1.0.0", "1.0.1"]), False),  # enumerated
    # re-introduced after a fix: still open at the top
    ({"id": "e", "affected": [{"ranges": [{"events": [
        {"introduced": "0"}, {"fixed": "1.0"}, {"introduced": "2.0"}]}]}]}, True),
    ({"id": "f"}, False),
])
def test_has_open_range_reads_the_events_not_the_severity(vuln, expected):
    assert pf.has_open_range(vuln) is expected


def test_an_explicit_version_list_is_closed_by_construction():
    """A finite list cannot contain 'the next release'."""
    seam = Seam([_ranged("GHSA-list", "CRITICAL", versions=["1.0.0"])])
    assert not pf.check_server(entry(args=["-y", "pkg"]), config=ON,
                               query=seam.query).refused


def test_a_withdrawn_advisory_is_skipped_at_every_severity():
    """A withdrawn HIGH refusing a clean package is how a gate gets
    switched off."""
    seam = Seam([_ranged("GHSA-gone", "CRITICAL", withdrawn="2026-01-01T00:00:00Z")])
    result = pf.check_server(entry(args=["-y", "pkg@1.0.0"]), config=ON,
                             query=seam.query)
    assert not result.refused
    assert result.reason == pf.REASON_CLEAN, "a withdrawn-only answer is clean"


def test_a_withdrawn_record_does_not_inflate_the_advisory_count():
    seam = Seam([_ranged("GHSA-gone", "CRITICAL", withdrawn="2026-01-01T00:00:00Z"),
                 _ranged("GHSA-real", "LOW", fixed="2.0.0")])
    result = pf.check_server(entry(args=["-y", "pkg@1.0.0"]), config=ON,
                             query=seam.query)
    assert not result.refused
    assert result.advisories == ("GHSA-real",)
    assert "1 advisory" in result.detail


# -- R8: strict + unpinned refuses without egress --------------------------

def test_strict_refuses_an_unpinned_entry_without_querying(monkeypatch):
    """The outcome is fixed before the request, so no request is made."""
    seam = Seam([])
    monkeypatch.setattr(pf, "_osv_post", seam.post)
    result = pf.check_server(entry(args=["-y", "pkg"]), config=STRICT)
    assert result.refused
    assert result.reason == pf.REASON_UNPINNED
    assert seam.payloads == [], "a deterministic refusal needs no egress"


# -- R2: the line is fetch-at-launch ---------------------------------------

@pytest.mark.parametrize("command,args", [
    ("python3", ["-m", "mcp_server_git"]),
    ("python", ["-m", "some.module", "--flag"]),
    ("node", ["/opt/thing/server.js"]),
    ("/opt/thing/mcp-server", []),
    ("go", ["run", "./cmd/server"]),
])
def test_a_launcher_that_fetches_nothing_proceeds(command, args):
    seam = Seam([advisory("MAL-1", malicious=True)])
    result = pf.check_server(entry(command, args), config=ON, query=seam.query)
    assert not result.refused
    assert result.reason == pf.REASON_NO_PACKAGE
    assert seam.calls == []


@pytest.mark.parametrize("command,args", [
    ("npx", ["-y", "github:someone/repo"]),
    ("npx", ["-y", "https://example.invalid/x.tgz"]),
    ("uvx", ["git+https://example.invalid/x.git"]),
    ("go", ["run", "not a module@v1.0.0"]),
])
def test_a_fetching_launcher_that_cannot_be_named_still_refuses(command, args):
    result = pf.check_server(entry(command, args), config=ON,
                             query=Seam([]).query)
    assert result.refused
    assert result.reason == pf.REASON_UNRESOLVABLE


def test_yarn_dlx_is_an_npm_launcher():
    assert pf.resolve_package("yarn", ["dlx", "pkg@1.0.0"]).identity == \
        pf.PackageIdentity("npm", "pkg", "1.0.0")


# -- R4 / R5: Go and Deno ---------------------------------------------------

@pytest.mark.parametrize("command,args,ecosystem,name,version", [
    ("go", ["run", "github.com/x/y/cmd@v1.2.3"], "Go", "github.com/x/y/cmd", "1.2.3"),
    ("go", ["run", "example.com/m@1.2.3"], "Go", "example.com/m", "1.2.3"),
    ("deno", ["run", "-A", "npm:@scope/pkg@1.2.3"], "npm", "@scope/pkg", "1.2.3"),
    ("deno", ["run", "npm:pkg@1.0.0"], "npm", "pkg", "1.0.0"),
])
def test_the_new_resolvers(command, args, ecosystem, name, version):
    assert pf.resolve_package(command, args).identity == \
        pf.PackageIdentity(ecosystem, name, version)


def test_the_go_v_prefix_is_normalised_so_the_cache_keys_on_one_spelling():
    with_v = pf.resolve_package("go", ["run", "example.com/m@v1.2.3"]).identity
    without = pf.resolve_package("go", ["run", "example.com/m@1.2.3"]).identity
    assert with_v == without


def test_jsr_has_no_advisory_source_and_says_so():
    r = pf.resolve_package("deno", ["run", "jsr:@scope/pkg@1.0.0"])
    assert r.kind == "unsupported_launcher"
    assert "JSR" in r.detail


def test_a_go_module_with_a_known_advisory_refuses():
    seam = Seam([_ranged("GO-2026-1", "HIGH", fixed="9.9.9")])
    result = pf.check_server(
        entry("go", ["run", "github.com/x/y@v1.0.0"]), config=ON, query=seam.query)
    assert result.refused
    assert seam.calls[0][0].ecosystem == "Go"


# -- R10: a redirected registry makes the coordinate a lie -----------------

@pytest.mark.parametrize("key", [
    "NPM_CONFIG_REGISTRY", "npm_config_registry", "PIP_INDEX_URL",
    "UV_INDEX_URL", "UV_DEFAULT_INDEX", "GOPROXY", "YARN_REGISTRY",
    "npm_config_@myscope:registry",
])
def test_a_redirected_registry_in_the_entry_env_refuses(key):
    server = SimpleNamespace(
        name="s", transport="stdio", command="npx",
        args=("-y", "pkg@1.0.0"), env={key: "https://evil.invalid/"})
    seam = Seam([])
    result = pf.check_server(server, config=ON, query=seam.query)
    assert result.refused
    assert result.reason == pf.REASON_UNRESOLVABLE
    assert key in result.detail
    assert seam.calls == [], "a coordinate known to be a lie is not put on the wire"


def test_the_redirect_check_never_reads_the_value():
    """Those values are routinely URLs with a token in them."""
    server = SimpleNamespace(
        name="s", transport="stdio", command="npx", args=("-y", "pkg@1.0.0"),
        env={"NPM_CONFIG_REGISTRY": "https://user:sk-secret@evil.invalid/"})
    result = pf.check_server(server, config=ON, query=Seam([]).query)
    assert "sk-secret" not in result.detail
    assert "sk-secret" not in result.message("s")


def test_an_ordinary_env_still_resolves():
    server = SimpleNamespace(
        name="s", transport="stdio", command="npx", args=("-y", "pkg@1.0.0"),
        env={"HOME": "/Users/eric", "MY_TOKEN": "x"})
    seam = Seam([])
    assert not pf.check_server(server, config=ON, query=seam.query).refused
    assert len(seam.calls) == 1


def test_a_redirect_on_a_non_fetching_entry_is_not_the_gates_business():
    server = SimpleNamespace(
        name="s", transport="stdio", command="/opt/thing/server",
        args=(), env={"GOPROXY": "https://elsewhere.invalid"})
    assert not pf.check_server(server, config=ON, query=Seam([]).query).refused


# -- R9: a warning the operator never sees is a pass -----------------------

class _RecordingStore:
    def __init__(self):
        self.added = []

    def find_by_detector_title(self, detector, title):
        for f in self.added:
            if f.detector == detector and f.title == title:
                return f
        return None

    def add(self, finding):
        finding.id = finding.id or f"id-{len(self.added)}"
        self.added.append(finding)
        return finding.id


@pytest.mark.parametrize("vulns,reason,severity", [
    ([_ranged("GHSA-fixed", "CRITICAL", fixed="2.0.0")], pf.REASON_UNPINNED, "warning"),
    ([advisory("MAL-1", malicious=True)], pf.REASON_MALWARE, "critical"),
])
def test_every_reportable_outcome_reaches_the_findings_surface(
        vulns, reason, severity):
    """Asserted on the FINDING, not on a log line — for the same reason the
    switch-off test asserts on the HTTP seam."""
    store = _RecordingStore()
    result = pf.check_server(entry(args=["-y", "pkg"]), config=ON,
                             query=Seam(vulns).query)
    assert result.reason == reason
    pf.report_finding("filesystem", result, store=store)

    assert len(store.added) == 1
    finding = store.added[0]
    assert finding.detector == pf.FINDING_DETECTOR
    assert finding.severity == severity
    assert "filesystem" in finding.title
    assert finding.affected_services == ["filesystem"]
    assert finding.why_now and finding.why_care and finding.why_so


def test_a_healthy_launch_files_nothing():
    store = _RecordingStore()
    clean = pf.check_server(entry(args=["-y", "pkg@1.0.0"]), config=ON,
                            query=Seam([]).query)
    pf.report_finding("s", clean, store=store)
    pf.report_finding("s", pf.check_server(entry("/opt/x"), config=ON,
                                           query=Seam([]).query), store=store)
    assert store.added == [], "a finding raised on every healthy launch is noise"


def test_relaunching_the_same_server_does_not_stack_findings():
    store = _RecordingStore()
    result = pf.check_server(entry(args=["-y", "pkg"]), config=ON,
                             query=Seam([advisory("MAL-1", malicious=True)]).query)
    first = pf.report_finding("s", result, store=store)
    second = pf.report_finding("s", result, store=store)
    assert first == second
    assert len(store.added) == 1


def test_a_broken_findings_store_never_stops_a_launch():
    class _Broken:
        def find_by_detector_title(self, *a):
            raise RuntimeError("database is locked")

    result = pf.check_server(entry(args=["-y", "pkg"]), config=ON,
                             query=Seam([]).query)
    assert pf.report_finding("s", result, store=_Broken()) is None


@pytest.mark.asyncio
async def test_the_client_files_the_finding_on_the_way_past(monkeypatch):
    from halbert_core.mcp import client as client_mod
    from halbert_core.mcp.config import MCPClientConfig, MCPServerConfig

    monkeypatch.setattr(
        pf, "load_preflight_config", lambda: pf.PreflightConfig(enabled=True))
    monkeypatch.setattr(pf, "_query_osv",
                        lambda i, t: [_ranged("GHSA-f", "HIGH", fixed="9.0.0")])
    filed = []
    monkeypatch.setattr(pf, "report_finding",
                        lambda name, result, store=None: filed.append((name, result)))

    class _FakeTransport:
        alive = True

        async def connect(self): pass

        async def close(self): pass

    monkeypatch.setattr(client_mod, "build_transport", lambda c: _FakeTransport())
    server = MCPServerConfig(name="fs", transport="stdio", command="npx",
                             args=("-y", "pkg"))
    client = client_mod.MCPClient(
        config_loader=lambda: MCPClientConfig(servers=(server,)))
    await client._ensure("fs")          # a WARN outcome: it launches

    assert len(filed) == 1
    assert filed[0][0] == "fs"
    assert not filed[0][1].refused


# -- R3: the switch is where an unconfirmed write cannot reach -------------

def test_the_switch_lives_beside_the_config_it_governs():
    from halbert_core.utils.platform import get_config_dir

    assert pf._config_path().parent == get_config_dir()


def test_a_write_to_the_switch_requires_confirmation():
    """R3's whole point, asserted against the real classifier: at MEDIUM
    the agent could turn its own gate off without asking."""
    from halbert_core.tools.safety import ToolSafetyFramework

    result = ToolSafetyFramework().classify(
        "write_file", {"path": str(pf._config_path()), "content": "enabled: false"})
    assert result.risk_level.value == "high"


# ==========================================================================
# Adversarial pass, 2026-09-10. Every test here pins a defect that was in
# the code and is not any more.
# ==========================================================================

@pytest.mark.parametrize("spec,name", [
    # npm only started requiring lowercase around 2017; what shipped before
    # is still installable, and a lowercase-only grammar refused it.
    ("JSONStream@1.3.5", "JSONStream"),
    ("@Scope/Pkg@1.0.0", "@Scope/Pkg"),
    ("Base64@1.0.0", "Base64"),
])
def test_a_legacy_uppercase_npm_name_is_a_real_package_not_a_malformed_one(
        spec, name):
    resolution = pf.resolve_package("npx", ["-y", spec])
    assert resolution.kind == "package", resolution.detail
    assert resolution.identity.name == name, "the case is carried, not folded"


def test_a_malware_refusal_names_the_malware_record_not_the_first_six():
    """The id cap used to list whichever advisories came back first, so a
    refusal could cite six unrelated LOW findings and never the MAL-
    record it actually refused on."""
    vulns = [advisory(f"GHSA-noise{i}", severity="LOW") for i in range(8)]
    vulns.append(advisory("MAL-2026-999"))
    result = pf.check_server(entry(args=["-y", "pkg@1.0.0"]), config=ON,
                             query=Seam(vulns).query)
    assert result.reason == pf.REASON_MALWARE
    assert result.advisories == ("MAL-2026-999",)


def test_a_severity_refusal_names_the_advisory_that_caused_it():
    vulns = [advisory(f"GHSA-noise{i}", severity="LOW") for i in range(8)]
    vulns.append(advisory("GHSA-thebadone", severity="CRITICAL"))
    result = pf.check_server(entry(args=["-y", "pkg@1.0.0"]), config=ON,
                             query=Seam(vulns).query)
    assert result.refused
    assert result.advisories == ("GHSA-thebadone",)
    assert "GHSA-thebadone" in result.message("s")


def test_the_real_malware_record_shape_is_recognised_without_the_id_prefix():
    """Measured from api.osv.dev: the feed writes
    ``malicious-packages-origins``, not a ``malicious`` flag — the arm that
    checked the latter never fired on real data."""
    assert pf._is_malware({
        "id": "OSV-2026-1",
        "database_specific": {"malicious-packages-origins": [{"source": "x"}]},
    }) is True


def test_two_package_flags_install_two_packages_and_are_refused():
    """`npx -p safe -p evil cmd` installs both; clearing the first would
    let the second ride in behind it."""
    resolution = pf.resolve_package(
        "npx", ["-p", "safe@1.0.0", "-p", "evil@1.0.0", "cmd"])
    assert resolution.kind == "unresolvable"
    assert "2 packages" in resolution.detail


def test_one_package_flag_still_resolves():
    assert pf.resolve_package(
        "npx", ["-p", "pkg@1.0.0", "cmd"]).identity == \
        pf.PackageIdentity("npm", "pkg", "1.0.0")


@pytest.mark.parametrize("command,args", [
    # A launcher flag that eats its value must not leave the value looking
    # like a package. Each of these refuses rather than querying wrongly.
    ("go", ["run", "-exec", "wrapper", "example.com/m@v1.0.0"]),
    ("uvx", ["--from"]),
])
def test_an_ambiguous_launcher_argv_refuses_rather_than_guessing(command, args):
    assert pf.resolve_package(command, args).kind == "unresolvable"


def test_a_deno_flag_carrying_an_npm_prefix_is_not_the_package():
    resolution = pf.resolve_package(
        "deno", ["run", "--allow-net=npm:evil", "npm:real@1.0.0"])
    assert resolution.identity == pf.PackageIdentity("npm", "real", "1.0.0")
