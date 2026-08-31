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


def test_design_roles_are_registered():
    """The full design taxonomy: wave 1 (network, service, storage) plus
    credentials_admin, plus waves 2-3 (security, shell, package, boot,
    sharing). kernel_admin/users_admin/etc. stay deferred by design and
    must NOT appear here."""
    assert set(ROLES) == {
        "network_admin", "service_admin", "storage_admin", "credentials_admin",
        "security_admin", "shell_admin", "package_admin", "boot_admin",
        "sharing_admin",
    }


def test_every_role_has_a_manifest_that_exists():
    for name in ROLES:
        assert os.path.isfile(manifest_path_for(name)), f"{name} manifest missing"


def test_every_role_manifest_parses_and_has_content():
    for name in ROLES:
        man = Manifest.from_file(manifest_path_for(name))
        assert man.include, f"{name} manifest has no include patterns"


def test_staging_subdir_is_derived_from_role_name():
    assert staging_subdir_for("network_admin") == "network"
    assert staging_subdir_for("storage_admin") == "storage"
    assert staging_subdir_for("security_admin") == "security"
    assert staging_subdir_for("sharing_admin") == "sharing"


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
    """Wave-1 roles plus credentials are file-backed everywhere; no wave-one
    role leaves an empty scope on either platform."""
    for name in ("network_admin", "service_admin", "storage_admin", "credentials_admin"):
        for system in ("Linux", "Darwin"):
            assert ROLES[name].file_backed_on(system) is True, (
                f"{name} gated out on {system} would stage an empty scope"
            )


def test_every_role_is_file_backed_somewhere():
    """A role gated out of every platform would register a permanently
    empty scope — under scope_mode="hard" that excludes everything."""
    for name, role in ROLES.items():
        assert any(role.file_backed_on(s) for s in ("Linux", "Darwin")), name


def test_linux_sees_every_role():
    assert set(roles_for_platform("Linux")) == set(ROLES)


def test_platform_asymmetry_is_not_tidied_away():
    """The two platforms genuinely do not have the same roles (design doc,
    "do not tidy this away"). Homebrew is command-only on macOS — there is
    no package-manager config file to harvest — and macOS has no
    bootloader-config files (com.apple.Boot.plist holds one empty Kernel
    Flags key). Staging either on Darwin would create an empty scope."""
    assert ROLES["package_admin"].file_backed_on("Linux") is True
    assert ROLES["package_admin"].file_backed_on("Darwin") is False
    assert ROLES["boot_admin"].file_backed_on("Linux") is True
    assert ROLES["boot_admin"].file_backed_on("Darwin") is False
    assert set(roles_for_platform("Darwin")) == set(ROLES) - {
        "package_admin", "boot_admin"
    }


def test_security_shell_and_sharing_are_file_backed_on_both_platforms():
    """Wave-2/3 cross-platform roles, verified on a stock macOS host:
    /etc/pam.d (~25 files), /etc/sudoers, /etc/paths, /etc/zshrc,
    /etc/nfs.conf and com.apple.smb.server.plist all exist. A role that
    matches even one real file must be file-backed, or the scope ships
    empty under scope_mode="hard"."""
    for name in ("security_admin", "shell_admin", "sharing_admin"):
        assert ROLES[name].file_backed_on("Linux") is True
        assert ROLES[name].file_backed_on("Darwin") is True


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


# --- Waves 2-3: the rest of the design taxonomy ---------------------------
#
# Design: ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md, "Waves 2 and 3
# -- path sketches" and the membership table. Manifest entries are asserted
# verbatim so the registry, the manifests and the template cannot drift
# apart the way the wave-1 alias claims did (see the dangling-alias test).


def _manifest(role: str) -> Manifest:
    return Manifest.from_file(manifest_path_for(role))


def test_every_alias_target_exists():
    """network_admin claimed security_admin and storage_admin claimed
    sharing_admin while neither role existed -- the claims were dangling
    until waves 2-3 shipped. No alias may regress to pointing at nothing."""
    for name, role in ROLES.items():
        for alias in role.aliases_from:
            assert alias in ROLES, (
                f"{name} aliases {alias}, which is not registered"
            )


def test_grub_aliases_into_security_and_storage():
    """/etc/default/grub is primary to boot_admin but carries one hardening
    line and one storage line (rd.luks.*, resume=), so it is aliased into
    both -- the worst collision on Linux, one line per role."""
    assert "boot_admin" in ROLES["security_admin"].aliases_from
    assert "boot_admin" in ROLES["storage_admin"].aliases_from


def test_fstab_aliases_into_boot():
    """/etc/fstab and /etc/crypttab are primary to storage_admin and
    consulted at boot, so they are aliased into boot_admin."""
    assert "storage_admin" in ROLES["boot_admin"].aliases_from


def test_auto_upgrade_aliases_into_security():
    """Auto-upgrade configuration is primary to package_admin but answers
    "is this machine getting security patches", so it is aliased into
    security_admin."""
    assert "package_admin" in ROLES["security_admin"].aliases_from


def test_firewall_is_primary_to_security_not_network():
    """Design rev. 2 moved firewall rule files from network_admin to
    security_admin (they answer "is this machine hardened", not "how does
    this machine connect"), aliased back into network via the existing
    aliases_from claim."""
    security = _manifest("security_admin").include
    network = _manifest("network_admin").include
    for pattern in ("/etc/nftables.conf", "/etc/ufw/*", "/etc/firewalld/**/*.xml"):
        assert pattern in security, f"{pattern} must be primary to security_admin"
        assert pattern not in network, f"{pattern} must not be globbed into network_admin"


def test_security_hard_excludes_the_secret_backends():
    man = _manifest("security_admin")
    for pattern in ("/etc/shadow", "/etc/gshadow", "/etc/sssd/sssd.conf"):
        assert pattern in man.exclude


def test_security_covers_sudo_ssh_pam_and_kernel_aliases():
    """sudo/ssh/PAM are security's own; sysctl.d, modprobe.d and
    nsswitch.conf are kernel_admin/users_admin files held by
    security_admin until those roles ship (their promotion triggers),
    aliased into network_admin."""
    include = _manifest("security_admin").include
    for pattern in (
        "/etc/sudoers", "/etc/sudoers.d/*", "/etc/ssh/sshd_config",
        "/etc/pam.d/*", "/etc/sysctl.d/*", "/etc/modprobe.d/*",
        "/etc/nsswitch.conf",
    ):
        assert pattern in include


def test_shell_admin_covers_login_environment_on_both_platforms():
    """Linux: profile/environment/skel and the per-user rc files where the
    real value is; macOS: /etc/paths and friends (all plain text, small,
    high signal). Manifest.from_file expands ~, so per-user patterns are
    compared in their expanded form."""
    include = _manifest("shell_admin").include
    for pattern in (
        "/etc/profile", "/etc/profile.d/*.sh", "/etc/environment",
        "/etc/skel/*", "~/.bashrc", "~/.zshrc", "~/.profile",
        "/etc/paths", "/etc/paths.d/*", "/etc/zshrc", "/etc/manpaths",
    ):
        assert os.path.expanduser(pattern) in include


def test_shell_admin_excludes_the_binary_timezone_blob():
    """/etc/localtime is a symlink into the binary zoneinfo database -- the
    same text-index corruption zpool.cache demonstrated. /etc/timezone
    (Debian) carries the intent as text."""
    man = _manifest("shell_admin")
    assert "/etc/localtime" not in man.include
    assert "/etc/localtime" in man.exclude


def test_package_admin_covers_the_linux_repo_families():
    man = _manifest("package_admin")
    for pattern in (
        "/etc/apt/sources.list", "/etc/apt/sources.list.d/*",
        "/etc/pacman.conf", "/etc/zypp/**", "/etc/yum.repos.d/*.repo",
        "/etc/flatpak/remotes.d/*",
    ):
        assert pattern in man.include


def test_package_admin_excludes_apt_credentials():
    """/etc/apt/auth.conf.d/** holds repo credentials -- excluded outright
    rather than trusted to keyword redaction."""
    assert "/etc/apt/auth.conf.d/**" in _manifest("package_admin").exclude


def test_boot_admin_covers_grub_systemd_boot_and_initramfs():
    """Divergent grub paths (Debian/Arch /boot/grub vs RHEL/SUSE
    /boot/grub2 vs EFI), systemd-boot, and the three-way initramfs split."""
    include = _manifest("boot_admin").include
    for pattern in (
        "/etc/default/grub", "/boot/grub/grub.cfg", "/boot/grub2/grub.cfg",
        "/boot/loader/loader.conf", "/boot/loader/entries/*.conf",
        "/etc/kernel/cmdline", "/etc/mkinitcpio.conf", "/etc/dracut.conf",
        "/etc/initramfs-tools/**",
    ):
        assert pattern in include


def test_sharing_admin_covers_samba_nfs_avahi_and_darwin_smb():
    """Linux is rich (samba/NFS/avahi/rsyncd/vsftpd); macOS is thin but
    real: com.apple.smb.server.plist and /etc/nfs.conf both exist on a
    stock host, which is what keeps the role file-backed on Darwin."""
    include = _manifest("sharing_admin").include
    for pattern in (
        "/etc/samba/smb.conf", "/etc/exports", "/etc/nfs.conf",
        "/etc/avahi/avahi-daemon.conf", "/etc/rsyncd.conf",
        "/Library/Preferences/SystemConfiguration/com.apple.smb.server.plist",
    ):
        assert pattern in include


def test_mechanism_directories_are_never_assigned_by_glob():
    """Design corollary: /etc/default and /etc/sysconfig are role-agnostic
    containers -- grub, tlp, snapper, nfs and locale all live in
    /etc/default, so a glob over the container itself poisons every scope.
    Files must be named one by one; a subsystem-specific subdir with its
    own file-pattern glob is fine (network_admin's
    /etc/sysconfig/network-scripts/ifcfg-* is the design's own RHEL
    entry). Only a wildcard over the container's direct children fails."""
    for name in ROLES:
        for pattern in _manifest(name).include:
            for mechanism in ("/etc/default/", "/etc/sysconfig/"):
                if pattern.startswith(mechanism):
                    remainder = pattern[len(mechanism):]
                    assert not remainder.startswith("*"), (
                        f"{name} globs the mechanism dir {mechanism} ({pattern})"
                    )


def test_template_declares_the_wave_two_three_role_scopes():
    scopes = {s["id"]: s for s in _load_template()["scopes"]}
    for name in ("security_admin", "shell_admin", "package_admin",
                 "boot_admin", "sharing_admin"):
        assert name in scopes, f"{name} scope missing from template"
        assert scopes[name]["paths"] == [f"host/{staging_subdir_for(name)}"]
        assert scopes[name]["pipeline_profile"] == "system_config"
