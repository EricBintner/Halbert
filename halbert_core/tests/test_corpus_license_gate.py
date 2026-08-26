# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Tests for the corpus licensing policy and build-time gate.

Covers the two release blockers this machinery exists for:

  LEG-CRIT-01  CC BY-NC 4.0 (SS64) content must never enter a commercial
               bundle — by path or by record — and excluding it must not cost
               the user any macOS command coverage.
  LEG-MAJ-05   GNU FDL 1.3 (Arch Wiki) content must never enter a macOS
               bundle, and specifically never the DRM-wrapped App Store one.

The negative tests matter more than the positive ones: a gate that cannot fail
is not a gate. Each planted-violation test asserts the gate catches something
that would otherwise ship.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "halbert_core"))

from halbert_core.corpus.license_policy import (  # noqa: E402
    LicensePolicy,
    LicenseViolation,
)

DATA_DIR = REPO_ROOT / "data"
GATE = REPO_ROOT / "scripts" / "corpus_license_gate.py"

COMMERCIAL_CHANNELS = ["macos-pro", "macos-app-store"]
MACOS_CHANNELS = ["oss-macos", "macos-pro", "macos-app-store"]


@pytest.fixture(scope="module")
def policy() -> LicensePolicy:
    return LicensePolicy.load(repo_root=REPO_ROOT)


def _write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )


@pytest.fixture
def macos_tree(tmp_path: Path) -> Path:
    """A minimal, clean macOS corpus tree standing in for a staged bundle."""
    root = tmp_path / "data"
    _write_jsonl(
        root / "macos" / "support" / "macos_command_guides.jsonl",
        [
            {
                "id": "halbert-macos-cmd-ls",
                "title": "macOS Command: ls",
                "content": "# ls",
                "source": "halbert-macos-command-guides",
                "license_spdx": "LicenseRef-Halbert-Corpus-1.0",
                "metadata": {"command": "ls", "platform": "macos"},
            }
        ],
    )
    _write_jsonl(
        root / "bsd" / "freebsd-handbook" / "freebsd_handbook.jsonl",
        [{"id": "fb-1", "content": "handbook", "source": "freebsd-handbook"}],
    )
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Policy configuration is well-formed
# ---------------------------------------------------------------------------


def test_every_manifest_source_has_a_registered_license(policy):
    """An unclassified source is a licensing hole; fail loudly at test time."""
    unknown = []
    for name, meta in policy.manifest["sources"].items():
        spdx = meta.get("license_spdx", "")
        if not spdx:
            unknown.append(f"{name}: no license_spdx")
        elif policy.terms(spdx) is None:
            unknown.append(f"{name}: '{spdx}' is not in config/licensing.yml")
    assert not unknown, "unclassified corpus sources: " + "; ".join(unknown)


def test_expected_channels_exist(policy):
    for channel in ["oss-linux", *MACOS_CHANNELS, "hf-dataset"]:
        assert channel in policy.channels


def test_unknown_channel_raises(policy):
    with pytest.raises(KeyError):
        policy.channel("windows-store")


def test_commercial_channels_forbid_noncommercial_licenses(policy):
    for channel in COMMERCIAL_CHANNELS:
        assert policy.channel(channel).require_commercial_use == "allowed"


def test_app_store_channel_rejects_drm_conflicting_licenses(policy):
    """GFDL forbids technical measures; the App Store applies them."""
    channel = policy.channel("macos-app-store")
    assert channel.drm is True
    assert channel.allow_drm_conflict is False
    assert policy.terms("GFDL-1.3-or-later").drm_conflict is True


# ---------------------------------------------------------------------------
# LEG-MAJ-05 — Arch Wiki (GNU FDL) build gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("channel", MACOS_CHANNELS)
def test_arch_wiki_excluded_from_every_macos_channel(policy, channel):
    included = policy.included_paths(channel)
    leaked = [p for p in included if "arch" in p]
    assert not leaked, f"Arch Wiki paths leaked into {channel}: {leaked}"


def test_arch_wiki_ships_in_the_linux_community_build(policy):
    """The exclusion is macOS-specific, not a blanket ban — GPL-3.0 Linux
    builds are DRM-free and may carry copyleft documentation."""
    included = policy.included_paths("oss-linux")
    assert any("arch-wiki" in p for p in included)


def test_arch_wiki_exclusion_reason_is_recorded(policy):
    report = policy.evaluate("macos-app-store")
    arch = [d for d in report.excluded if d.path.startswith("linux/arch-wiki/")]
    assert arch, "arch-wiki/ was not evaluated at all"
    reasons = " ".join(arch[0].reasons)
    assert "copyleft" in reasons
    assert "DRM" in reasons or "technical restrictions" in reasons


@pytest.mark.parametrize("channel", MACOS_CHANNELS)
def test_planted_arch_wiki_fails_the_macos_audit(policy, macos_tree, channel):
    _write_jsonl(
        macos_tree / "linux" / "arch-wiki" / "arch_wiki.jsonl",
        [{"id": "arch-1", "content": "pacman", "source": "arch-wiki"}],
    )
    violations = policy.audit_tree(macos_tree, channel)
    assert violations, f"{channel} audit accepted Arch Wiki content"
    assert any("arch-wiki" in v.path for v in violations)


def test_no_arch_wiki_in_the_real_macos_data_tree(policy):
    """The checked-in data/macos + data/bsd trees must be Arch-free."""
    for subtree in ("macos", "bsd"):
        root = DATA_DIR / subtree
        if not root.exists():
            continue
        assert not list(root.rglob("*arch*")), f"Arch content found under data/{subtree}"


# ---------------------------------------------------------------------------
# LEG-CRIT-01 — SS64 / CC BY-NC quarantine
# ---------------------------------------------------------------------------


def test_ss64_is_quarantined_out_of_the_shippable_corpus():
    support = DATA_DIR / "macos" / "support" / "macos_support.jsonl"
    if not support.exists():
        pytest.skip("corpus not present in this checkout")
    sources = {
        json.loads(line)["source"]
        for line in support.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert "ss64-macos" not in sources, (
        "CC BY-NC 4.0 SS64 records are back in the shippable macOS corpus — "
        "re-run scripts/quarantine_ss64.py"
    )


def test_quarantined_records_carry_explicit_license_metadata():
    quarantine = DATA_DIR / "non-commercial" / "macos_ss64" / "ss64_macos.jsonl"
    if not quarantine.exists():
        pytest.skip("quarantine not present in this checkout")
    for line in quarantine.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        assert record["license_spdx"] == "CC-BY-NC-4.0"
        assert record["attribution"]


@pytest.mark.parametrize("channel", COMMERCIAL_CHANNELS)
def test_noncommercial_path_never_ships_commercially(policy, channel):
    assert not [p for p in policy.included_paths(channel) if p.startswith("non-commercial/")]


def test_noncommercial_path_excluded_from_every_channel(policy):
    """No channel ships the quarantine — not even the free ones, so that one
    corpus build serves every macOS channel."""
    for channel in policy.channels:
        included = policy.included_paths(channel)
        assert not [p for p in included if p.startswith("non-commercial/")], channel


@pytest.mark.parametrize("channel", COMMERCIAL_CHANNELS)
def test_planted_noncommercial_path_fails_audit(policy, macos_tree, channel):
    _write_jsonl(
        macos_tree / "non-commercial" / "macos_ss64" / "ss64_macos.jsonl",
        [{"id": "x", "source": "ss64-macos", "license_spdx": "CC-BY-NC-4.0"}],
    )
    violations = policy.audit_tree(macos_tree, channel)
    assert any(v.kind == "denied_path" for v in violations)


@pytest.mark.parametrize("channel", COMMERCIAL_CHANNELS)
def test_ss64_records_hidden_in_an_allowed_path_still_fail(policy, macos_tree, channel):
    """The case a path allowlist alone would miss: quarantined records smuggled
    into a file that legitimately ships."""
    target = macos_tree / "macos" / "support" / "macos_support.jsonl"
    _write_jsonl(
        target,
        [
            {"id": "ok", "source": "halbert-macos-guides", "content": "fine"},
            {"id": "macos-cmd-cat", "source": "ss64-macos", "content": "smuggled"},
        ],
    )
    violations = policy.audit_tree(macos_tree, channel)
    assert any(v.kind == "quarantined_record" for v in violations), (
        "record-level quarantine did not fire"
    )


@pytest.mark.parametrize("channel", COMMERCIAL_CHANNELS)
def test_record_level_cc_by_nc_tag_fails(policy, macos_tree, channel):
    """Even with an unknown `source`, an explicit CC BY-NC tag is caught."""
    _write_jsonl(
        macos_tree / "macos" / "support" / "extra.jsonl",
        [{"id": "y", "source": "somewhere-new", "license_spdx": "CC-BY-NC-4.0"}],
    )
    violations = policy.audit_tree(macos_tree, channel)
    assert any(v.license_spdx == "CC-BY-NC-4.0" for v in violations)


def test_unclassifiable_record_license_is_a_violation(policy, macos_tree):
    _write_jsonl(
        macos_tree / "macos" / "support" / "mystery.jsonl",
        [{"id": "z", "source": "mystery", "license": "Some Bespoke EULA v3"}],
    )
    violations = policy.audit_tree(macos_tree, "macos-pro")
    assert any("not in the licence registry" in v.detail for v in violations)


def test_known_free_text_license_strings_resolve(policy):
    """Scraper-written strings must map onto the registry, or every real
    bundle fails the gate for the wrong reason."""
    for raw, expected in [
        ("FreeBSD Documentation License", "BSD-Documentation"),
        ("CC BY-SA 4.0", "CC-BY-SA-4.0"),
        ("BSD-like (MacPorts)", "MacPorts-BSD-like"),
        ("local", "APSL-2.0"),
    ]:
        assert policy.resolve(raw) == expected
        assert policy.terms(raw) is not None


# ---------------------------------------------------------------------------
# Replacement coverage — excluding SS64 must cost the user nothing
# ---------------------------------------------------------------------------


def test_halbert_guides_fully_replace_the_quarantined_commands(policy):
    gaps = policy.coverage_gaps()
    assert "macos-command-reference" in gaps
    assert not gaps["macos-command-reference"], (
        "commands lost their replacement coverage: "
        + ", ".join(gaps["macos-command-reference"][:20])
    )


def test_replacement_guides_are_halbert_licensed():
    replacement = DATA_DIR / "macos" / "support" / "macos_command_guides.jsonl"
    if not replacement.exists():
        pytest.skip("replacement corpus not generated in this checkout")
    records = [
        json.loads(line)
        for line in replacement.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records
    for record in records:
        assert record["license_spdx"] == "LicenseRef-Halbert-Corpus-1.0"
        assert record["source"] == "halbert-macos-command-guides"
        assert record["metadata"]["command"]
        assert len(record["content"]) > 400, f"{record['id']} is too thin to be a replacement"


def test_replacement_generator_output_is_current():
    """The checked-in JSONL must match what the generator produces, so the
    corpus cannot drift away from its auditable source."""
    script = REPO_ROOT / "scripts" / "generate_macos_command_guides.py"
    if not script.exists():
        pytest.skip("generator not present")
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Platform separation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("channel", MACOS_CHANNELS)
def test_no_linux_paths_in_macos_channels(policy, channel):
    assert not [p for p in policy.included_paths(channel) if p.startswith("linux/")]


def test_no_macos_paths_in_the_linux_channel(policy):
    included = policy.included_paths("oss-linux")
    assert not [p for p in included if p.startswith("macos/") or p.startswith("bsd/")]


def test_planted_linux_content_fails_a_macos_audit(policy, macos_tree):
    _write_jsonl(
        macos_tree / "linux" / "systemd-docs" / "systemd.jsonl",
        [{"id": "sd-1", "content": "systemctl", "source": "systemd-docs"}],
    )
    violations = policy.audit_tree(macos_tree, "macos-pro")
    assert any(v.kind == "platform_root" for v in violations)


def test_manifest_metadata_is_allowed_at_the_tree_root(policy, macos_tree):
    """The manifest must travel with the bundle, so it is not a stray file."""
    violations = policy.audit_tree(macos_tree, "macos-pro")
    assert not [v for v in violations if v.path == "manifest.json"]


def test_stray_root_file_is_rejected(policy, macos_tree):
    (macos_tree / "leftover.jsonl").write_text('{"id":"x"}\n', encoding="utf-8")
    violations = policy.audit_tree(macos_tree, "macos-pro")
    assert any(v.kind == "unexpected_root_file" for v in violations)


# ---------------------------------------------------------------------------
# Enforcement surface
# ---------------------------------------------------------------------------


def test_clean_tree_passes(policy, macos_tree):
    for channel in MACOS_CHANNELS:
        assert policy.audit_tree(macos_tree, channel) == []


def test_assert_tree_clean_raises_on_violation(policy, macos_tree):
    _write_jsonl(
        macos_tree / "non-commercial" / "x" / "x.jsonl",
        [{"id": "x", "source": "ss64-macos"}],
    )
    with pytest.raises(LicenseViolation) as excinfo:
        policy.assert_tree_clean(macos_tree, "macos-pro")
    assert excinfo.value.channel == "macos-pro"
    assert excinfo.value.violations


def test_gate_cli_exits_nonzero_on_a_dirty_bundle(macos_tree):
    _write_jsonl(
        macos_tree / "non-commercial" / "macos_ss64" / "ss64.jsonl",
        [{"id": "x", "source": "ss64-macos", "license_spdx": "CC-BY-NC-4.0"}],
    )
    result = subprocess.run(
        [
            sys.executable,
            str(GATE),
            "--channel",
            "macos-pro",
            "--bundle",
            str(macos_tree),
            "--no-color",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 1, result.stdout
    assert "FAIL" in result.stdout


def test_gate_cli_exits_zero_on_a_clean_bundle(macos_tree):
    result = subprocess.run(
        [
            sys.executable,
            str(GATE),
            "--channel",
            "macos-app-store",
            "--bundle",
            str(macos_tree),
            "--no-color",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_gate_cli_print_paths_matches_the_policy(policy):
    result = subprocess.run(
        [sys.executable, str(GATE), "--channel", "macos-pro", "--print-paths"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    printed = [line for line in result.stdout.splitlines() if line.strip()]
    assert printed == policy.included_paths("macos-pro")


def test_build_scripts_gate_before_packaging():
    """A build script that bundles data/ directly would bypass every check
    above, so assert the wiring itself."""
    for name in ("build-linux.sh", "build-macos.sh"):
        script = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "corpus_license_gate.py" in script, f"{name} does not run the licence gate"
        assert "--add-data $STAGE_DIR:data" in script, (
            f"{name} bundles something other than the gated, staged corpus"
        )
        assert "--add-data $PROJECT_ROOT/data" not in script, (
            f"{name} still bundles the raw data tree, which contains the quarantine"
        )


# ---------------------------------------------------------------------------
# LEG-CRIT-03 — no copyleft dependency in the Mac App Store binary
# ---------------------------------------------------------------------------


def _load_dep_checker():
    import importlib.util

    path = REPO_ROOT / "scripts" / "check_appstore_deps.py"
    spec = importlib.util.spec_from_file_location("check_appstore_deps", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def deps():
    return _load_dep_checker()


@pytest.fixture(scope="module")
def dep_register(deps):
    import yaml

    return yaml.safe_load(
        (REPO_ROOT / "config" / "dependency-licenses.yml").read_text(encoding="utf-8")
    )


def test_real_dependency_manifests_pass_the_app_store_check():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_appstore_deps.py"), "--no-color"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_dual_licensed_dependency_counts_as_permissive(deps, dep_register):
    classes = dep_register["copyleft_classes"]
    assert deps.classify("MIT OR Apache-2.0", classes) == "permissive"
    assert deps.classify("Apache-2.0 OR MIT", classes) == "permissive"


def test_gpl_and_lgpl_are_classified_as_copyleft(deps, dep_register):
    classes = dep_register["copyleft_classes"]
    assert deps.classify("GPL-3.0-or-later", classes) == "strong"
    assert deps.classify("LGPL-2.1-or-later", classes) == "weak"


def test_a_new_gpl_dependency_blocks_the_app_store_build(deps, dep_register):
    register = dict(dep_register)
    register["python"] = dict(register["python"])
    register["python"]["readline-gpl"] = {"spdx": "GPL-3.0-or-later"}
    failures, _, _ = deps.check(
        "python",
        [{"name": "readline-gpl", "marker": "", "extra": ""}],
        register,
        register["copyleft_classes"],
        colour=False,
    )
    assert failures and "GPL-3.0-or-later" in failures[0]


def test_an_unclassified_dependency_blocks_the_build(deps, dep_register):
    failures, _, _ = deps.check(
        "python",
        [{"name": "some-brand-new-package", "marker": "", "extra": ""}],
        dep_register,
        dep_register["copyleft_classes"],
        colour=False,
    )
    assert failures and "no entry" in failures[0]


def test_linux_only_copyleft_dependency_needs_its_platform_marker(deps, dep_register):
    """systemd-python is LGPL. It is only acceptable because pyproject keeps it
    off macOS — drop the marker and the check must fail."""
    without_marker, _, _ = deps.check(
        "python",
        [{"name": "systemd-python", "marker": "", "extra": ""}],
        dep_register,
        dep_register["copyleft_classes"],
        colour=False,
    )
    assert without_marker and "platform marker" in without_marker[0]

    with_marker, warnings, _ = deps.check(
        "python",
        [{"name": "systemd-python", "marker": "platform_system == 'Linux'", "extra": ""}],
        dep_register,
        dep_register["copyleft_classes"],
        colour=False,
    )
    assert not with_marker
    assert warnings and "excluded from macOS" in warnings[0]


def test_pyproject_still_marks_systemd_python_as_linux_only(deps):
    parsed = deps.parse_pyproject(REPO_ROOT / "halbert_core" / "pyproject.toml")
    entry = next((d for d in parsed if d["name"] == "systemd-python"), None)
    assert entry is not None, "systemd-python vanished from pyproject.toml"
    assert deps.marker_excludes_macos(entry["marker"]), (
        f"systemd-python (LGPL) is no longer excluded from macOS: marker={entry['marker']!r}"
    )


def test_every_declared_dependency_is_registered(deps, dep_register):
    """A dependency added to a manifest without a register entry is a
    licensing unknown; catch it in CI, not at submission time."""
    manifests = {
        "python": deps.parse_pyproject(REPO_ROOT / "halbert_core" / "pyproject.toml"),
        "rust": deps.parse_cargo(deps.CARGO_TOML),
        "npm": deps.parse_package_json(deps.PACKAGE_JSON),
    }
    missing = []
    for ecosystem, parsed in manifests.items():
        known = {k.lower() for k in (dep_register.get(ecosystem) or {})}
        for dep in parsed:
            if dep["name"].lower() not in known:
                missing.append(f"{ecosystem}:{dep['name']}")
    assert not missing, (
        "dependencies missing from config/dependency-licenses.yml: " + ", ".join(sorted(set(missing)))
    )
