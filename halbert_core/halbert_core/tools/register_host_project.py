# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Register the host's configuration tree as a SourcePrep project.

This creates (or updates) a SourcePrep project named "halbert-host" that
points at a staging directory containing snapshots of the host's live
configuration files. The project is then indexed so that the config brain
can semantically search over the host's configuration files, drop-ins,
and systemd units.

SourcePrep indexes files relative to the project root, so we stage copies
of the host config files into a local directory structure that mirrors
their original paths. This avoids permission issues with indexing /etc
directly and gives us a stable, snapshotable project root.

Phase 5 / T5a.1.
"""

from __future__ import annotations

import logging
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from ..config.parser import parse as parse_config
from ..ingestion.redaction import redact_text
from ..integrations.prep_token import auth_headers as _auth_headers
from ..utils.paths import data_subdir

logger = logging.getLogger(__name__)

PROJECT_NAME = "halbert-host"

# Staging directory for the host config tree. T-H1.1 unified the two-project
# split into one SourcePrep project under a single root:
#   ~/.local/share/halbert/sourceprep/
#       host/      ← live config snapshots (this registrar)
#       knowledge/  ← jsonl_to_markdown.py doc corpus
# The host config files stage to sourceprep/host/ so the unified "halbert"
# project's `host/` scope covers them. A custom --staging-dir override still
# works for debugging and points wherever the caller wants.
SOURCEPREP_ROOT = data_subdir("sourceprep")
STAGING_DIR = data_subdir("sourceprep", "host")

# OS-specific config file collections to stage
_LINUX_CONFIG_PATHS = [
    "/etc/fstab",
    "/etc/ssh/sshd_config",
    "/etc/ssh/sshd_config.d",
    "/etc/systemd/system",
    "/etc/default",
    "/etc/sysctl.conf",
    "/etc/sysctl.d",
    "/etc/hosts",
    "/etc/hostname",
]

_MACOS_CONFIG_PATHS = [
    "/etc/fstab",
    "/etc/ssh/sshd_config",
    "/etc/ssh/sshd_config.d",
    "/etc/hosts",
    "/etc/synthetic.conf",
    "/Library/LaunchDaemons",
    "/Library/LaunchAgents",
]

# Include globs for the staged files (relative to staging root)
_STAGED_INCLUDE_GLOBS = [
    "**/*.conf",
    "**/*.cfg",
    "**/*.yml",
    "**/*.yaml",
    "**/*.service",
    "**/*.mount",
    "**/*.plist",
    "**/fstab",
    "**/sshd_config*",
    "**/hosts",
    "**/hostname",
    "**/synthetic.conf",
    "**/sysctl.conf",
    # Credential files — cross-platform, added with the credentials_admin scope.
    # These are config files with key=value or INI structure that the parser
    # handles. Private key files (*.pem, id_rsa*) are excluded by
    # _COMMON_EXCLUDE_GLOBS and the credentials.yml exclude block.
    "**/credentials",
    "**/config.json",
    "**/.netrc",
    "**/ssh_config",
    "**/.env",
    "**/.env.local",
    "**/.env.production",
    "**/.env.staging",
    "**/.npmrc",
    "**/pip.conf",
    "**/.pypirc",
    "**/.gitconfig",
    "**/.git-credentials",
    "**/credentials.tfrc.json",
    "**/.terraformrc",
]

_COMMON_EXCLUDE_GLOBS = [
    "**/.git/**",
    "**/ssl/**",
    "**/letsencrypt/**",
    "**/shadow",
    "**/gshadow",
    # Key material — defence in depth.  Most of these match no include glob
    # today (the include allowlist is the primary gate), but the protection
    # must not depend on that list never widening.  Task 1 lifts redaction
    # from the staging path, which removes the PEM_RE backstop inside
    # redact_text(); these excludes replace it at the staging gate.
    "**/*.key",
    "**/*.pem",
    "**/*.p12",
    "**/*.pfx",
    "**/id_rsa*",
    "**/id_ecdsa*",
    "**/id_ed25519*",
    "**/*.kdbx",
    "**/.netrc",
    "**/authorized_keys",
]


def _os_config_paths() -> List[str]:
    """Return OS-appropriate config paths to stage."""
    if platform.system() == "Darwin":
        return _MACOS_CONFIG_PATHS
    return _LINUX_CONFIG_PATHS


# Read failures that mean "there was never anything here to index": a
# dangling symlink, a path that is a directory or has a file in the middle of
# it. Everything else is reported at warning — see _stage_one_file.
_NOTHING_TO_READ = (FileNotFoundError, IsADirectoryError, NotADirectoryError)


def _stage_one_file(src_file: Path, dest_file: Path, *, redact: bool = True) -> bool:
    """Stage a single config file, optionally through the redaction pipeline.

    When ``redact=True`` (default), the file content is passed through
    ``redact_text()`` before writing — anything landing under the staging
    root is indexed by SourcePrep and returned by scoped queries, so
    unredacted content here is unredacted content in the knowledge base.

    When ``redact=False``, the raw text is written.  This is for Halbert's
    private host project only: the staging dir is user-owned, the daemon
    is localhost-only, and the MCP response boundary (``mcp_response()``)
    redacts on egress to external clients.  The exclude globs
    (``_COMMON_EXCLUDE_GLOBS``) still strip key material (*.key, *.pem,
    id_rsa*, etc.) regardless of this flag.

    Binary formats (plists) are normalized to text by the parser first, so
    they are greppable AND so the redaction rules can actually match —
    redaction is text-based and cannot see inside a binary blob.

    Returns True if the file was staged.
    """
    try:
        canon = parse_config(str(src_file))
    except _NOTHING_TO_READ as e:
        # Nothing was lost, so there is nothing to report. A stale symlink is
        # a fact about the host rather than a limit on what Halbert can see,
        # and the manifests deliberately list paths that exist on only one
        # distro or platform, so absence is the bulk case -- warning on it
        # would drown the signal from the case below.
        logger.debug(f"Skip {src_file} (nothing to read): {e}")
        return False
    except Exception as e:
        # Everything else is a blind spot: the manifest asked for this file,
        # the file is there, and it did not reach the index. Permission denied
        # is the case that motivated this -- a mode-0600 root-owned plist
        # vanished from a real staging run with no signal at the default log
        # level. A decode error or a parser crash is the same defect from
        # Halbert's point of view: it administers this machine and cannot say
        # what is in one of its config files. Say so, loudly enough to be
        # seen. These are rare, so this does not become noise.
        logger.warning(f"Cannot read {src_file}, excluded from the index: {e}")
        return False

    # `lines` is the canonical text form for every kind the parser emits,
    # including plists re-serialized to XML. It carries no line terminators:
    # `splitlines()` cannot express "the file ended with a newline", so the
    # join always loses the final one. Put it back rather than write every
    # staged file one byte short of its original — the whole point of this
    # tree is that it can be diffed against the live host, and a spurious
    # "\\ No newline at end of file" on every file makes the real redaction
    # changes harder to see. A source file that genuinely lacked a trailing
    # newline gains one; that is the correct shape for a config file and is
    # meaningless for a plist, which is re-serialized either way.
    text = "\n".join(line["text"] for line in canon.get("lines") or [])
    if text:
        text += "\n"

    try:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        # An empty file is still staged. Its content contributes nothing to the
        # index, but its existence is a fact about the host — an empty drop-in
        # is how a unit gets masked or a default overridden — and dropping it
        # would make the staged tree misreport the machine's file inventory.
        dest_file.write_text(redact_text(text) if redact else text, encoding="utf-8")
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot write staged copy {dest_file}: {e}")
        return False
    return True


def _stage_config_files(paths: List[str], staging_root: Path, *, redact: bool = True) -> int:
    """Stage config files/dirs into the staging directory.

    When ``redact=True`` (default), content is redacted before writing.
    When ``redact=False``, raw content is written — for Halbert's private
    host project only (see ``_stage_one_file`` for the security rationale).

    Preserves the original path structure under the staging root.
    Skips files that don't exist or aren't readable.

    Returns the number of files staged.
    """
    staging_root = Path(staging_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    count = 0

    for src in paths:
        src_path = Path(src).expanduser()
        if not src_path.exists():
            logger.debug(f"Skipping (not found): {src_path}")
            continue

        # Determine destination preserving path structure
        if src_path.is_absolute():
            # Strip leading slash so it becomes relative under staging root
            dest = staging_root / str(src_path).lstrip("/")
        else:
            dest = staging_root / src_path

        try:
            if src_path.is_file():
                if _stage_one_file(src_path, dest, redact=redact):
                    count += 1
            elif src_path.is_dir():
                for root, dirs, files in os.walk(src_path):
                    rel = Path(root).relative_to(src_path)
                    dest_dir = dest / rel
                    for f in files:
                        if _stage_one_file(Path(root) / f, dest_dir / f, redact=redact):
                            count += 1
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot stage {src_path}: {e}")

    return count


def stage_role_tree(
    role: str,
    staging_root: Path,
    manifest_path: Optional[str] = None,
    *,
    redact: bool = True,
) -> int:
    """Stage one role's manifest-matched config under staging_root/<role>/.

    When ``redact=True`` (default), content is redacted before writing.
    When ``redact=False``, raw content is written — for Halbert's private
    host project only.

    Returns the number of files staged.
    """
    from ..config.manifest import Manifest
    from ..config.roles import manifest_path_for, staging_subdir_for

    man = Manifest.from_file(manifest_path or manifest_path_for(role))
    paths = man.iter_paths()
    if not paths:
        logger.info("Role %s matched no files on this host", role)
        return 0

    role_root = Path(staging_root) / staging_subdir_for(role)
    staged = _stage_config_files(paths, role_root, redact=redact)
    logger.info("Staged %d files for role %s under %s", staged, role, role_root)
    return staged


class HostProjectRegistrar:
    """Register and configure the halbert-host SourcePrep project."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = (
            base_url
            or "http://localhost:8400"
        ).rstrip("/")
        self.timeout = timeout

    def _list_projects(self) -> List[Dict[str, Any]]:
        """GET /projects — list all registered projects."""
        try:
            resp = requests.get(
                f"{self.base_url}/projects",
                timeout=self.timeout,
                headers=_auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                return data["data"].get("projects", [])
            return data.get("projects", [])
        except requests.RequestException as e:
            logger.error(f"Failed to list SourcePrep projects: {e}")
            return []

    def _find_project(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a project by name. Returns the project dict or None."""
        for p in self._list_projects():
            if p.get("name") == name:
                return p
        return None

    def _create_project(self, path: str, name: str, mode: str = "standalone") -> Dict[str, Any]:
        """POST /projects — create a new project. Returns the project dict."""
        resp = requests.post(
            f"{self.base_url}/projects",
            json={"path": path, "name": name, "mode": mode},
            timeout=self.timeout,
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        # Response shape: {"success": true, "data": {"project": {...}}}
        if isinstance(data, dict) and "data" in data:
            inner = data["data"]
            if isinstance(inner, dict) and "project" in inner:
                return inner["project"]
            return inner or {}
        return data

    def _update_project_config(self, project_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """PUT /projects/{id} — update project config (include_globs, etc.)."""
        resp = requests.put(
            f"{self.base_url}/projects/{project_id}",
            json={"config": config, "touch": True},
            timeout=self.timeout,
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def _build_project(self, project_id: str) -> Dict[str, Any]:
        """POST /projects/{id}/trace/build — trigger an index build."""
        try:
            resp = requests.post(
                f"{self.base_url}/projects/{project_id}/trace/build",
                json={},
                timeout=self.timeout * 4,
                headers=_auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"Trace build endpoint failed: {e}")
            return {}

    def register(
        self,
        name: str = PROJECT_NAME,
        config_paths: Optional[List[str]] = None,
        include_globs: Optional[List[str]] = None,
        exclude_globs: Optional[List[str]] = None,
        mode: str = "standalone",
        build: bool = True,
        staging_dir: Optional[str] = None,
        *,
        redact: bool = True,
    ) -> Dict[str, Any]:
        """Register or update the halbert-host SourcePrep project.

        Stages host config files into a local directory, then registers
        that directory as a SourcePrep project.

        Args:
            name: Project name (default: "halbert-host")
            config_paths: Host paths to stage. If None, uses OS-appropriate defaults.
            include_globs: Include globs for the staged files. If None, uses defaults.
            exclude_globs: Exclude globs. If None, uses common defaults.
            mode: Index location mode ("standalone", "embedded", "custom")
            build: If True, trigger an index build after registration.
            staging_dir: Custom staging directory. If None, uses default.
            redact: If True (default), redact content before staging. If False,
                write raw content — for Halbert's private host project only.
                The MCP response boundary (mcp_response) handles egress
                redaction for external clients.

        Returns:
            Dict with project_id, created (bool), files_staged, and build_result.
        """
        paths = config_paths or _os_config_paths()
        globs = include_globs or _STAGED_INCLUDE_GLOBS
        excludes = exclude_globs or _COMMON_EXCLUDE_GLOBS
        staging_root = Path(staging_dir) if staging_dir else Path(STAGING_DIR)

        # Stage config files
        files_staged = _stage_config_files(paths, staging_root, redact=redact)
        logger.info(f"Staged {files_staged} config files into {staging_root} (redact={redact})")

        if files_staged == 0:
            logger.warning("No config files staged — project will be empty")

        # Check if project already exists
        existing = self._find_project(name)
        created = False

        if existing:
            project_id = existing["id"]
            logger.info(f"Project '{name}' already exists (id={project_id}), updating config")
        else:
            # Create new project pointing at staging dir
            try:
                project = self._create_project(path=str(staging_root), name=name, mode=mode)
                project_id = project.get("id")
                created = True
                logger.info(f"Created project '{name}' (id={project_id}) at {staging_root}")
            except requests.RequestException as e:
                logger.error(f"Failed to create project '{name}': {e}")
                return {"error": str(e), "created": False, "files_staged": files_staged}

        if not project_id:
            logger.error("No project_id returned from SourcePrep")
            return {"error": "no project_id", "created": created, "files_staged": files_staged}

        # Update config with include/exclude globs
        config = {
            "include_globs": globs,
            "exclude_globs": excludes,
            "max_file_bytes": 100000,
            "use_gitignore": False,
            "trace": {"enabled": True},
        }
        try:
            self._update_project_config(project_id, config)
            logger.info(f"Updated config for '{name}': {len(globs)} include globs")
        except requests.RequestException as e:
            logger.warning(f"Failed to update project config: {e}")

        # Build the index
        build_result = {}
        if build:
            try:
                build_result = self._build_project(project_id)
                logger.info(f"Build triggered for '{name}'")
            except requests.RequestException as e:
                logger.warning(f"Build failed (non-fatal): {e}")
                build_result = {"error": str(e)}

        return {
            "project_id": project_id,
            "name": name,
            "created": created,
            "staging_dir": str(staging_root),
            "files_staged": files_staged,
            "include_globs": globs,
            "build_result": build_result,
        }

    def verify(self, query: str = "sshd config", name: str = PROJECT_NAME) -> Dict[str, Any]:
        """Verify the project is indexed by running a semantic search.

        Args:
            query: Search query to test.
            name: Project name to search within.

        Returns:
            Search results dict.
        """
        project = self._find_project(name)
        if not project:
            return {"error": f"Project '{name}' not found"}

        project_id = project["id"]
        try:
            resp = requests.post(
                f"{self.base_url}/projects/{project_id}/search",
                json={"query": query, "k": 5, "min_score": 0.05},
                timeout=self.timeout,
                headers=_auth_headers(),
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"error": str(e)}


def register_host_project(
    base_url: Optional[str] = None,
    build: bool = True,
    *,
    redact: bool = True,
) -> Dict[str, Any]:
    """Convenience function: register the host config project.

    Args:
        base_url: SourcePrep daemon URL. Defaults to http://localhost:8400.
        build: If True, trigger an index build.
        redact: If True (default), redact content before staging. If False,
            write raw content — for Halbert's private host project only.

    Returns:
        Registration result dict.
    """
    registrar = HostProjectRegistrar(base_url=base_url)
    return registrar.register(build=build, redact=redact)


if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    result = register_host_project(build=True)
    print(json.dumps(result, indent=2))

    if "error" not in result:
        print("\n--- Verification search ---")
        verify = HostProjectRegistrar().verify("sshd port")
        print(json.dumps(verify, indent=2)[:2000])

    sys.exit(0 if "error" not in result else 1)
