"""
Host Config Tree Registration

Registers the host's configuration state as a SourcePrep project and
triggers an initial build. The synthesized tree includes /etc, systemd
units, dotfiles, and selected log excerpts — indexed as if it were a
code repo.

This module handles B1: project registration with custom globs for
config formats. It calls the SourcePrep daemon's HTTP API via
SourcePrepClient.

Usage:
    from halbert_core.integrations.host_config_registration import register_host_project

    project_id = register_host_project(
        host_root="/",           # or path to synthesized config tree
        project_name="halbert-host",
    )

Glob configuration:
    Config formats are included via custom include_globs in the
    .sourceprep/team_config.json. The SourcePrep walker is glob-driven
    and per-project configurable — no engine changes needed.

    Default config globs cover:
    - Standard config extensions: *.conf, *.yaml, *.yml, *.toml, *.json, *.ini
    - systemd units: *.service, *.timer, *.socket, *.mount, *.automount
    - Extensionless configs: fstab, hostname, hosts, resolv.conf, sshd_config,
      sudoers, crontab, authorized_keys, environment
    - Shell scripts: *.sh, *.bash
    - Markdown (for HALBERT.md, README): *.md

    Secrets are handled by prep_engine.detect_secrets which runs on the
    embedding path — confirm redaction before deploying to production.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .sourceprep_client import SourcePrepClient

logger = logging.getLogger(__name__)


DEFAULT_CONFIG_INCLUDE_GLOBS: List[str] = [
    # Standard config extensions
    "**/*.conf",
    "**/*.yaml",
    "**/*.yml",
    "**/*.toml",
    "**/*.json",
    "**/*.ini",
    "**/*.cfg",
    "**/*.properties",
    # systemd units
    "**/*.service",
    "**/*.timer",
    "**/*.socket",
    "**/*.mount",
    "**/*.automount",
    "**/*.target",
    # Shell scripts
    "**/*.sh",
    "**/*.bash",
    # Markdown (HALBERT.md, README, docs)
    "**/*.md",
    # Extensionless config files (explicit filename globs)
    "**/fstab",
    "**/hostname",
    "**/hosts",
    "**/resolv.conf",
    "**/sshd_config",
    "**/sudoers",
    "**/crontab",
    "**/authorized_keys",
    "**/environment",
    "**/networks",
    "**/protocols",
    "**/services",
    "**/group",
    "**/passwd",
    "**/shadow",
    "**/subuid",
    "**/subgid",
]

DEFAULT_CONFIG_EXCLUDE_GLOBS: List[str] = [
    # Exclude binary/compiled files
    "**/*.pyc",
    "**/*.so",
    "**/*.bin",
    # Exclude large log files (excerpts handled separately)
    "**/*.log",
    "**/*.log.*",
    # Exclude cache directories
    "**/__pycache__/**",
    "**/.cache/**",
    # Exclude SourcePrep's own metadata
    "**/.sourceprep/**",
]

# Sensitive files to exclude from indexing — secrets hygiene
SENSITIVE_EXCLUDE_GLOBS: List[str] = [
    "**/shadow",
    "**/shadow-*",
    "**/gshadow",
    "**/gshadow-*",
    "**/ssh_host_*_key",
    "**/ssh_host_*_key.pub",
    "**/authorized_keys",
    "**/*.pem",
    "**/*.key",
]


def get_config_globs(
    include_sensitive: bool = False,
    extra_includes: Optional[List[str]] = None,
    extra_excludes: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """Build include/exclude glob lists for the host config project.

    Args:
        include_sensitive: If True, include sensitive files (NOT recommended
            for production — use for local dev only).
        extra_includes: Additional include globs.
        extra_excludes: Additional exclude globs.

    Returns:
        Dict with 'include_globs' and 'exclude_globs' keys.
    """
    includes = list(DEFAULT_CONFIG_INCLUDE_GLOBS)
    excludes = list(DEFAULT_CONFIG_EXCLUDE_GLOBS)

    if not include_sensitive:
        excludes.extend(SENSITIVE_EXCLUDE_GLOBS)

    if extra_includes:
        includes.extend(extra_includes)

    if extra_excludes:
        excludes.extend(extra_excludes)

    return {
        "include_globs": includes,
        "exclude_globs": excludes,
    }


def register_host_project(
    host_root: str = "/",
    project_name: str = "halbert-host",
    project_id: Optional[str] = None,
    include_sensitive: bool = False,
    extra_includes: Optional[List[str]] = None,
    extra_excludes: Optional[List[str]] = None,
    client: Optional[SourcePrepClient] = None,
    trigger_build: bool = True,
) -> str:
    """Register the host config tree as a SourcePrep project.

    Calls POST /projects to create the project, then optionally
    POST /projects/{id}/build to trigger an initial index build.

    Args:
        host_root: Root path of the config tree (default "/" for live host,
            or path to a synthesized/snapshot tree).
        project_name: Display name for the project.
        project_id: Optional explicit project ID. If None, SourcePrep
            auto-generates one.
        include_sensitive: Include sensitive files (NOT recommended).
        extra_includes: Additional include globs beyond defaults.
        extra_excludes: Additional exclude globs beyond defaults.
        client: Existing SourcePrepClient instance. If None, creates one.
        trigger_build: If True, trigger an initial build after registration.

    Returns:
        The project ID.

    Raises:
        requests.RequestException: If the SourcePrep daemon is unreachable
            or returns an error.
        ValueError: If project registration fails.
    """
    if client is None:
        client = SourcePrepClient()

    if not client.health():
        raise ConnectionError(
            f"SourcePrep daemon not reachable at {client.base_url}. "
            "Ensure the daemon is running."
        )

    globs = get_config_globs(
        include_sensitive=include_sensitive,
        extra_includes=extra_includes,
        extra_excludes=extra_excludes,
    )

    logger.info(
        f"Registering host config project '{project_name}' "
        f"with {len(globs['include_globs'])} include globs, "
        f"{len(globs['exclude_globs'])} exclude globs"
    )

    # POST /projects — create the project
    import requests

    create_url = f"{client.base_url}/projects"
    create_body: Dict[str, Any] = {
        "path": host_root,
        "name": project_name,
        "mode": "standalone",
    }

    try:
        resp = requests.post(
            create_url, json=create_body, timeout=client.timeout
        )
        resp.raise_for_status()
        result = resp.json()
    except requests.RequestException as e:
        logger.error(f"Failed to create SourcePrep project: {e}")
        raise

    # Extract project ID from response
    data = result.get("data", result)
    pid = project_id or data.get("id") or data.get("project", {}).get("id")

    if not pid:
        raise ValueError(
            f"SourcePrep did not return a project ID. Response: {result}"
        )

    logger.info(f"Project created with ID: {pid}")

    # Update project config with custom globs via PUT /projects/{id}
    config_update_url = f"{client.base_url}/projects/{pid}"
    config_body = {
        "config": {
            "include_globs": globs["include_globs"],
            "exclude_globs": globs["exclude_globs"],
            "use_gitignore": False,
        }
    }

    try:
        resp = requests.put(
            config_update_url, json=config_body, timeout=client.timeout
        )
        resp.raise_for_status()
        logger.info(f"Project config updated with config globs")
    except requests.RequestException as e:
        logger.warning(f"Failed to update project config: {e}")
        logger.warning(
            "Project created but globs not set. "
            "Set .sourceprep/team_config.json manually."
        )

    # Trigger initial build
    if trigger_build:
        build_url = f"{client.base_url}/projects/{pid}/build"
        build_body = {
            "include_globs": globs["include_globs"],
            "exclude_globs": globs["exclude_globs"],
            "use_gitignore": False,
        }

        try:
            resp = requests.post(
                build_url, json=build_body, timeout=60.0
            )
            resp.raise_for_status()
            logger.info(f"Build triggered for project {pid}")
        except requests.RequestException as e:
            logger.warning(f"Failed to trigger build: {e}")
            logger.warning(
                "Project registered but not built. "
                "Build manually via POST /projects/{pid}/build."
            )

    # Store project ID for client reuse
    client.project_id = pid

    return pid


def ensure_host_project(
    project_name: str = "halbert-host",
    host_root: str = "/",
    client: Optional[SourcePrepClient] = None,
    **kwargs: Any,
) -> str:
    """Ensure the host config project exists, creating it if needed.

    Checks existing projects first. If a project with the given name
    already exists, returns its ID. Otherwise, creates a new one.

    Args:
        project_name: Display name to search for or create.
        host_root: Root path for the config tree.
        client: Existing SourcePrepClient instance.
        **kwargs: Passed to register_host_project().

    Returns:
        The project ID.
    """
    if client is None:
        client = SourcePrepClient()

    if not client.health():
        raise ConnectionError(
            f"SourcePrep daemon not reachable at {client.base_url}."
        )

    import requests

    # List existing projects
    try:
        resp = requests.get(
            f"{client.base_url}/projects", timeout=client.timeout
        )
        resp.raise_for_status()
        result = resp.json()
        projects = result.get("data", result)
        if isinstance(projects, dict):
            projects = projects.get("projects", [])
    except (requests.RequestException, KeyError):
        projects = []

    # Search for existing project by name
    for proj in projects:
        if isinstance(proj, dict) and proj.get("name") == project_name:
            pid = proj.get("id", "")
            logger.info(f"Found existing project '{project_name}' with ID: {pid}")
            client.project_id = pid
            return pid

    # Not found — create it
    logger.info(f"Project '{project_name}' not found, creating...")
    return register_host_project(
        host_root=host_root,
        project_name=project_name,
        client=client,
        **kwargs,
    )
