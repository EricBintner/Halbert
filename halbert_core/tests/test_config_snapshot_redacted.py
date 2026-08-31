# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""`snapshot()`'s two sinks have two different redaction contracts (REV-01 F1).

The canon DB under `data/config/canon/` is RAW BY DESIGN — the user-owned,
localhost-only private index that tier routing, `describe_secret`, the
correlation index, `drift.py` and `edge_extractor.py` all read. The Tier-2
feature set is built on real values: a redacted canon fed `describe_secret`
the `<secret>` placeholder and it reported the placeholder's length and
entropy for every credential on the machine, and the correlation index
collapsed every secret onto one hash (false correlations for rotation
advice). What protects the raw canon is the egress boundaries — tier
routing answers `local_only` with metadata only, and the MCP dispatch choke
point redacts every `tools/call` result — both pinned by
`test_tier2_guarantee.py` and `test_security_roles.py`.

The raw-text sink under `data/config/raw/` is the opposite: ALWAYS redacted,
whatever the canon's state. It is a grep-able debugging mirror, not an input
to any secret-aware feature.

`redact=True` remains available for callers that want a redacted canon; its
line-count and shape guarantees (the PEM-block test) stay pinned here.

Neither contract may disturb `hash`. Drift detection compares hashes to
decide whether a file changed at all, so a hash computed over redacted
content would report every credential-bearing file as modified on the first
run after the change and then never again -- silently, because the
comparison would still be self-consistent.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from halbert_core.config import snapshot as snapshot_mod
from halbert_core.config.parser import parse as parse_config
from halbert_core.ingestion.redaction import redact_lines, redact_parsed

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


def test_a_boolean_under_a_secret_key_survives():
    """A bool cannot be a credential, and it is often the setting that matters.

    It is drawn from a universally-known two-element set, so it carries no
    bits that could identify anything -- the same argument `_is_netmask`
    makes for subnet masks. Meanwhile the keys it sits under are exactly the
    ones a sysadmin assistant exists to reason about: `PasswordAuthentication`
    matches on `password`, and every launchd `MachServices.<name>` entry whose
    service name happens to contain `key` or `token` is a bare `<true/>`.

    The plist text pass already spares them -- `_redact_plist_value` returns
    None for a self-closing `<true/>` -- so redacting them here would make
    `tree` disagree with `lines` inside the same canon file. Measured across
    461 launchd plists on this host: 14 leaves, all of them booleans, were
    the only place the two passes disagreed.

    An integer is not exempt. A numeric PIN is a real credential, and
    `_normalize_scalar` turns one into an int.
    """
    out = redact_parsed(
        {
            "PasswordAuthentication": False,
            "MachServices": {"com.apple.applekeystored": True},
            "PrivateKey": "abc123=",
            "pin": 1234,
            "password": None,
        }
    )
    assert out["PasswordAuthentication"] is False
    assert out["MachServices"]["com.apple.applekeystored"] is True
    assert out["PrivateKey"] == "<secret>"
    assert out["pin"] == "<secret>"
    assert out["password"] is None


def test_redact_lines_round_trips_a_file_with_no_lines():
    """`"\\n".join([])` is `""` and `"".split("\\n")` is `[""]`.

    That asymmetry is the one place the join-redact-split round trip does not
    preserve its own input length, and it turns "no lines" into "one line".
    """
    assert redact_lines([]) == []
    assert redact_lines([""]) == [""]


def test_an_empty_config_file_still_snapshots(tmp_path, monkeypatch):
    """An empty config file is ordinary and must not become an error.

    An empty drop-in is how a systemd unit gets masked or a default
    overridden, so its existence is a fact about the host. Found by running
    the redaction over every readable file under /etc on this machine: seven
    were empty, and every one of them tripped `redact_lines`' line-count
    guard and was recorded as a failed file instead of a snapshotted one.
    """
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "masked.conf").write_text("", encoding="utf-8")
    manifest = tmp_path / "manifest.yml"
    manifest.write_text(
        f"include:\n  - {etc}/*.conf\nexclude: []\n", encoding="utf-8"
    )
    monkeypatch.setattr(snapshot_mod, "RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setattr(snapshot_mod, "CANON_DIR", str(tmp_path / "canon"))
    monkeypatch.setattr(snapshot_mod, "SNAP_DIR", str(tmp_path / "snap"))

    summary = snapshot_mod.snapshot(str(manifest))

    assert [e for e in summary if "error" in e] == []
    assert len(summary) == 1
    canon = json.loads(
        (tmp_path / "canon" / f"{summary[0]['hash']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert canon["lines"] == []
    assert canon["hash"] == hashlib.sha256(b"").hexdigest()


def test_raw_text_sink_carries_no_plaintext_credential(snapshotted, tmp_path):
    """The grep-able debugging mirror is ALWAYS redacted, whatever the canon."""
    raw_dir = tmp_path / "out" / "raw"
    for name, blob in snapshotted.items():
        raw = (raw_dir / f"{blob['entry']['hash']}.txt").read_text(encoding="utf-8")
        for secret in ALL_SECRETS:
            assert secret not in raw, f"{secret!r} survived in the raw sink of {name}"


def test_canon_is_raw_by_design(snapshotted):
    """The private index carries the real values the Tier-2 features need.

    Both carriers are asserted on their own terms: `sections`/`tree` (parsed
    values) and `lines` (the full-text mirror inside the canon record).
    """
    conf = snapshotted["wg0.conf"]["canon"]
    assert WG_PRIVATE_KEY in str(conf["sections"])
    assert PSK_PASSPHRASE in str(conf["sections"])
    assert WG_PRIVATE_KEY in str(conf["lines"])
    assert PSK_PASSPHRASE in str(conf["lines"])

    tree = snapshotted["wifi.yaml"]["canon"]["tree"]
    assert tree["wifi"]["home"]["psk"] == YAML_PSK
    assert tree["wifi"]["guest"][0]["password"] == YAML_PASSWORD


def test_describe_secret_receives_real_values(snapshotted, monkeypatch):
    """The Tier-2 feature the raw canon exists for: real metadata, not the
    placeholder's. With the old redacted canon this reported length 8,
    entropy 2.75 — the properties of the string `<secret>` — for every
    credential on the machine.
    """
    from halbert_core.config import queries as queries_mod
    from halbert_core.config.queries import get_config_value

    monkeypatch.setattr(
        queries_mod, "CANON_DIR", snapshot_mod.CANON_DIR, raising=True
    )
    monkeypatch.setattr(
        queries_mod, "SNAP_DIR", snapshot_mod.SNAP_DIR, raising=True
    )
    path = str(snapshotted["wg0.conf"]["source"])
    result = get_config_value(path, "PrivateKey")
    assert "description" in result
    description = result["description"]
    assert description["length"] == len(WG_PRIVATE_KEY)
    assert description["entropy_bits"] != 2.75  # the placeholder's entropy


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
def test_raw_sink_is_canon_lines_through_redaction(snapshotted, tmp_path, name):
    """The raw sink is what the canon's `lines` look like post-`redact_text`.

    The two sinks are written from the same source text one line apart; the
    canon keeps it verbatim and the raw sink runs it through `redact_text`.
    Asserting the transform (rather than equality, as the redacted-canon era
    did) keeps the pair honest without coupling the two contracts.
    """
    from halbert_core.ingestion.redaction import redact_text

    raw_dir = tmp_path / "out" / "raw"
    blob = snapshotted[name]
    raw = (raw_dir / f"{blob['entry']['hash']}.txt").read_text(encoding="utf-8")
    from_canon = "\n".join(ln["text"] for ln in blob["canon"]["lines"])
    assert redact_text(from_canon) == raw.rstrip("\n")


def test_pem_block_is_removed_without_renumbering_the_file(snapshotted, tmp_path, monkeypatch):
    """A PEM block loses its body and keeps its height — the redact=True canon.

    `PEM_RE` is the only pattern in the redaction module whose match spans
    lines, and `redact_text` replaces the whole block with one marker. That is
    right for the raw text sink and wrong for a line-numbered canon: it would
    move every line below the block up by the block's height, and
    `edge_extractor.py` cites `lines[*].n`. So the redacted canon keeps the
    block's newlines and empties its interior. The raw-by-default canon keeps
    the block verbatim.
    """
    # Re-run the snapshot with an explicitly redacted canon into fresh dirs.
    etc = snapshotted["wg0.conf"]["source"].parent
    manifest = tmp_path / "manifest-redacted.yml"
    manifest.write_text(
        f"include:\n  - {etc}/*.conf\nexclude: []\n", encoding="utf-8"
    )
    canon_dir = tmp_path / "out-redacted" / "canon"
    monkeypatch.setattr(snapshot_mod, "CANON_DIR", str(canon_dir))
    monkeypatch.setattr(snapshot_mod, "RAW_DIR", str(tmp_path / "out-redacted" / "raw"))
    monkeypatch.setattr(snapshot_mod, "SNAP_DIR", str(tmp_path / "out-redacted" / "snap"))
    summary = snapshot_mod.snapshot(str(manifest), redact=True)
    entry = next(e for e in summary if e["path"].endswith("bundle.conf"))
    canon = json.loads((canon_dir / f"{entry['hash']}.json").read_text(encoding="utf-8"))

    texts = [ln["text"] for ln in canon["lines"]]
    assert len(texts) == len(BUNDLE_CONF.splitlines())
    assert [ln["n"] for ln in canon["lines"]] == list(range(1, len(texts) + 1))
    assert texts[0] == "# TLS material"
    assert texts[1] == "<pem_block>"
    assert texts[2:5] == ["", "", ""]
    # The line below the block still sits on its original number.
    assert texts[5] == "after = ok"
