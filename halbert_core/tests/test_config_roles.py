# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Role manifests and the role registry."""
from __future__ import annotations

import os

from halbert_core.config.manifest import Manifest


def test_manifest_expands_home_in_include(tmp_path, monkeypatch):
    """Role manifests reference per-user paths like ~/Library/LaunchAgents."""
    fake_home = tmp_path / "home" / "tester"
    fake_home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))

    man_file = tmp_path / "manifest.yml"
    man_file.write_text(
        "include:\n  - ~/Library/LaunchAgents/*.plist\nexclude: []\nparsers: {}\n"
    )

    man = Manifest.from_file(str(man_file))
    assert man.include[0].startswith(str(fake_home))
    assert "~" not in man.include[0]


def test_manifest_expands_home_in_exclude(tmp_path, monkeypatch):
    fake_home = tmp_path / "home" / "tester"
    fake_home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))

    man_file = tmp_path / "manifest.yml"
    man_file.write_text(
        "include:\n  - /etc/*.conf\nexclude:\n  - ~/private/**\nparsers: {}\n"
    )

    man = Manifest.from_file(str(man_file))
    assert man.exclude[0].startswith(str(fake_home))


def test_manifest_iter_paths_finds_home_relative_file(tmp_path, monkeypatch):
    fake_home = tmp_path / "home" / "tester"
    agents = fake_home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.example.plist").write_text("<plist/>")
    monkeypatch.setenv("HOME", str(fake_home))

    man_file = tmp_path / "manifest.yml"
    man_file.write_text(
        "include:\n  - ~/Library/LaunchAgents/*.plist\nexclude: []\nparsers: {}\n"
    )

    found = Manifest.from_file(str(man_file)).iter_paths()
    assert any(p.endswith("com.example.plist") for p in found)


def test_absolute_paths_are_unchanged(tmp_path):
    man_file = tmp_path / "manifest.yml"
    man_file.write_text("include:\n  - /etc/fstab\nexclude: []\nparsers: {}\n")
    assert Manifest.from_file(str(man_file)).include == ["/etc/fstab"]


from halbert_core.config.roles import (
    ROLES,
    RoleScope,
    manifest_path_for,
    roles_for_platform,
    staging_subdir_for,
)


def test_wave_one_roles_are_registered():
    assert set(ROLES) == {"network_admin", "service_admin", "storage_admin"}


def test_every_role_has_a_manifest_that_exists():
    for name in ROLES:
        assert os.path.isfile(manifest_path_for(name)), f"{name} manifest missing"


def test_staging_subdir_is_derived_from_role_name():
    assert staging_subdir_for("network_admin") == "network"
    assert staging_subdir_for("storage_admin") == "storage"


def test_storage_is_file_backed_on_macos_too():
    """macOS storage is thin, not absent: autofs is real mount intent.

    The manifest matches /etc/auto_master, /etc/auto_home and
    /etc/autofs.conf on a stock host (verified: 3 files). Gating the role
    out of Darwin left those unstaged and the scope empty, and under
    scope_mode="hard" an empty mask excludes everything rather than
    narrowing -- a broken scope, not a thin one.
    """
    assert ROLES["storage_admin"].file_backed_on("Linux") is True
    assert ROLES["storage_admin"].file_backed_on("Darwin") is True


def test_network_is_file_backed_on_both_platforms():
    assert ROLES["network_admin"].file_backed_on("Linux") is True
    assert ROLES["network_admin"].file_backed_on("Darwin") is True


def test_every_wave_one_role_is_file_backed_on_both_platforms():
    """No wave-one role leaves an empty scope on either platform."""
    for system in ("Linux", "Darwin"):
        assert set(roles_for_platform(system)) == set(ROLES), (
            f"a role is gated out on {system}, which would stage an empty scope"
        )


def test_roles_for_platform_still_drops_a_docs_only_role(monkeypatch):
    """No role uses the docs-only gate today; it must still work if one does.

    Asserted against an injected role rather than a real one, so the day a
    role legitimately has no files on a platform the filter is known good.
    """
    from halbert_core.config import roles as roles_mod

    monkeypatch.setitem(
        roles_mod.ROLES,
        "linux_only_admin",
        RoleScope(
            name="linux_only_admin",
            manifest="storage.yml",
            file_backed_platforms=("Linux",),
        ),
    )
    assert "linux_only_admin" in roles_for_platform("Linux")
    assert "linux_only_admin" not in roles_for_platform("Darwin")


def test_firewall_files_alias_network_into_security():
    """Design decision: firewall is primary to security, aliased to network."""
    assert "security_admin" in ROLES["network_admin"].aliases_from


def test_role_scope_is_immutable():
    import dataclasses

    assert dataclasses.is_dataclass(RoleScope)
    assert ROLES["network_admin"].__dataclass_params__.frozen


# --- Binary files must not enter a text index ----------------------------


def test_zpool_cache_is_excluded_not_harvested():
    """/etc/zfs/zpool.cache is a packed nvlist, not a config file.

    Pool topology is available live from `zpool status`, which is
    command-output and out of scope for a file manifest.
    """
    man = Manifest.from_file(manifest_path_for("storage_admin"))
    assert "/etc/zfs/zpool.cache" not in man.include
    assert "/etc/zfs/zpool.cache" in man.exclude


def test_a_packed_nvlist_would_index_as_replacement_soup(tmp_path):
    """Why the exclusion exists, demonstrated against the real parser.

    config/parser.py checks only the `.plist` extension before falling back
    to a UTF-8 read with errors="replace"; zpool.cache has no extension that
    branch recognises. The mangled text is what gets hashed, so drift
    detection compares corruption to corruption -- two genuinely different
    pools can produce the same hash.
    """
    from halbert_core.config.parser import parse as parse_config

    blob = b"\x00\x00\x00\x01\x00\x00\x00\x08version\x00\x00\x00\x1c\xff\xfe\x80"
    a = tmp_path / "zpool.cache"
    a.write_bytes(blob)
    b = tmp_path / "other.cache"
    b.write_bytes(blob.replace(b"\xff\xfe\x80", b"\xff\xfd\x81"))

    parsed_a, parsed_b = parse_config(str(a)), parse_config(str(b))
    assert any("�" in ln["text"] for ln in parsed_a["lines"])
    assert parsed_a["hash"] == parsed_b["hash"], (
        "if this ever fails the parser learned to see bytes, and the "
        "exclusion could be revisited"
    )


def test_an_excluded_path_is_really_dropped(tmp_path):
    """The exclusion is enforced by iter_paths, not just documented."""
    zfs = tmp_path / "etc" / "zfs"
    zfs.mkdir(parents=True)
    (zfs / "zpool.cache").write_bytes(b"\x00\x00\x00\x01nvlist")
    (zfs / "vdev_id.conf").write_text("alias d1 /dev/disk/by-path/x\n")

    man_file = tmp_path / "storage.yml"
    man_file.write_text(
        f"include:\n  - {zfs}/*\nexclude:\n  - {zfs}/zpool.cache\nparsers: {{}}\n"
    )

    found = Manifest.from_file(str(man_file)).iter_paths()
    assert [os.path.basename(p) for p in found] == ["vdev_id.conf"]


# --- The role axis must be registered as SourcePrep scopes ----------------

import yaml


def _load_template():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(
        here, "halbert_core", "integrations", "sourceprep_template.yml"
    )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_template_declares_all_wave_one_role_scopes():
    scope_ids = {s["id"] for s in _load_template()["scopes"]}
    assert {"network_admin", "service_admin", "storage_admin"} <= scope_ids


def test_role_scopes_point_at_their_staging_subdir():
    scopes = {s["id"]: s for s in _load_template()["scopes"]}
    assert scopes["network_admin"]["paths"] == ["host/network"]
    assert scopes["service_admin"]["paths"] == ["host/service"]
    assert scopes["storage_admin"]["paths"] == ["host/storage"]


def test_role_scopes_use_system_config_profile():
    scopes = {s["id"]: s for s in _load_template()["scopes"]}
    for name in ("network_admin", "service_admin", "storage_admin"):
        assert scopes[name]["pipeline_profile"] == "system_config"


def test_existing_scopes_are_preserved():
    """Role scopes are additive; the platform axis must survive."""
    scope_ids = {s["id"] for s in _load_template()["scopes"]}
    assert {"host", "knowledge-linux", "knowledge-macos"} <= scope_ids


def test_every_template_role_scope_is_in_the_registry():
    """Template and registry must not drift apart."""
    from halbert_core.config.roles import ROLES

    scope_ids = {s["id"] for s in _load_template()["scopes"]}
    for role in ROLES:
        assert role in scope_ids, f"{role} in registry but not template"


# --- The manifests must reach a wheel ------------------------------------
#
# `test_every_role_has_a_manifest_that_exists` passes in a checkout and
# cannot see this: production resolves the manifests relative to the
# *installed package*, and a repo-relative path does not exist there.


def _package_root() -> str:
    from halbert_core.config import roles as roles_mod

    return os.path.dirname(os.path.dirname(os.path.abspath(roles_mod.__file__)))


def test_role_manifests_live_inside_the_installed_package():
    """A path outside the package cannot survive `pip install`.

    Resolved as `<package>/../../../config/scopes`, every manifest was
    missing under a wheel: stage_role_tree raised FileNotFoundError,
    _stage_host_tree swallowed it as non-fatal, and sourceprep_template.yml
    then registered host/network, host/service and host/storage against
    directories that were never created -- the empty-scope condition
    roles.py warns about, where scope_mode="hard" makes an empty mask
    exclude everything rather than narrow.
    """
    root = _package_root() + os.sep
    for name in ROLES:
        path = os.path.abspath(manifest_path_for(name))
        assert path.startswith(root), f"{name} manifest is outside the package: {path}"
        assert os.path.isfile(path), f"{name} manifest missing: {path}"


def _package_data_globs():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    pyproject = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyproject.toml"
    )
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    return data.get("tool", {}).get("setuptools", {}).get("package-data", {})


def test_pyproject_declares_the_manifests_as_package_data():
    """Living inside the package is necessary but not sufficient.

    Verified by building a wheel from this pyproject before the fix: with
    only `include = ["halbert_core*"]` and no package-data stanza, the wheel
    held 331 entries and *zero* non-.py files -- so even
    integrations/sourceprep_template.yml, which already lived inside the
    package, was absent from every non-editable install.
    """
    import fnmatch

    globs = _package_data_globs()
    assert globs, "no [tool.setuptools.package-data]: a wheel drops every data file"

    root = _package_root()
    for name in ROLES:
        rel = os.path.relpath(os.path.abspath(manifest_path_for(name)), root)
        # `halbert_core.config` + `scopes/*.yml` -> `config/scopes/<name>.yml`
        matched = any(
            fnmatch.fnmatch(rel, os.path.join(*pkg.split(".")[1:], pattern))
            for pkg, patterns in globs.items()
            for pattern in patterns
        )
        assert matched, f"{rel} is not covered by any package-data glob"


def test_the_sourceprep_template_is_package_data_too():
    """It is read at registration time and was missing from the wheel for
    exactly the same reason the manifests were."""
    import fnmatch

    globs = _package_data_globs()
    rel = os.path.join("integrations", "sourceprep_template.yml")
    assert os.path.isfile(os.path.join(_package_root(), rel))
    assert any(
        fnmatch.fnmatch(rel, os.path.join(*pkg.split(".")[1:], pattern))
        for pkg, patterns in globs.items()
        for pattern in patterns
    ), f"{rel} is not covered by any package-data glob"
