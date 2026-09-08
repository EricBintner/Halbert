# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""``halbert consent-verify`` and ``halbert consent-rebuild`` — the two
commands the consent ledger ships, mirroring ``audit-verify`` /
``vault-rebuild`` (PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md §1.5).

Exit contract: 1 tampered (or projection disagrees), 2 cannot-check,
--json for machine-readable output. The wording discipline of §3.5
applies unchanged: the report never says "verified" — on one machine
the ledger and anything that could vouch for it share a disk, so the
claim it can back is "no tampering detected since this log began".
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from halbert_core.consent.store import ConsentStore
from halbert_core.persona.permission import ConsentDecision, Principal

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_grant(store: ConsentStore) -> None:
    store.record_decision(
        capability="sensor.screen",
        decision=ConsentDecision.GRANTED,
        principal=Principal(
            kind="owner", id="local:501", authn="os_reauth:touchid", at_machine=True
        ),
        surface="desktop-app/first-run",
        text_shown_sha256="9f2c" + "0" * 60,
    )


@pytest.fixture
def a_store(tmp_path):
    store = ConsentStore(
        data_dir=str(tmp_path / "data"), config_dir=str(tmp_path / "config")
    )
    _write_grant(store)
    return store


def _run_cli(command, *args):
    return subprocess.run(
        [sys.executable, "Halbert/main.py", command, *args],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def _dirs_args(store: ConsentStore):
    return ["--data-dir", store.data_dir, "--config-dir", store.config_dir]


# ---------------------------------------------------------------------------
# consent-verify.
# ---------------------------------------------------------------------------


def test_verify_exits_zero_on_a_clean_ledger(a_store):
    result = _run_cli("consent-verify", *_dirs_args(a_store))

    assert result.returncode == 0, result.stderr
    assert "no tampering detected" in result.stdout.lower()


def test_verify_never_says_verified(a_store):
    """§3.5's badge, in the consent command's form: the report may say
    "no tampering detected", never "verified"."""
    result = _run_cli("consent-verify", *_dirs_args(a_store))

    assert "verified" not in result.stdout.lower()


def test_verify_exits_two_when_it_cannot_check(tmp_path):
    """A data dir that cannot hold a ledger (it is a file) is "cannot
    check" — exit 2, never the same code as "checked and found nothing"."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("in the way")

    result = _run_cli(
        "consent-verify", "--data-dir", str(blocker), "--config-dir", str(tmp_path)
    )

    assert result.returncode == 2


def test_verify_exits_one_on_a_tampered_ledger(a_store):
    shard = sorted((Path(a_store.data_dir) / "consent").glob("*.jsonl"))[0]
    shard.write_text(
        shard.read_text().replace(
            '"capability": "sensor.screen"', '"capability": "sensor.camera"'
        )
    )

    result = _run_cli("consent-verify", *_dirs_args(a_store))

    assert result.returncode == 1
    assert "tampering detected" in result.stdout.lower()


def test_verify_exits_one_when_the_projection_disagrees(a_store):
    projection = Path(a_store.config_dir) / "consent-state.json"
    tampered = json.loads(projection.read_text())
    tampered["state"]["sensor.screen"]["decision"] = "denied"
    projection.write_text(json.dumps(tampered))

    result = _run_cli("consent-verify", *_dirs_args(a_store))

    assert result.returncode == 1
    assert "projection" in result.stdout.lower()


def test_verify_exits_zero_on_an_empty_first_boot_ledger(tmp_path):
    store = ConsentStore(
        data_dir=str(tmp_path / "data"), config_dir=str(tmp_path / "config")
    )

    result = _run_cli("consent-verify", *_dirs_args(store))

    assert result.returncode == 0, result.stderr
    assert "no records" in result.stdout.lower()


def test_verify_json_names_the_problem(a_store):
    shard = sorted((Path(a_store.data_dir) / "consent").glob("*.jsonl"))[0]
    shard.write_text(
        shard.read_text().replace(
            '"capability": "sensor.screen"', '"capability": "sensor.camera"'
        )
    )

    result = _run_cli("consent-verify", "--json", *_dirs_args(a_store))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["problems"]


def test_verify_json_on_a_clean_ledger(a_store):
    result = _run_cli("consent-verify", "--json", *_dirs_args(a_store))

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["projection"] == "agrees"
    assert payload["checked"] == 1


# ---------------------------------------------------------------------------
# consent-rebuild.
# ---------------------------------------------------------------------------


def test_rebuild_reprojects_a_clobbered_projection(a_store):
    projection = Path(a_store.config_dir) / "consent-state.json"
    projection.write_text("{}")

    result = _run_cli("consent-rebuild", *_dirs_args(a_store))

    assert result.returncode == 0, result.stderr
    assert (
        json.loads(projection.read_text())["state"]["sensor.screen"]["decision"]
        == "granted"
    )


def test_rebuild_json_carries_the_counts(a_store):
    result = _run_cli("consent-rebuild", "--json", *_dirs_args(a_store))

    payload = json.loads(result.stdout)
    assert payload["records"] == 1
    assert payload["capabilities"] == 1
    assert payload["path"].endswith("consent-state.json")


def test_rebuild_refuses_to_launder_a_tampered_ledger(a_store):
    """A rebuild from a tampered log would print "1 written" over a lie
    — the command must refuse instead of cleaning up the evidence."""
    shard = sorted((Path(a_store.data_dir) / "consent").glob("*.jsonl"))[0]
    shard.write_text(
        shard.read_text().replace(
            '"capability": "sensor.screen"', '"capability": "sensor.camera"'
        )
    )

    result = _run_cli("consent-rebuild", *_dirs_args(a_store))

    assert result.returncode == 1
    assert "refus" in result.stdout.lower()