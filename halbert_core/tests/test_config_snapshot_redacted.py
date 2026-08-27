# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""`snapshot()`'s canonical JSON must carry no plaintext credential.

The raw-text sink under `data/config/raw/` has been redacted since Phase A,
but the canonical JSON written one line later carried the same file twice
over -- once parsed into `sections`/`tree`, once as a full-text `lines`
array -- with every value verbatim. `CANON_DIR` is not staged into a
searchable scope, so this was never an *index* leak; it is plaintext
credentials on disk from the one pipeline whose stated job includes removing
them, and both `drift.py` and `edge_extractor.py` read it.

The fix must not disturb `hash`. Drift detection compares hashes to decide
whether a file changed at all, so a hash computed over redacted content would
report every credential-bearing file as modified on the first run after the
change and then never again -- silently, because the comparison would still
be self-consistent.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from halbert_core.config import snapshot as snapshot_mod
from halbert_core.config.parser import parse as parse_config

# Distinctive enough that an `in` test over the whole file is meaningful.
WG_PRIVATE_KEY = "uJ7T3XwQZ1sPRIVATEKEYVALUE9aBcDeFgHiJkLmNoPq="
WG_PRESHARED_KEY = "k9QmPRESHAREDKEYVALUE7xY2zQ8wErTyUiOpAsDfGh="
PSK_PASSPHRASE = "correct horse battery staple"
YAML_PSK = "guestwifisecret123"
YAML_PASSWORD = "hunter2guestpassword"
PEM_BODY_1 = "MIIBVgIBADANBgkqPEMBODYSECRETLINE1w0BAQEFAASCAUAwggE8AgEA"
PEM_BODY_2 = "AkEA1QIDAQABAkAPEMBODYSECRETLINE2BgkqhkiG9w0BAQEFAASCAUAw"

ALL_SECRETS = (
    WG_PRIVATE_KEY,
    WG_PRESHARED_KEY,
    PSK_PASSPHRASE,
    YAML_PSK,
    YAML_PASSWORD,
    PEM_BODY_1,
    PEM_BODY_2,
)

WG_CONF = f"""[Interface]
PrivateKey = {WG_PRIVATE_KEY}
ListenPort = 51820
Address = 10.0.0.1/24

[Peer]
PresharedKey = {WG_PRESHARED_KEY}
psk = {PSK_PASSPHRASE}
Endpoint = 10.0.0.2:51820
"""

WIFI_YAML = f"""wifi:
  home:
    ssid: HomeNet
    psk: {YAML_PSK}
  guest:
    - name: guest
      password: {YAML_PASSWORD}
"""

# No section header, so configparser bails and the parser degrades to text --
# this file exists for its `lines`, which is where a PEM block lives.
BUNDLE_CONF = f"""# TLS material
-----BEGIN PRIVATE KEY-----
{PEM_BODY_1}
{PEM_BODY_2}
-----END PRIVATE KEY-----
after = ok
"""


@pytest.fixture()
def snapshotted(tmp_path, monkeypatch):
    """Run `snapshot()` over two temp config files into temp output dirs."""
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "wg0.conf").write_text(WG_CONF, encoding="utf-8")
    (etc / "wifi.yaml").write_text(WIFI_YAML, encoding="utf-8")
    (etc / "bundle.conf").write_text(BUNDLE_CONF, encoding="utf-8")

    manifest = tmp_path / "manifest.yml"
    manifest.write_text(
        "include:\n"
        f"  - {etc}/*.conf\n"
        f"  - {etc}/*.yaml\n"
        "exclude: []\n",
        encoding="utf-8",
    )

    raw_dir = tmp_path / "out" / "raw"
    canon_dir = tmp_path / "out" / "canon"
    snap_dir = tmp_path / "out" / "snapshots"
    monkeypatch.setattr(snapshot_mod, "RAW_DIR", str(raw_dir))
    monkeypatch.setattr(snapshot_mod, "CANON_DIR", str(canon_dir))
    monkeypatch.setattr(snapshot_mod, "SNAP_DIR", str(snap_dir))

    summary = snapshot_mod.snapshot(str(manifest))
    assert [e for e in summary if "error" in e] == []

    by_name = {}
    for entry in summary:
        canon_path = canon_dir / f"{entry['hash']}.json"
        by_name[entry["path"].rsplit("/", 1)[-1]] = {
            "entry": entry,
            "text": canon_path.read_text(encoding="utf-8"),
            "canon": json.loads(canon_path.read_text(encoding="utf-8")),
            "source": etc / entry["path"].rsplit("/", 1)[-1],
        }
    return by_name


def test_canon_json_carries_no_plaintext_credential(snapshotted):
    """Not one secret survives anywhere in either canonical file."""
    for name, blob in snapshotted.items():
        for secret in ALL_SECRETS:
            assert secret not in blob["text"], f"{secret!r} leaked into {name}"


def test_canon_json_redacts_both_the_parsed_values_and_the_lines(snapshotted):
    """The two carriers are separate: `sections`/`tree` and `lines`.

    Redacting only one of them still writes the file's secrets to disk, so
    each is asserted on its own terms rather than through the whole-file
    substring check above.
    """
    conf = snapshotted["wg0.conf"]["canon"]
    assert WG_PRIVATE_KEY not in str(conf["sections"])
    assert PSK_PASSPHRASE not in str(conf["sections"])
    assert WG_PRIVATE_KEY not in str(conf["lines"])
    assert PSK_PASSPHRASE not in str(conf["lines"])

    tree = snapshotted["wifi.yaml"]["canon"]["tree"]
    assert tree["wifi"]["home"]["psk"] != YAML_PSK
    assert tree["wifi"]["guest"][0]["password"] != YAML_PASSWORD


def test_canon_json_keeps_the_shape_of_what_it_redacted(snapshotted):
    """Keys, nesting and line numbers survive; only values change.

    `drift.py` diffs `sections` key by key and `edge_extractor.py` cites
    `lines[*].n`, so a redaction that dropped entries or renumbered lines
    would break both while looking like it had worked.
    """
    conf = snapshotted["wg0.conf"]["canon"]
    assert set(conf["sections"]) == {"Interface", "Peer"}
    assert set(conf["sections"]["Interface"]) == {
        "privatekey",
        "listenport",
        "address",
    }
    assert set(conf["sections"]["Peer"]) == {"presharedkey", "psk", "endpoint"}
    # Non-credential values are untouched -- over-redaction here would destroy
    # the configuration the assistant exists to reason about.
    assert conf["sections"]["Interface"]["listenport"] == 51820
    assert conf["sections"]["Interface"]["address"] == "10.0.0.1/24"

    source_lines = WG_CONF.splitlines()
    assert len(conf["lines"]) == len(source_lines)
    assert [ln["n"] for ln in conf["lines"]] == list(
        range(1, len(source_lines) + 1)
    )
    # Section headers and key names are still on their original lines.
    assert conf["lines"][0]["text"] == "[Interface]"
    assert conf["lines"][5]["text"] == "[Peer]"
    assert conf["lines"][2]["text"] == "ListenPort = 51820"

    tree = snapshotted["wifi.yaml"]["canon"]["tree"]
    assert set(tree["wifi"]) == {"home", "guest"}
    assert set(tree["wifi"]["home"]) == {"ssid", "psk"}
    assert tree["wifi"]["home"]["ssid"] == "HomeNet"
    assert isinstance(tree["wifi"]["guest"], list)
    assert len(tree["wifi"]["guest"]) == 1
    assert set(tree["wifi"]["guest"][0]) == {"name", "password"}
    assert tree["wifi"]["guest"][0]["name"] == "guest"


@pytest.mark.parametrize(
    "name,source_text",
    [("wg0.conf", WG_CONF), ("wifi.yaml", WIFI_YAML)],
)
def test_canon_hash_is_still_the_hash_of_the_original_file(
    snapshotted, name, source_text
):
    """Redaction must not move the hash.

    Asserted against a sha256 computed here rather than against anything
    Halbert produces, so the check cannot drift along with the code: this is
    the pre-fix value by construction.
    """
    expected = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    assert snapshotted[name]["canon"]["hash"] == expected
    assert snapshotted[name]["entry"]["hash"] == expected
    # The parser is what computes it, and the parser reads the live file.
    assert parse_config(str(snapshotted[name]["source"]))["hash"] == expected


def test_canon_keeps_the_path_and_kind_it_is_looked_up_by(snapshotted):
    """`path` addresses the file for drift and edges; it is not a value."""
    conf = snapshotted["wg0.conf"]["canon"]
    assert conf["kind"] == "ini"
    assert conf["path"].endswith("/etc/wg0.conf")
    assert snapshotted["wifi.yaml"]["canon"]["kind"] == "yaml"


@pytest.mark.parametrize("name", ["wg0.conf", "wifi.yaml"])
def test_raw_sink_and_canon_lines_agree(snapshotted, tmp_path, name):
    """Canon's `lines` carry what the raw sink carries.

    The two sinks are written from the same source text one line apart. If
    they can disagree, one of them is the weaker guarantee and the module has
    no single answer to "what does redaction leave behind".

    `bundle.conf` is excluded and gets its own test: it is the one deliberate
    divergence, because the raw sink may collapse a PEM block's lines and a
    line-numbered sink may not.
    """
    raw_dir = tmp_path / "out" / "raw"
    blob = snapshotted[name]
    raw = (raw_dir / f"{blob['entry']['hash']}.txt").read_text(encoding="utf-8")
    from_canon = "\n".join(ln["text"] for ln in blob["canon"]["lines"])
    assert from_canon == raw.rstrip("\n")


def test_pem_block_is_removed_without_renumbering_the_file(snapshotted):
    """A PEM block loses its body and keeps its height.

    `PEM_RE` is the only pattern in the redaction module whose match spans
    lines, and `redact_text` replaces the whole block with one marker. That is
    right for the raw text sink and wrong here: it would move every line below
    the block up by the block's height, and `edge_extractor.py` cites
    `lines[*].n`. So canon keeps the block's newlines and empties its
    interior.
    """
    canon = snapshotted["bundle.conf"]["canon"]
    texts = [ln["text"] for ln in canon["lines"]]
    assert len(texts) == len(BUNDLE_CONF.splitlines())
    assert [ln["n"] for ln in canon["lines"]] == list(range(1, len(texts) + 1))
    assert texts[0] == "# TLS material"
    assert texts[1] == "<pem_block>"
    assert texts[2:5] == ["", "", ""]
    # The line below the block still sits on its original number.
    assert texts[5] == "after = ok"
