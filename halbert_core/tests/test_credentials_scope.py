# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the credentials_admin scope — the credential file manifest."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from halbert_core.config.roles import (
    ROLES,
    manifest_path_for,
    roles_for_platform,
    staging_subdir_for,
)
from halbert_core.config.manifest import Manifest


class TestCredentialsRole:
    """The credentials_admin role is registered and reachable."""

    def test_role_exists(self):
        assert "credentials_admin" in ROLES

    def test_role_manifest_is_credentials_yml(self):
        assert ROLES["credentials_admin"].manifest == "credentials.yml"

    def test_role_file_backed_on_linux(self):
        assert ROLES["credentials_admin"].file_backed_on("Linux")

    def test_role_file_backed_on_darwin(self):
        assert ROLES["credentials_admin"].file_backed_on("Darwin")

    def test_role_in_platform_list_linux(self):
        assert "credentials_admin" in roles_for_platform("Linux")

    def test_role_in_platform_list_darwin(self):
        assert "credentials_admin" in roles_for_platform("Darwin")

    def test_manifest_file_exists(self):
        path = manifest_path_for("credentials_admin")
        assert os.path.exists(path), f"Manifest file not found: {path}"

    def test_staging_subdir(self):
        assert staging_subdir_for("credentials_admin") == "credentials"


class TestCredentialsManifest:
    """The credentials manifest includes the right files and excludes key material."""

    @pytest.fixture
    def manifest(self):
        path = manifest_path_for("credentials_admin")
        return Manifest.from_file(path)

    def test_includes_aws_credentials(self, manifest):
        paths = [p.replace(os.path.expanduser("~"), "~") for p in manifest.include]
        assert any("aws/credentials" in p for p in paths)

    def test_includes_aws_config(self, manifest):
        paths = [p.replace(os.path.expanduser("~"), "~") for p in manifest.include]
        assert any("aws/config" in p for p in paths)

    def test_includes_kube_config(self, manifest):
        paths = [p.replace(os.path.expanduser("~"), "~") for p in manifest.include]
        assert any("kube/config" in p for p in paths)

    def test_includes_netrc(self, manifest):
        paths = [p.replace(os.path.expanduser("~"), "~") for p in manifest.include]
        assert any(".netrc" in p for p in paths)

    def test_includes_ssh_config(self, manifest):
        paths = [p.replace(os.path.expanduser("~"), "~") for p in manifest.include]
        assert any("ssh/config" in p for p in paths)

    def test_includes_docker_config(self, manifest):
        paths = [p.replace(os.path.expanduser("~"), "~") for p in manifest.include]
        assert any("docker/config.json" in p for p in paths)

    def test_includes_env_files(self, manifest):
        paths = [p.replace(os.path.expanduser("~"), "~") for p in manifest.include]
        assert any(p.endswith(".env") for p in paths)
        assert any(".env.local" in p for p in paths)

    def test_includes_npmrc(self, manifest):
        paths = [p.replace(os.path.expanduser("~"), "~") for p in manifest.include]
        assert any(".npmrc" in p for p in paths)

    def test_includes_gitconfig(self, manifest):
        paths = [p.replace(os.path.expanduser("~"), "~") for p in manifest.include]
        assert any(".gitconfig" in p for p in paths)

    def test_excludes_private_keys(self, manifest):
        """Private key files are in the exclude list."""
        exclude_text = " ".join(manifest.exclude)
        assert "id_rsa" in exclude_text
        assert "*.pem" in exclude_text
        assert "*.key" in exclude_text
        assert "id_ecdsa" in exclude_text
        assert "id_ed25519" in exclude_text

    def test_excludes_authorized_keys(self, manifest):
        assert any("authorized_keys" in p for p in manifest.exclude)

    def test_excludes_env_example(self, manifest):
        assert any(".env.example" in p for p in manifest.exclude)


class TestCredentialsStaging:
    """Credential files stage correctly through the redaction pipeline."""

    def test_aws_credentials_stages_with_redaction(self, tmp_path):
        """~/.aws/credentials content is redacted when staged with redact=True."""
        from halbert_core.tools.register_host_project import _stage_one_file

        src = tmp_path / "aws_creds"
        src.write_text("[default]\naws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"
                       "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n")

        dest = tmp_path / "staged" / "credentials"
        dest.parent.mkdir(parents=True)
        _stage_one_file(src, dest, redact=True)

        staged = dest.read_text()
        assert "AKIAIOSFODNN7EXAMPLE" not in staged
        assert "wJalrXUtnFEMI" not in staged
        assert "<secret>" in staged

    def test_aws_credentials_stages_raw_when_unredacted(self, tmp_path):
        """~/.aws/credentials content is raw when staged with redact=False."""
        from halbert_core.tools.register_host_project import _stage_one_file

        src = tmp_path / "aws_creds"
        src.write_text("[default]\naws_access_key_id = AKIAIOSFODNN7EXAMPLE\n"
                       "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n")

        dest = tmp_path / "staged" / "credentials"
        dest.parent.mkdir(parents=True)
        _stage_one_file(src, dest, redact=False)

        staged = dest.read_text()
        assert "AKIAIOSFODNN7EXAMPLE" in staged
        assert "wJalrXUtnFEMI" in staged

    def test_kube_config_stages_with_redaction(self, tmp_path):
        """~/.kube/config content is redacted when staged with redact=True."""
        from halbert_core.tools.register_host_project import _stage_one_file

        src = tmp_path / "kube_config"
        src.write_text(
            "apiVersion: v1\n"
            "clusters:\n"
            "- cluster:\n"
            "    server: https://1.2.3.4:6443\n"
            "    certificate-authority-data: SGVsbG8gV29ybGQ=\n"
            "  name: prod\n"
            "users:\n"
            "- name: admin\n"
            "  user:\n"
            "    token: abc123secrettoken456\n"
        )

        dest = tmp_path / "staged" / "config"
        dest.parent.mkdir(parents=True)
        _stage_one_file(src, dest, redact=True)

        staged = dest.read_text()
        assert "abc123secrettoken456" not in staged
        assert "<secret>" in staged

    def test_env_file_stages_with_redaction(self, tmp_path):
        """.env file content is redacted when staged with redact=True."""
        from halbert_core.tools.register_host_project import _stage_one_file

        src = tmp_path / "env_file"
        src.write_text(
            "DATABASE_URL=postgres://user:secretpass@db.example.com:5432/mydb\n"
            "API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123456789\n"
            "SECRET_KEY=hunter2supersecret\n"
            "DEBUG=true\n"
        )

        dest = tmp_path / "staged" / ".env"
        dest.parent.mkdir(parents=True)
        _stage_one_file(src, dest, redact=True)

        staged = dest.read_text()
        assert "secretpass" not in staged
        assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in staged
        assert "hunter2supersecret" not in staged
        assert "DEBUG=true" in staged  # non-secret survives

    def test_ssh_config_stages(self, tmp_path):
        """~/.ssh/config is staged (it's operational data, not secrets)."""
        from halbert_core.tools.register_host_project import _stage_one_file

        src = tmp_path / "ssh_config"
        src.write_text(
            "Host prod\n"
            "    HostName prod.example.com\n"
            "    User admin\n"
            "    IdentityFile ~/.ssh/id_ed25519\n"
            "    Port 2222\n"
        )

        dest = tmp_path / "staged" / "ssh_config"
        dest.parent.mkdir(parents=True)
        _stage_one_file(src, dest, redact=True)

        staged = dest.read_text()
        # Operational data survives
        assert "prod.example.com" in staged
        assert "Port 2222" in staged
        assert "IdentityFile" in staged
