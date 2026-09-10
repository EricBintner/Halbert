# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Ask an advisory source about the package an MCP entry would install (FD-10).

``entry_guard.py`` screens the *shape* of a config entry: a shell with an
inline script, a fetch piped into an interpreter, a write to a
persistence surface. It is deterministic, offline, and it says nothing at
all about what ``npx -y @scope/pkg@1.2.3`` will pull down. That is the
gap FD-10 named, and this is the second gate that closes it: resolve what
the entry would actually install, ask OSV whether that exact artifact has
a known advisory, and refuse the SERVER — never the daemon — when it does.

The two gates produce different findings and should read differently.
``entry_guard`` says *this entry is not a server*. This one says *this
server's package has a known problem*.

Opt-in, and off by default
--------------------------
This is the only outbound request the MCP client makes on its own behalf,
on a machine whose whole posture is local-first, so it is a thing the
operator switches on: ``mcp_preflight_config.yml`` under the data
directory beside ``mcp_config.yml`` and ``vision_config.yml`` — read on
every call, cached on the file's own ``(mtime_ns, size)`` signature so an
edit lands without a restart. With the switch off nothing is resolved and
nothing is queried.

It is in the CONFIG directory and not the data directory for a measured
reason (R3): a write to the data directory classifies MEDIUM in
``tools/safety.py`` — no confirmation — so a gate whose switch lived there
could be turned off by the agent's own ``write_file`` without asking. The
config directory classifies HIGH. See :func:`_config_path`.

What is sent
------------
The package coordinates and nothing else: ``{"package": {"name":
..., "ecosystem": ...}, "version": ...}``. Not the entry, not the
command line, not the environment — those carry filesystem paths and
sometimes bearer tokens, and Halbert's MCP surface is a cloud pipeline.
:func:`_query_osv` builds that body from the three resolved fields only,
and a test asserts on the body.

The three-way split
-------------------
The rule the scheduler and the discovery scanners already run on: absent
tooling proceeds, *unobservable* tooling refuses with the uncertainty
named. Applied here, and this is the whole policy:

=============================  ===============  ===============
outcome                        default          ``strict: true``
=============================  ===============  ===============
fetches nothing at launch      proceed          proceed
no advisory                    proceed          proceed
advisory, HIGH or CRITICAL     REFUSE           REFUSE
a malware record (``MAL-``)    REFUSE           REFUSE
advisory, below HIGH           warn, proceed    REFUSE
advisory, severity unknown     warn, proceed    REFUSE
launcher with no source        note, proceed    REFUSE
unpinned, package has malware  REFUSE           REFUSE
unpinned, open HIGH/CRITICAL   REFUSE           REFUSE
unpinned, anything else        warn, proceed    REFUSE (no query)
redirected registry in env     REFUSE           REFUSE
package not identifiable       REFUSE           REFUSE
source unreachable             REFUSE           REFUSE
=============================  ===============  ===============

``strict`` means "refuse anything I could not positively clear". Under it
an unpinned entry is refused WITHOUT a request (R8): the outcome is fixed
before the question, so asking would be egress for nothing.

Every warn row above reaches the operator's findings surface, not only a
log line — :func:`report_finding`, R9. A warning nobody sees is a pass.

The line: does it fetch at launch?
----------------------------------
Not "can I name the package". ``npx``/``bunx``/``uvx``/``pipx run``/
``npm exec``/``pnpm dlx``/``yarn dlx``/``deno run npm:``/``go run mod@v``
pull an artifact from a public registry at launch, so what runs is decided
at launch and must be preflighted. ``python -m mcp_server_git``, a bare
path, ``node server.js`` and ``go run ./cmd`` do not — the operator
installed that deliberately, earlier. Refusing those claimed a protection
this gate cannot deliver, since it cannot see inside the child's
environment. Stated cost: a compromised release already installed in that
environment is not caught here, and never was.

An unpinned entry is the middle case and gets a package-level answer (R1):
conclusive for a malware record and for a HIGH/CRITICAL advisory whose
range is still open (:func:`has_open_range` — the launch-time artifact is
inside an open range by construction), and a warning for everything else,
because measured against the real API a package-level hit is routinely
true of a package whose current release is clean.

An advisory source cannot tell "this release has no advisory" from "no
such package": a typo'd or not-yet-published name answers CLEAN, because
OSV has nothing to say about it either way. Closing that would mean a
second request to a second host (the registry) on every launch, which is
not a trade this module makes — the entry guard and the operator's own
eyes are what stand between a typo and a launch.

Known gaps, stated rather than papered over: ``docker``/``podman``,
``cargo``, ``gem`` and ``mvn`` fetch at launch from ecosystems this module
has no advisory source for, and land in ``unsupported_launcher`` — a note
by default, a refusal under ``strict``; vetting a container image would
mean pulling the thing being vetted. ``jsr:`` is the same. CVSS v4 vectors
are not scored — measured across 694 real advisories, v4-only-with-no-
severity-word is 2.2% of records and never stands alone, and 0 of 18 real
pinned releases fold to "severity unknown".

Findings name the package and its advisory ids, which is the point of the
finding — but a planted config controls those strings, so every one of
them goes through :func:`_safe` before it reaches a log line or an error
message, and a name that does not match its ecosystem's grammar is
``unresolvable`` rather than a query.
"""
from __future__ import annotations

import enum
import json
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("halbert.mcp.preflight")

__all__ = [
    "FINDING_DETECTOR",
    "OSV_QUERY_URL",
    "PREFLIGHT_CONFIG_NAME",
    "PackageIdentity",
    "PreflightConfig",
    "PreflightResult",
    "Resolution",
    "Verdict",
    "check_server",
    "cvss_v3_base_score",
    "has_open_range",
    "is_enabled",
    "is_withdrawn",
    "load_preflight_config",
    "report_finding",
    "reset_preflight_caches",
    "resolve_package",
    "severity_of",
]

#: OSV's public query endpoint. No API key, no account, no per-caller
#: identity — the request carries the coordinates and nothing that would
#: tie them to this host. Deliberately a module constant and not a config
#: key: an operator-settable endpoint would make this switch a way to
#: point Halbert's only MCP-side egress at an arbitrary host.
OSV_QUERY_URL = "https://api.osv.dev/v1/query"

#: Beside the other operator files under the data directory, in the shape
#: ``vision_config.yml`` and ``skills_config.yml`` established.
PREFLIGHT_CONFIG_NAME = "mcp_preflight_config.yml"

#: OSV's own ecosystem spellings. Not lowercased anywhere — "PyPI" is
#: the literal the API matches on.
ECOSYSTEM_NPM = "npm"
ECOSYSTEM_PYPI = "PyPI"
ECOSYSTEM_GO = "Go"


# ---------------------------------------------------------------------------
# Result vocabulary
# ---------------------------------------------------------------------------

class Verdict(enum.Enum):
    PROCEED = "proceed"
    REFUSE = "refuse"


#: Every ``reason`` slug this module can return, so a caller can branch on
#: one without matching prose. ``clean`` and ``no_package`` are the only
#: two that mean "positively cleared".
REASON_DISABLED = "disabled"
REASON_CLEAN = "clean"
REASON_NO_PACKAGE = "no_package"
REASON_UNSUPPORTED_LAUNCHER = "unsupported_launcher"
REASON_ADVISORY = "advisory"
REASON_MALWARE = "malware"
REASON_UNRESOLVABLE = "unresolvable"
REASON_UNPINNED = "unpinned"
REASON_UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class PackageIdentity:
    """The three fields that go on the wire, and nothing else."""

    ecosystem: str
    name: str
    version: str

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.ecosystem, self.name, self.version)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.name}@{self.version} ({self.ecosystem})"


@dataclass(frozen=True)
class Resolution:
    """What the entry's command line turned out to be.

    ``kind`` is one of ``package``, ``no_package``, ``unsupported_launcher``,
    ``unpinned`` or ``unresolvable``. ``detail`` is already sanitized and
    safe to log.
    """

    kind: str
    detail: str
    identity: Optional[PackageIdentity] = None


@dataclass(frozen=True)
class PreflightResult:
    verdict: Verdict
    reason: str
    detail: str
    advisories: Tuple[str, ...] = ()
    severity: Optional[str] = None
    #: True only if a request actually went out (a cache hit is False).
    queried: bool = False

    @property
    def refused(self) -> bool:
        return self.verdict is Verdict.REFUSE

    def message(self, server_name: str) -> str:
        """The line a caller logs or raises with. Never carries the
        entry's own strings beyond the sanitized package coordinates."""
        ids = f" [{', '.join(self.advisories)}]" if self.advisories else ""
        return (f"MCP server '{_safe(server_name, 64)}': package preflight "
                f"{self.reason} — {self.detail}{ids}")


# ---------------------------------------------------------------------------
# The operator's switch
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PreflightConfig:
    enabled: bool = False
    strict: bool = False
    timeout_seconds: float = 6.0
    cache_ttl_seconds: float = 21600.0


_CONFIG_LOCK = threading.Lock()
_CONFIG_CACHE: Optional[Tuple[Tuple[str, int, int], PreflightConfig]] = None


def _config_path() -> Path:
    """Beside ``mcp_config.yml``, the file this switch governs.

    R3, and it is a security property rather than a tidiness one. Measured
    on 2026-09-10 with Halbert's own classifier: a ``write_file`` to the
    data directory classifies MEDIUM — no confirmation — so with the switch
    living there the agent could turn its own gate off without asking. The
    same write to the config directory classifies HIGH. ``mcp_config.yml``
    and ``vision_config.yml`` are both already here, and ``vision_config``
    is the right sibling to follow: it is a gate, where
    ``skills_config.yml`` is a preference list.
    """
    try:
        from ..utils.platform import get_config_dir

        return Path(get_config_dir()) / PREFLIGHT_CONFIG_NAME
    except Exception:  # pragma: no cover - platform module always imports
        return Path.home() / ".halbert" / PREFLIGHT_CONFIG_NAME


def _positive_float(raw: Any, default: float, key: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("%s: %s is not a number, using %s",
                       PREFLIGHT_CONFIG_NAME, key, default)
        return default
    if value <= 0:
        logger.warning("%s: %s must be positive, using %s",
                       PREFLIGHT_CONFIG_NAME, key, default)
        return default
    return value


def load_preflight_config() -> PreflightConfig:
    """The operator's switch, or the shipped default (everything off).

    Cached on the file's own ``(mtime_ns, size)`` — the signature the
    reload plane uses — so an edit lands without a restart and an
    unchanged file is not reparsed once per launch.

    A malformed file enables nothing. This is a security gate whose OFF
    state is the shipped one; a YAML typo must not turn it on, and it
    must not turn a working daemon into a dead one either.
    """
    global _CONFIG_CACHE
    path = _config_path()
    try:
        st = path.stat()
        signature = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        signature = (str(path), -1, -1)
    with _CONFIG_LOCK:
        cached = _CONFIG_CACHE
    if cached is not None and cached[0] == signature:
        return cached[1]

    config = PreflightConfig()
    if signature[1] >= 0:
        try:
            import yaml

            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config = PreflightConfig(
                    enabled=bool(loaded.get("enabled", False)),
                    strict=bool(loaded.get("strict", False)),
                    timeout_seconds=_positive_float(
                        loaded.get("timeout_seconds", 6.0), 6.0,
                        "timeout_seconds"),
                    cache_ttl_seconds=_positive_float(
                        loaded.get("cache_ttl_seconds", 21600.0), 21600.0,
                        "cache_ttl_seconds"),
                )
            elif loaded is not None:
                logger.warning("%s is not a mapping; the preflight stays off",
                               path)
        except Exception as e:
            logger.warning(
                "could not read %s (%s: %s); the preflight stays off",
                path, type(e).__name__, e)
    with _CONFIG_LOCK:
        _CONFIG_CACHE = (signature, config)
    return config


def is_enabled() -> bool:
    """Cheap enough to call on every connect: one stat when the config is
    unchanged, and the answer is ``False`` when the file is absent."""
    return load_preflight_config().enabled


# ---------------------------------------------------------------------------
# Sanitization — the entry controls these strings
# ---------------------------------------------------------------------------

_UNSAFE = re.compile(r"[^\x20-\x7e]")


def _safe(text: Any, limit: int = 128) -> str:
    """One entry-controlled string, made safe to put in a log line.

    Control characters (an ANSI escape, a newline that forges a second log
    record) become ``?``, and the result is capped. A screen that echoes
    what it screened is how a gate becomes an amplifier.
    """
    flat = _UNSAFE.sub("?", str(text))
    if len(flat) > limit:
        return flat[:limit] + "…"
    return flat


# ---------------------------------------------------------------------------
# Resolvers: what would this command line install?
# ---------------------------------------------------------------------------

#: npm's own grammar (package.json name rules), tightened to what a
#: registry name can actually be. A name that fails this is not queried.
#:
#: Uppercase is ALLOWED and not folded: npm only started requiring
#: lowercase around 2017 and the packages published before that are still
#: installable — ``JSONStream`` is one, and a lowercase-only grammar
#: refused it as malformed, which under this gate means refusing a real
#: server over a real package. OSV matches the name as published, so the
#: case is carried through untouched.
_NPM_NAME = re.compile(
    r"^(?:@[A-Za-z0-9][A-Za-z0-9._~-]*/)?[A-Za-z0-9][A-Za-z0-9._~-]*$")

#: PEP 508 name. Normalized to PEP 503 form before it goes on the wire.
_PYPI_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")

#: An exact semver, and only an exact semver. ``^1.2.3``, ``~1.2``,
#: ``latest`` and ``>=1`` all resolve to "whatever is published now".
_SEMVER_EXACT = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

#: PEP 440, permissively: enough to reject a range or a marker.
_PEP440_EXACT = re.compile(r"^[0-9][0-9A-Za-z.!+_-]*$")

#: Launchers that FETCH from a public registry at launch and whose
#: ecosystem this module has no advisory source for. They are the genuine
#: could-not-tell: a note by default, a refusal under ``strict``. Named
#: individually so the refusal can say which one it was.
_UNSUPPORTED_LAUNCHERS = frozenset({
    "docker", "podman", "nerdctl", "cargo", "gem", "bundle",
    "dotnet", "mvn",
})

_NPM_LAUNCHERS = frozenset({"npx", "bunx", "pnpx"})
_PY_LAUNCHERS = frozenset({"uvx", "pipx"})
_PY_INTERPRETERS = re.compile(r"^python[0-9.]*$")

#: ``npx``/``bunx`` flags that consume the token after them, so the
#: package is not mistaken for a flag's value. ``--package``/``-p`` is the
#: one whose value IS the package.
_NPX_VALUE_FLAGS = frozenset({
    "-p", "--package", "-c", "--call", "--node-arg", "--npm", "--shell",
    "--userconfig", "--cache", "--registry", "--scope",
})
_NPX_PACKAGE_FLAGS = frozenset({"-p", "--package"})

#: ``uvx`` flags that consume a value. ``--from`` is the one that names
#: the distribution when the command name differs from it.
_UVX_VALUE_FLAGS = frozenset({
    "--from", "--with", "--with-requirements", "--with-editable", "-p",
    "--python", "--index", "--index-url", "--extra-index-url",
    "--default-index", "--find-links", "-f", "--constraints", "-c",
    "--overrides", "--index-strategy", "--keyring-provider",
    "--exclude-newer", "--cache-dir", "--project", "--directory",
    "--refresh-package", "--no-project", "--config-file",
})
_PIPX_VALUE_FLAGS = frozenset({
    "--spec", "--python", "--index-url", "--pip-args", "--verbose",
})


def _basename(command: str) -> str:
    return command.replace("\\", "/").rsplit("/", 1)[-1].strip()


def _split_flag(token: str) -> Tuple[str, Optional[str]]:
    """``--from=spec`` -> ``("--from", "spec")``; otherwise ``(token, None)``."""
    if token.startswith("-") and "=" in token:
        head, _, tail = token.partition("=")
        return head, tail
    return token, None


def _positionals(args: Sequence[str], value_flags: frozenset,
                 capture: frozenset = frozenset()) -> Tuple[List[str], Optional[str]]:
    """Split a launcher's argv into positionals and the captured flag value.

    Stops at ``--``: everything after it belongs to the launched program,
    not the launcher. An unknown ``-``-prefixed token is treated as a
    boolean flag — if that guess is wrong the token we pick will fail its
    ecosystem's name grammar, which is ``unresolvable`` rather than a
    confidently wrong query.
    """
    positional: List[str] = []
    captured: Optional[str] = None
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            index += 1
            positional.extend(args[index:])
            break
        head, inline = _split_flag(token)
        if head.startswith("-") and head != "-":
            if inline is not None:
                if head in capture and captured is None:
                    captured = inline
            elif head in value_flags:
                index += 1
                if index < len(args):
                    if head in capture and captured is None:
                        captured = args[index]
            index += 1
            continue
        positional.append(token)
        index += 1
    return positional, captured


def _npm_spec(spec: str) -> Resolution:
    """``@scope/pkg@1.2.3`` -> an identity; anything looser -> why not."""
    raw = spec.strip()
    if not raw:
        return Resolution("unresolvable", "the entry names no package")
    lowered = raw.lower()
    for prefix in ("file:", "link:", "git+", "git:", "github:", "gitlab:",
                   "bitbucket:", "http:", "https:", "npm:", "."):
        if lowered.startswith(prefix):
            return Resolution(
                "unresolvable",
                f"the package is fetched as '{_safe(prefix.rstrip(':'), 16)}' "
                f"rather than from the npm registry, so a registry advisory "
                f"cannot be looked up")
    # The scope's own '@' is at index 0 and is not the version separator.
    at = raw.rfind("@")
    if at > 0:
        name, version = raw[:at], raw[at + 1:]
    else:
        name, version = raw, ""
    if not _NPM_NAME.match(name):
        return Resolution(
            "unresolvable",
            f"'{_safe(name, 64)}' is not a well-formed npm package name")
    if not version:
        return Resolution(
            "unpinned",
            f"npm '{_safe(name, 64)}' is not pinned to a version, so the "
            f"entry installs whatever npm publishes at launch",
            PackageIdentity(ECOSYSTEM_NPM, name, ""))
    if not _SEMVER_EXACT.match(version):
        return Resolution(
            "unpinned",
            f"npm '{_safe(name, 64)}' resolves through the range or tag "
            f"'{_safe(version, 32)}' rather than an exact version, so what "
            f"it installs is decided at launch",
            PackageIdentity(ECOSYSTEM_NPM, name, ""))
    return Resolution(
        "package", f"npm {_safe(name, 64)}@{_safe(version, 32)}",
        PackageIdentity(ECOSYSTEM_NPM, name, version))


def _normalize_pypi(name: str) -> str:
    """PEP 503 normalization — the form OSV matches PyPI names on."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _pypi_spec(spec: str) -> Resolution:
    """``pkg==1.2.3``, ``pkg@1.2.3``, or a bare ``pkg``."""
    raw = spec.strip()
    if not raw:
        return Resolution("unresolvable", "the entry names no package")
    lowered = raw.lower()
    for prefix in ("git+", "http:", "https:", "file:", ".", "/"):
        if lowered.startswith(prefix):
            return Resolution(
                "unresolvable",
                "the distribution is installed from a URL or a path rather "
                "than from PyPI, so a registry advisory cannot be looked up")
    if raw.endswith((".whl", ".tar.gz", ".zip")):
        return Resolution(
            "unresolvable",
            "the distribution is a local artifact rather than a PyPI "
            "release, so a registry advisory cannot be looked up")
    # Extras are not part of the identity: pkg[extra]==1.0
    raw = re.sub(r"\[[^\]]*\]", "", raw, count=1)
    version = ""
    if "==" in raw:
        name, _, version = raw.partition("==")
        version = version.split(",", 1)[0]
    elif "@" in raw:
        name, _, version = raw.partition("@")
    else:
        name = raw
        if re.search(r"[<>!~=]", name):
            head = re.split(r"[<>!~=]", name, maxsplit=1)[0]
            if _PYPI_NAME.match(head.strip()):
                return Resolution(
                    "unpinned",
                    f"PyPI '{_safe(head, 64)}' resolves through the range "
                    f"'{_safe(raw, 48)}' rather than an exact version, so "
                    f"what it installs is decided at launch",
                    PackageIdentity(ECOSYSTEM_PYPI,
                                    _normalize_pypi(head.strip()), ""))
            return Resolution(
                "unresolvable",
                f"'{_safe(head, 64)}' is not a well-formed PyPI project name")
    name = name.strip()
    version = version.strip()
    if not _PYPI_NAME.match(name):
        return Resolution(
            "unresolvable",
            f"'{_safe(name, 64)}' is not a well-formed PyPI project name")
    if not version:
        return Resolution(
            "unpinned",
            f"PyPI '{_safe(name, 64)}' is not pinned to a version, so the "
            f"entry installs whatever PyPI publishes at launch",
            PackageIdentity(ECOSYSTEM_PYPI, _normalize_pypi(name), ""))
    if not _PEP440_EXACT.match(version):
        return Resolution(
            "unpinned",
            f"PyPI '{_safe(name, 64)}' resolves through "
            f"'{_safe(version, 32)}' rather than an exact version",
            PackageIdentity(ECOSYSTEM_PYPI, _normalize_pypi(name), ""))
    normalized = _normalize_pypi(name)
    return Resolution(
        "package", f"PyPI {_safe(normalized, 64)}=={_safe(version, 32)}",
        PackageIdentity(ECOSYSTEM_PYPI, normalized, version))


def _resolve_npx(args: Sequence[str]) -> Resolution:
    # ``npx -p a -p b cmd`` installs BOTH. Taking the first and clearing it
    # would let a second package ride in behind a clean one, so an entry
    # that names more than one is refused rather than half-checked.
    named = [a for a in args if _split_flag(a)[0] in _NPX_PACKAGE_FLAGS]
    if len(named) > 1:
        return Resolution(
            "unresolvable",
            f"the entry installs {len(named)} packages in one launch and a "
            f"preflight answers for one; give the server its own entry per "
            f"package")
    positional, captured = _positionals(
        args, _NPX_VALUE_FLAGS, _NPX_PACKAGE_FLAGS)
    if captured:
        return _npm_spec(captured)
    if not positional:
        return Resolution(
            "unresolvable",
            "the launcher is given no package to run")
    return _npm_spec(positional[0])


def _resolve_uvx(args: Sequence[str]) -> Resolution:
    positional, captured = _positionals(
        args, _UVX_VALUE_FLAGS, frozenset({"--from"}))
    if captured:
        return _pypi_spec(captured)
    if not positional:
        return Resolution(
            "unresolvable",
            "the launcher is given no package to run")
    return _pypi_spec(positional[0])


def _resolve_pipx(args: Sequence[str]) -> Resolution:
    rest = list(args)
    # Only `pipx run` installs something; `pipx list` and friends are not
    # a server launch and never reach here in practice.
    while rest and rest[0].startswith("-"):
        head, inline = _split_flag(rest[0])
        rest.pop(0)
        if inline is None and head in _PIPX_VALUE_FLAGS and rest:
            rest.pop(0)
    if not rest or rest[0] != "run":
        return Resolution(
            "unresolvable",
            "the pipx invocation does not name a package to run")
    positional, captured = _positionals(rest[1:], _PIPX_VALUE_FLAGS,
                                        frozenset({"--spec"}))
    if captured:
        return _pypi_spec(captured)
    if not positional:
        return Resolution(
            "unresolvable", "the launcher is given no package to run")
    return _pypi_spec(positional[0])


def _resolve_python(args: Sequence[str]) -> Resolution:
    """A python entry fetches nothing at launch, so it is absent (R2).

    ``python -m mcp_server_git`` imports a distribution the operator
    pip-installed deliberately, earlier; nothing is pulled from a registry
    now. Refusing it — the first cut of this module did — claimed a
    protection the gate cannot deliver, because it cannot see inside the
    child's environment, and it taught operators that the gate is noise.
    The cost is stated rather than hidden: a compromised release already
    installed in that environment is not caught here. It never was.
    """
    return Resolution(
        "no_package",
        "the entry runs an interpreter against something already installed "
        "on this machine; nothing is fetched from a registry at launch")


def _resolve_deno(args: Sequence[str]) -> Resolution:
    """R5. ``npm:`` is an npm coordinate wearing a different prefix."""
    for token in args:
        if token.startswith("-") or token in {"run", "task", "serve"}:
            continue
        lowered = token.lower()
        if lowered.startswith("npm:"):
            return _npm_spec(token[4:])
        if lowered.startswith("jsr:"):
            return Resolution(
                "unsupported_launcher",
                "the entry installs from JSR, which this preflight has no "
                "advisory source for")
        if lowered.startswith(("http:", "https:")):
            return Resolution(
                "unresolvable",
                "the entry runs a module fetched from a URL rather than from "
                "a registry an advisory source indexes")
        return Resolution(
            "no_package",
            "the entry runs a local script, which no package registry has a "
            "record of")
    return Resolution(
        "no_package",
        "the entry starts deno with nothing to fetch")


#: Go module versions are ``v``-prefixed on the command line and OSV
#: accepts either spelling — normalised once here so the cache keys on one.
_GO_MODULE = re.compile(r"^[a-z0-9][a-z0-9._~-]*(\.[a-z0-9._~-]+)+(/[^\s@]+)*$",
                        re.IGNORECASE)


def _resolve_go(args: Sequence[str]) -> Resolution:
    """R4. ``go run example.com/mod/cmd@v1.2.3`` fetches at launch."""
    rest = [a for a in args if not a.startswith("-")]
    if not rest or rest[0] != "run":
        return Resolution(
            "unsupported_launcher",
            "the go invocation does not name a module to fetch and run")
    rest = rest[1:]
    if not rest:
        return Resolution(
            "unresolvable", "'go run' is given no module to run")
    spec = rest[0]
    if spec.startswith((".", "/")) or spec.endswith(".go"):
        return Resolution(
            "no_package",
            "the entry builds a local package, which no module proxy has a "
            "published record of")
    module, _, version = spec.partition("@")
    if not _GO_MODULE.match(module):
        return Resolution(
            "unresolvable",
            f"'{_safe(module, 64)}' is not a well-formed Go module path")
    if not version:
        return Resolution(
            "unpinned",
            f"Go '{_safe(module, 64)}' is not pinned to a version, so the "
            f"entry builds whatever the module proxy serves at launch",
            PackageIdentity(ECOSYSTEM_GO, module, ""))
    normalised = version[1:] if version[:1].lower() == "v" else version
    if not _PEP440_EXACT.match(normalised) or version.lower() in {
            "latest", "upgrade", "patch", "none"}:
        return Resolution(
            "unpinned",
            f"Go '{_safe(module, 64)}' resolves through "
            f"'{_safe(version, 32)}' rather than an exact version",
            PackageIdentity(ECOSYSTEM_GO, module, ""))
    return Resolution(
        "package", f"Go {_safe(module, 64)}@{_safe(normalised, 32)}",
        PackageIdentity(ECOSYSTEM_GO, module, normalised))


def resolve_package(command: str, args: Sequence[str]) -> Resolution:
    """What one stdio entry would FETCH at launch, or why that cannot be said.

    R2's rule, and the whole shape of this module: the question is not
    "can I name the package" but **does this launcher pull an artifact
    from a public registry at launch time**. Three legs, and every
    ``kind`` below is one of them:

    * **does not fetch** — a bare path, a local script, ``python -m``,
      ``node server.js``, ``go run ./cmd``. The operator installed that
      deliberately, earlier; nothing is being decided now. ``no_package``,
      and absent proceeds.
    * **fetches, and the artifact is nameable** — ``npx pkg@1.2.3``.
      ``package`` (or ``unpinned`` when the release is decided at launch),
      and it gets queried.
    * **fetches, and the artifact is not nameable** — a git or URL
      specifier, a malformed name, an ecosystem with no advisory source.
      ``unresolvable`` (refused) or ``unsupported_launcher`` (noted;
      refused under ``strict``).

    Pure: no I/O, no network, no filesystem. The answer is derivable from
    the config entry alone, because the entry is what an operator — or an
    attacker — edits.
    """
    program = _basename(command).lower()
    if program.endswith(".exe"):
        program = program[:-4]
    argv = [str(a) for a in args]

    if program in _NPM_LAUNCHERS:
        return _resolve_npx(argv)
    if program in {"npm", "pnpm", "yarn", "bun"}:
        # `npm exec pkg`, `pnpm dlx pkg`, `yarn dlx pkg`, `bun x pkg`.
        subcommands = {"exec", "dlx", "x", "create"}
        rest = list(argv)
        while rest and rest[0].startswith("-"):
            rest.pop(0)
        if rest and rest[0] in subcommands:
            return _resolve_npx(rest[1:])
        if rest and rest[0] in {"run", "start", "test"}:
            # A package.json script, or `bun run server.ts`: local, and
            # no registry has a record of it.
            return Resolution(
                "no_package",
                "the entry runs a local script, which no package registry "
                "has a record of")
        return Resolution(
            "unresolvable",
            f"'{_safe(program, 24)}' is invoked without a subcommand that "
            f"names a package to run")
    if program == "uvx":
        return _resolve_uvx(argv)
    if program == "uv":
        rest = list(argv)
        while rest and rest[0].startswith("-"):
            rest.pop(0)
        if rest and rest[0] in {"tool", "tools"}:
            rest = rest[1:]
            while rest and rest[0].startswith("-"):
                rest.pop(0)
            if rest and rest[0] in {"run", "uvx"}:
                return _resolve_uvx(rest[1:])
        if rest and rest[0] == "run":
            return Resolution(
                "unresolvable",
                "'uv run' runs a command inside a project environment rather "
                "than installing a named release, so what it would import is "
                "decided by that project's lockfile; launch it through a "
                "pinned 'uvx' spec to preflight it")
        return Resolution(
            "unresolvable",
            "the uv invocation does not name a package to run")
    if program == "pipx":
        return _resolve_pipx(argv)
    if program == "deno":
        return _resolve_deno(argv)
    if program == "go":
        return _resolve_go(argv)
    if _PY_INTERPRETERS.match(program):
        return _resolve_python(argv)
    if program in _UNSUPPORTED_LAUNCHERS:
        return Resolution(
            "unsupported_launcher",
            f"'{_safe(program, 24)}' distributes packages from an ecosystem "
            f"this preflight has no advisory source for")
    if program in {"node", "java"}:
        return Resolution(
            "no_package",
            "the entry runs something already on this machine; nothing is "
            "fetched from a registry at launch")
    return Resolution(
        "no_package",
        "the entry runs a program already on this machine, not a package "
        "fetched from a registry")


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

SEVERITY_ORDER = ("UNKNOWN", "NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL")
_SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITY_ORDER)}

#: The advisory-database words that are not CVSS words.
_SEVERITY_ALIASES = {
    "MODERATE": "MEDIUM",
    "IMPORTANT": "HIGH",
    "SEVERE": "HIGH",
    "MALICIOUS": "CRITICAL",
}

_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_AC = {"L": 0.77, "H": 0.44}
_PR_UNCHANGED = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.50}
_UI = {"N": 0.85, "R": 0.62}
_CIA = {"H": 0.56, "L": 0.22, "N": 0.0}


def _roundup(value: float) -> float:
    """CVSS v3.1's own rounding (Appendix A), not ``round()``."""
    scaled = int(round(value * 100000))
    if scaled % 10000 == 0:
        return scaled / 100000.0
    return (math.floor(scaled / 10000) + 1) / 10.0


def cvss_v3_base_score(vector: str) -> Optional[float]:
    """The base score for a CVSS v3.0/v3.1 vector, or ``None``.

    OSV carries the vector, not the score, and most npm/PyPI records that
    have CVSS data have only that — so without this, "refuse on HIGH"
    would degrade to "severity unknown" on the majority of real
    advisories. v4 vectors are not scored (a different, much larger
    metric set); they return ``None``, which lands in the *could not
    tell* row rather than in a clean pass.
    """
    text = str(vector or "").strip()
    if not text.upper().startswith(("CVSS:3.0/", "CVSS:3.1/")):
        return None
    metrics: Dict[str, str] = {}
    for part in text.split("/")[1:]:
        key, _, value = part.partition(":")
        if key and value:
            metrics[key.upper()] = value.upper()
    try:
        scope_changed = metrics["S"] == "C"
        av = _AV[metrics["AV"]]
        ac = _AC[metrics["AC"]]
        pr = (_PR_CHANGED if scope_changed else _PR_UNCHANGED)[metrics["PR"]]
        ui = _UI[metrics["UI"]]
        conf = _CIA[metrics["C"]]
        integ = _CIA[metrics["I"]]
        avail = _CIA[metrics["A"]]
    except KeyError:
        return None

    iss = 1.0 - ((1.0 - conf) * (1.0 - integ) * (1.0 - avail))
    if scope_changed:
        impact = 7.52 * (iss - 0.029) - 3.25 * ((iss - 0.02) ** 15)
    else:
        impact = 6.42 * iss
    if impact <= 0:
        return 0.0
    exploitability = 8.22 * av * ac * pr * ui
    total = impact + exploitability
    if scope_changed:
        total *= 1.08
    return _roundup(min(total, 10.0))


def _band(score: float) -> str:
    if score <= 0.0:
        return "NONE"
    if score < 4.0:
        return "LOW"
    if score < 7.0:
        return "MEDIUM"
    if score < 9.0:
        return "HIGH"
    return "CRITICAL"


def _is_malware(vuln: Dict[str, Any]) -> bool:
    """A malicious-package record, which is what FD-10 is actually about.

    OSF's Malicious Packages feed reaches OSV as ``MAL-`` ids, and those
    records frequently carry no CVSS at all — scoring them by severity
    alone would file the exact thing this gate exists for under "could
    not tell".
    """
    identifier = str(vuln.get("id") or "")
    if identifier.upper().startswith("MAL-"):
        return True
    for alias in vuln.get("aliases") or []:
        if str(alias).upper().startswith("MAL-"):
            return True
    specific = vuln.get("database_specific")
    if isinstance(specific, dict):
        # ``malicious-packages-origins`` is the key the real feed writes;
        # a plain ``malicious`` flag was assumed here and is not a shape
        # OSV emits, so that arm never fired. Both are accepted now, and
        # the id prefix above stays the signal that actually carries.
        if specific.get("malicious") or specific.get(
                "malicious-packages-origins"):
            return True
    return False


def severity_of(vuln: Dict[str, Any]) -> str:
    """One advisory's severity, from whichever field OSV carried it in.

    Preference order: a malware record is CRITICAL outright; then the
    numeric CVSS base score computed from the vector (the precise
    answer); then the database's own severity word; then UNKNOWN, which
    is a *could not tell*, never a pass.
    """
    if _is_malware(vuln):
        return "CRITICAL"

    best: Optional[str] = None
    entries = vuln.get("severity")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            score = cvss_v3_base_score(entry.get("score") or "")
            if score is None:
                continue
            band = _band(score)
            if best is None or _SEVERITY_RANK[band] > _SEVERITY_RANK[best]:
                best = band
    if best is not None:
        return best

    for holder in (vuln, *(a for a in (vuln.get("affected") or [])
                           if isinstance(a, dict))):
        specific = holder.get("database_specific")
        if not isinstance(specific, dict):
            continue
        word = str(specific.get("severity") or "").strip().upper()
        word = _SEVERITY_ALIASES.get(word, word)
        if word in _SEVERITY_RANK and word != "UNKNOWN":
            return word
    return "UNKNOWN"


def is_withdrawn(vuln: Dict[str, Any]) -> bool:
    """R7. A withdrawn record is a retraction, not a finding.

    Skipped at EVERY severity, deliberately: a withdrawn HIGH refusing a
    clean package is the failure mode that gets a security gate switched
    off, and OSV keeps withdrawn records in query answers.
    """
    return bool(str(vuln.get("withdrawn") or "").strip())


def has_open_range(vuln: Dict[str, Any]) -> bool:
    """R7. Is this advisory's affected range still open at the top?

    Reads ``affected[].ranges[].events`` and NOTHING else — never the
    severity word, which is independent of it in OSV's data. An open range
    (``introduced`` with no later ``fixed`` or ``last_affected``) means the
    most recent release is affected by construction, which is what lets an
    unpinned entry be judged without knowing which version it will fetch.

    An ``affected`` entry that enumerates explicit ``versions`` and carries
    no ranges is CLOSED by construction: it is a finite list, and "the
    latest release" is not in it unless it is named.
    """
    for affected in vuln.get("affected") or []:
        if not isinstance(affected, dict):
            continue
        ranges = affected.get("ranges")
        if not isinstance(ranges, list) or not ranges:
            continue
        for entry in ranges:
            if not isinstance(entry, dict):
                continue
            events = entry.get("events")
            if not isinstance(events, list):
                continue
            # Events are ordered; the last one to speak decides.
            still_open = False
            for event in events:
                if not isinstance(event, dict):
                    continue
                if "introduced" in event:
                    still_open = True
                elif "fixed" in event or "last_affected" in event:
                    still_open = False
            if still_open:
                return True
    return False


def _worst(vulns: Sequence[Dict[str, Any]]) -> Tuple[str, bool]:
    """The highest severity across the advisories, and whether any is
    a malware record."""
    worst = "UNKNOWN"
    malicious = False
    for vuln in vulns:
        if _is_malware(vuln):
            malicious = True
        band = severity_of(vuln)
        if _SEVERITY_RANK[band] > _SEVERITY_RANK[worst]:
            worst = band
    return worst, malicious


# ---------------------------------------------------------------------------
# The advisory source
# ---------------------------------------------------------------------------

class PreflightUnreachable(Exception):
    """The advisory source could not be asked. Never propagates out of
    :func:`check_server` — it becomes a REFUSE of that one server."""


def _osv_post(payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    """The one network call in this module. Tests patch THIS.

    ``payload`` is built by :func:`_query_osv` from the three resolved
    coordinate fields and is the entire body; nothing derived from the
    entry's command line, environment or paths is ever in it.
    """
    try:
        import requests
    except ImportError as e:  # pragma: no cover - requests is an mcp dep
        raise PreflightUnreachable(f"no HTTP client available ({e})") from None
    try:
        response = requests.post(
            OSV_QUERY_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json"},
            timeout=timeout,
        )
    except Exception as e:
        raise PreflightUnreachable(
            f"{type(e).__name__} contacting the advisory source") from None
    if response.status_code != 200:
        raise PreflightUnreachable(
            f"the advisory source answered HTTP {response.status_code}")
    try:
        body = response.json()
    except Exception:
        raise PreflightUnreachable(
            "the advisory source answered with something that is not JSON"
        ) from None
    if not isinstance(body, dict):
        raise PreflightUnreachable(
            "the advisory source answered with something that is not an "
            "object")
    return body


def _query_osv(identity: PackageIdentity, timeout: float) -> List[Dict[str, Any]]:
    """Ask OSV about one artifact. Coordinates only.

    An empty ``version`` means the PACKAGE-level question (R1): OSV accepts
    a query with no version and answers with every advisory it holds for
    the package, across all releases. That answer cannot say what an
    unpinned entry will fetch — but it can say the package has shipped
    malware, and that is conclusive without a version.
    """
    package = {"name": identity.name, "ecosystem": identity.ecosystem}
    payload: Dict[str, Any] = {"package": package}
    if identity.version:
        payload["version"] = identity.version
    body = _osv_post(payload, timeout)
    vulns = body.get("vulns")
    if vulns is None:
        return []
    if not isinstance(vulns, list):
        raise PreflightUnreachable(
            "the advisory source answered with a malformed 'vulns' field")
    return [v for v in vulns if isinstance(v, dict)]


# -- the cache, positive and negative ---------------------------------------

_CACHE_LOCK = threading.Lock()
_CACHE: Dict[Tuple[str, str, str], Tuple[float, Tuple[Dict[str, Any], ...]]] = {}


def reset_preflight_caches() -> None:
    """Drop the config memo and the advisory cache (test isolation; a
    restart does the same by being a new process)."""
    global _CONFIG_CACHE
    with _CONFIG_LOCK:
        _CONFIG_CACHE = None
    with _CACHE_LOCK:
        _CACHE.clear()


def _cached(identity: PackageIdentity,
            now: float) -> Optional[Tuple[Dict[str, Any], ...]]:
    with _CACHE_LOCK:
        entry = _CACHE.get(identity.key)
        if entry is None:
            return None
        expires, vulns = entry
        if expires <= now:
            del _CACHE[identity.key]
            return None
        return vulns


def _store(identity: PackageIdentity, vulns: Sequence[Dict[str, Any]],
           now: float, ttl: float) -> None:
    """Both answers are cached — the clean one especially.

    "No advisory" is the answer a normal machine gets every time, and
    re-asking for it on every relaunch of the same pinned version would
    make an opt-in check into a periodic beacon. A failure is NOT cached:
    a network blip must not be sticky for the rest of the TTL.
    """
    with _CACHE_LOCK:
        _CACHE[identity.key] = (now + ttl, tuple(vulns))


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def _advisory_ids(vulns: Sequence[Dict[str, Any]], limit: int = 6) -> Tuple[str, ...]:
    ids = []
    for vuln in vulns:
        identifier = _safe(vuln.get("id") or "?", 40)
        if identifier not in ids:
            ids.append(identifier)
        if len(ids) >= limit:
            break
    return tuple(ids)


#: R10. Environment keys in the ENTRY that redirect where the package
#: comes from. When one is set, the coordinate this module resolved is not
#: the artifact that will be fetched, so a clean OSV answer about it would
#: be a true statement about the wrong thing. Matched case-insensitively:
#: npm reads its config env case-insensitively, and an attacker picks the
#: spelling that is not on the list.
_REGISTRY_OVERRIDE_KEYS = frozenset({
    "npm_config_registry", "npm_config__auth", "yarn_registry",
    "npm_config_@scope:registry",
    "pip_index_url", "pip_extra_index_url", "pip_find_links",
    "uv_index", "uv_index_url", "uv_default_index", "uv_extra_index_url",
    "uv_find_links",
    "goproxy", "goprivate",
    "deno_registry_url", "npm_config_userconfig", "pip_config_file",
})


def _redirected_registry(env: Any) -> Optional[str]:
    """The first entry env key that moves the package source, or None.

    A local check on the entry — nothing extra goes on the wire, and the
    VALUE is never read or logged (it is frequently a URL with a token in
    it). Only the key name is named.

    Stated cost, because it bounds what this is worth: an ``.npmrc`` or a
    ``pip.conf`` in the working directory does the same redirection
    invisibly, and no config-entry check can see it. This catches the
    declared case only.
    """
    if not env:
        return None
    try:
        keys = list(env.keys())
    except Exception:
        return None
    for key in keys:
        name = str(key)
        if name.lower() in _REGISTRY_OVERRIDE_KEYS:
            return name
        # Scoped-registry keys are open-ended: npm_config_@any-scope:registry.
        lowered = name.lower()
        if lowered.startswith("npm_config_@") and lowered.endswith(":registry"):
            return name
    return None


def _refuse(reason: str, detail: str, **kwargs: Any) -> PreflightResult:
    return PreflightResult(Verdict.REFUSE, reason, detail, **kwargs)


def _proceed(reason: str, detail: str, **kwargs: Any) -> PreflightResult:
    return PreflightResult(Verdict.PROCEED, reason, detail, **kwargs)


def _obtain(identity: PackageIdentity, cfg: PreflightConfig,
            query: Optional[Callable], detail: str
            ) -> Tuple[Optional[Tuple[Dict[str, Any], ...]], bool,
                       Optional[PreflightResult]]:
    """Advisories for one identity: ``(vulns, queried, refusal)``.

    Exactly one of ``vulns`` and ``refusal`` is not None. Withdrawn records
    are dropped here (R7) so every caller sees the same filtered list, and
    a package whose only records are withdrawn reads as clean rather than
    as "1 advisory, severity unknown".
    """
    now = time.time()
    cached = _cached(identity, now)
    if cached is not None:
        return cached, False, None
    fetch = query if query is not None else _query_osv
    try:
        fetched = fetch(identity, cfg.timeout_seconds)
    except PreflightUnreachable as e:
        return None, False, _refuse(
            REASON_UNREACHABLE,
            f"{detail} could not be checked ({e}); the server is refused "
            f"rather than launched unchecked")
    except Exception as e:
        return None, False, _refuse(
            REASON_UNREACHABLE,
            f"{detail} could not be checked ({type(e).__name__}); the server "
            f"is refused rather than launched unchecked")
    vulns = tuple(v for v in fetched if not is_withdrawn(v))
    _store(identity, vulns, now, cfg.cache_ttl_seconds)
    return vulns, True, None


def _pinned_verdict(vulns: Tuple[Dict[str, Any], ...], cfg: PreflightConfig,
                    detail: str, queried: bool) -> PreflightResult:
    """The full answer, because the exact release is known."""
    if not vulns:
        return _proceed(REASON_CLEAN, f"{detail} has no advisory on record",
                        queried=queried)
    worst, malicious = _worst(vulns)
    ids = _advisory_ids(vulns)
    count = len(vulns)
    noun = "advisory" if count == 1 else "advisories"

    # A refusal names the records RESPONSIBLE for it, not the first few in
    # the answer. With more than a handful of advisories the id cap was
    # listing whichever came back first — so a malware refusal could cite
    # six unrelated LOW findings and never the MAL- record it refused on,
    # which is exactly the thing an operator needs to look up.
    if malicious:
        return _refuse(
            REASON_MALWARE,
            f"{detail} is on record as a malicious package",
            advisories=_advisory_ids([v for v in vulns if _is_malware(v)]),
            severity="CRITICAL", queried=queried)
    if _SEVERITY_RANK[worst] >= _SEVERITY_RANK["HIGH"]:
        blame = [v for v in vulns
                 if _SEVERITY_RANK[severity_of(v)] >= _SEVERITY_RANK["HIGH"]]
        return _refuse(
            REASON_ADVISORY,
            f"{detail} has {count} {noun}, worst {worst}",
            advisories=_advisory_ids(blame), severity=worst, queried=queried)
    if cfg.strict:
        described = worst if worst != "UNKNOWN" else "an unrated severity"
        return _refuse(
            REASON_ADVISORY,
            f"{detail} has {count} {noun} at {described}, and strict mode "
            f"refuses anything not positively cleared",
            advisories=ids, severity=worst, queried=queried)
    described = worst if worst != "UNKNOWN" else "UNKNOWN severity"
    return _proceed(
        REASON_ADVISORY,
        f"{detail} has {count} {noun} at {described}, below the refusal "
        f"threshold", advisories=ids, severity=worst, queried=queried)


def _unpinned_verdict(vulns: Tuple[Dict[str, Any], ...], label: str,
                      queried: bool) -> PreflightResult:
    """R1. What a PACKAGE-level answer can and cannot conclude.

    It cannot say what the entry will fetch — measured: at the package
    level ``@modelcontextprotocol/server-filesystem`` carries advisories
    while its current release carries none. Refusing on that would be a
    false alarm, and it would be a false alarm on the commonest real MCP
    entry, which is how an opt-in gate gets switched off entirely.

    Two things it CAN conclude:

    * a malware record — a package that has published malware, being
      installed as "whatever is published now", is the FD-10 threat itself
      and the remedy is one line of YAML;
    * a HIGH or CRITICAL advisory whose range is still open (R7) — the
      launch-time artifact is inside that range by construction, so this
      is not a guess.

    Everything else is the genuine could-not-tell: warn, name the fact
    that the entry is unpinned, and launch. ``strict`` never reaches here
    (R8).
    """
    ids = _advisory_ids(vulns)
    if not vulns:
        return _proceed(
            REASON_UNPINNED,
            f"{label} is unpinned: the package has no advisory on record, "
            f"but what it installs is decided at launch — pin a version to "
            f"check the release itself", queried=queried)

    malicious = [v for v in vulns if _is_malware(v)]
    if malicious:
        return _refuse(
            REASON_MALWARE,
            f"{label} is unpinned and the package is on record as having "
            f"published a malicious release",
            advisories=_advisory_ids(malicious), severity="CRITICAL",
            queried=queried)

    open_bad = [v for v in vulns
                if _SEVERITY_RANK[severity_of(v)] >= _SEVERITY_RANK["HIGH"]
                and has_open_range(v)]
    if open_bad:
        worst, _ = _worst(open_bad)
        return _refuse(
            REASON_ADVISORY,
            f"{label} is unpinned and has an unfixed {worst} advisory whose "
            f"affected range is still open, so the release it would fetch is "
            f"inside that range",
            advisories=_advisory_ids(open_bad), severity=worst,
            queried=queried)

    worst, _ = _worst(vulns)
    count = len(vulns)
    noun = "advisory" if count == 1 else "advisories"
    return _proceed(
        REASON_UNPINNED,
        f"{label} is unpinned: the package has {count} fixed or lower "
        f"{noun} (worst {worst}) and none with an open range, but what it "
        f"installs is decided at launch — pin a version to check the "
        f"release itself", advisories=ids, severity=worst, queried=queried)


def check_server(
    server: Any,
    *,
    config: Optional[PreflightConfig] = None,
    query: Optional[Callable[[PackageIdentity, float], List[Dict[str, Any]]]] = None,
) -> PreflightResult:
    """Should this server be launched? Never raises.

    ``server`` is an :class:`~halbert_core.mcp.config.MCPServerConfig` (or
    anything carrying ``name``/``transport``/``command``/``args``/``env``).
    Every failure mode — an unparseable entry, an unreachable source, a bug
    in this module — comes back as a :class:`PreflightResult`, because the
    caller is a daemon start and a gate that raises into one has turned a
    security check into an outage.
    """
    cfg = config if config is not None else load_preflight_config()
    if not cfg.enabled:
        return _proceed(REASON_DISABLED, "the package preflight is switched off")

    try:
        transport = str(getattr(server, "transport", "stdio") or "stdio").lower()
        if transport != "stdio":
            return _proceed(
                REASON_NO_PACKAGE,
                "the entry connects to a URL and installs nothing")

        resolution = resolve_package(
            str(getattr(server, "command", "") or ""),
            [str(a) for a in (getattr(server, "args", ()) or ())])

        if resolution.kind == "no_package":
            return _proceed(REASON_NO_PACKAGE, resolution.detail)
        if resolution.kind == "unsupported_launcher":
            if cfg.strict:
                return _refuse(REASON_UNSUPPORTED_LAUNCHER, resolution.detail)
            return _proceed(REASON_UNSUPPORTED_LAUNCHER, resolution.detail)

        # R10: from here down the launcher FETCHES, so a redirected registry
        # in the entry's own env means the artifact is not the one OSV would
        # be asked about. Checked before any query: a coordinate we already
        # know is a lie must not be put on the wire as though it were true.
        redirected = _redirected_registry(getattr(server, "env", None))
        if redirected:
            return _refuse(
                REASON_UNRESOLVABLE,
                f"the entry redirects its package source with "
                f"'{_safe(redirected, 40)}', so what it fetches is not the "
                f"release an advisory source would answer for")

        if resolution.kind == "unpinned":
            # R8: strict refuses every unpinned entry, and the outcome is
            # fixed before the request — so no request is made. A
            # deterministic answer needs no egress.
            if cfg.strict:
                return _refuse(
                    REASON_UNPINNED,
                    f"{resolution.detail} — strict mode requires a pinned "
                    f"version and refuses without querying")
            if resolution.identity is None:  # pragma: no cover - guarded
                # A resolver that reports "unpinned" without naming the
                # package has a bug; refuse rather than guess.
                return _refuse(REASON_UNRESOLVABLE, resolution.detail)
            package_level = PackageIdentity(
                resolution.identity.ecosystem, resolution.identity.name, "")
            # The coordinate alone: the resolution's own detail explains WHY
            # it is unpinned, and the verdict below says so again in its own
            # words — composing both produced "is not pinned ... is unpinned".
            label = (f"{package_level.ecosystem} "
                     f"'{_safe(package_level.name, 64)}'")
            vulns, queried, refusal = _obtain(
                package_level, cfg, query, label)
            if refusal is not None:
                return refusal
            return _unpinned_verdict(vulns or (), label, queried)

        if resolution.kind != "package" or resolution.identity is None:
            return _refuse(REASON_UNRESOLVABLE, resolution.detail)

        vulns, queried, refusal = _obtain(
            resolution.identity, cfg, query, resolution.detail)
        if refusal is not None:
            return refusal
        return _pinned_verdict(vulns or (), cfg, resolution.detail, queried)
    except Exception as e:  # pragma: no cover - belt and braces
        logger.debug("package preflight raised", exc_info=True)
        return _refuse(
            REASON_UNREACHABLE,
            f"the preflight itself failed ({type(e).__name__}); the server "
            f"is refused rather than launched unchecked")


# ---------------------------------------------------------------------------
# R9: the operator-facing surface
# ---------------------------------------------------------------------------

#: The detector name every preflight finding is filed under, so the
#: Findings page can group them and ``find_by_detector_title`` can
#: deduplicate a relaunch of the same server.
FINDING_DETECTOR = "mcp_package_preflight"

#: Outcomes that are worth telling the operator about. ``clean``,
#: ``no_package`` and ``disabled`` are not: a finding raised on every
#: healthy launch is a finding nobody reads.
_REPORTABLE = frozenset({
    REASON_ADVISORY, REASON_MALWARE, REASON_UNPINNED, REASON_UNRESOLVABLE,
    REASON_UNREACHABLE, REASON_UNSUPPORTED_LAUNCHER,
})


def report_finding(server_name: str, result: PreflightResult,
                   store: Any = None) -> Optional[str]:
    """Put one preflight outcome on the operator's findings surface.

    R9's rule: *a warning the operator never sees is a pass*. Every warn
    outcome of this gate — unpinned, an advisory below the threshold, a
    severity nothing could rate, a launcher with no advisory source —
    changes nothing the operator can observe unless it lands somewhere
    they look. A refusal is reported too, at ``critical``: the server not
    working is visible, but *why* it is not working should not require
    reading a log.

    Never raises, and returns None when nothing was filed. A findings
    store that is missing, locked or broken must not stop a server
    launching — this is a notification, not a gate.
    """
    if result.reason not in _REPORTABLE:
        return None
    name = _safe(server_name, 64)
    title = f"MCP server '{name}': package preflight {result.reason}"
    try:
        from ..findings.store import Finding, FindingStore

        store = store if store is not None else FindingStore()
        existing = store.find_by_detector_title(FINDING_DETECTOR, title)
        if existing is not None and existing.status == "open":
            # A relaunch of the same server is the same finding.
            return existing.id

        severity = "critical" if result.refused else "warning"
        launched = ("The server was NOT launched."
                    if result.refused
                    else "The server was launched anyway.")
        ids = ", ".join(result.advisories) if result.advisories else ""
        return store.add(Finding(
            id="",
            detector=FINDING_DETECTOR,
            severity=severity,
            title=title,
            description=f"{result.detail}. {launched}",
            why_now=(f"The MCP server '{name}' was about to launch and the "
                     f"package preflight is switched on."),
            why_care=(
                "A refused server contributes no tools until the entry is "
                "changed."
                if result.refused else
                "The gate could not positively clear this package, so it "
                "launched with the uncertainty named rather than silently."),
            why_so=result.detail,
            why_trust=([f"OSV advisory {i}" for i in result.advisories]
                       or ["resolved from the entry's own command line"]),
            affected_paths=[],
            affected_services=[name],
        ))
    except Exception:
        logger.debug("could not file a preflight finding", exc_info=True)
        return None
