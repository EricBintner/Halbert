# Role-Scoped Config Harvesting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship three role-scoped SourcePrep scopes (`network_admin`, `service_admin`, `storage_admin`) that give the agent narrow, per-subsystem config context — after first closing a live secret-leak in the staging path.

**Architecture:** Reuse the existing Phase 1/3 config pipeline (`manifest.py` → `snapshot.py` → redaction → `drift.py`, watched by `watcher.py`) unchanged, pointing it at narrow per-role manifests instead of one blanket `/etc/**/*.conf` glob. Rewire host staging to consume `snapshot.py`'s *redacted* output rather than copying live `/etc` paths verbatim. Register each role's staged tree as a SourcePrep scope with `scope_mode="hard"`.

**Tech Stack:** Python 3.10+, pytest, PyYAML, `watchdog`, stdlib `configparser`/`plistlib`, SourcePrep HTTP API.

**Design doc:** `.handoff/ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md`

---

## Working conventions

**Run tests from the `halbert_core/` directory, never the repo root.** Under
pytest from `/Volumes/4TB-BAD/Halbert`, `import halbert_core` resolves as a
*namespace package* pointing at the outer project directory and package-level
imports fail. All commands below use `cd /Volumes/4TB-BAD/Halbert/halbert_core`.

**Commit with explicit pathspecs** (`git commit -m "..." -- <paths>`). Other
sessions edit this working tree concurrently; a bare `git commit -a` will sweep
their staged work into your commit.

**Do not run SourcePrep builds or embedding scripts** without checking first:
`ps aux | grep -E 'staged_knowledge_embed|prep.cli serve'`. A concurrent build
can be clobbered, and the daemon's `building` flag does not reflect
out-of-process scripts.

---

## File structure

**Phase A — close the leak (Tasks 1–6)**

| File | Responsibility |
|---|---|
| `halbert_core/halbert_core/ingestion/redaction.py` | Modify: widen `TOKEN_RE`; add macOS identity redaction |
| `halbert_core/halbert_core/config/parser.py` | Modify: catch configparser errors; add `.plist` branch |
| `halbert_core/halbert_core/tools/register_host_project.py` | Modify: `_stage_config_files` reads redacted snapshot output |
| `halbert_core/tests/test_redaction_secrets.py` | Create: secret-pattern unit tests |
| `halbert_core/tests/test_config_parser_robustness.py` | Create: parser fallback + plist unit tests |
| `halbert_core/tests/test_host_staging_redacted.py` | Create: snapshot→redact→stage integration test |

**Phase B — role scopes (Tasks 7–12)**

| File | Responsibility |
|---|---|
| `config/scopes/network.yml` | Create: network_admin include/exclude globs |
| `config/scopes/service.yml` | Create: service_admin include/exclude globs |
| `config/scopes/storage.yml` | Create: storage_admin include/exclude globs |
| `halbert_core/halbert_core/config/manifest.py` | Modify: expand `~` in patterns |
| `halbert_core/halbert_core/config/roles.py` | Create: role registry (manifest paths, aliases, platform gating) |
| `halbert_core/halbert_core/integrations/sourceprep_template.yml` | Modify: add three role scopes |
| `halbert_core/tests/test_config_roles.py` | Create: role registry + manifest tests |

---

## Phase A — Close the secret leak

### Task 1: Widen the secret redaction regex

`TOKEN_RE` currently misses NetworkManager WiFi passwords (`psk=`, not a
keyword) and WireGuard private keys (`PrivateKey = ` — the regex allows no
whitespace around the separator).

**Files:**
- Modify: `halbert_core/halbert_core/ingestion/redaction.py:8`
- Test: `halbert_core/tests/test_redaction_secrets.py`

- [ ] **Step 1: Write the failing test**

Create `halbert_core/tests/test_redaction_secrets.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Secret-redaction coverage for config formats staged into SourcePrep.

Every pattern here corresponds to a real file the role manifests harvest.
A regression in any of these ships plaintext credentials into a searchable
knowledge scope.
"""
from __future__ import annotations

from halbert_core.ingestion.redaction import redact_text


def test_networkmanager_psk_is_redacted():
    """NetworkManager stores WiFi passwords as a bare psk= line."""
    nm = "[wifi-security]\nkey-mgmt=wpa-psk\npsk=hunter2supersecret\n"
    out = redact_text(nm)
    assert "hunter2supersecret" not in out
    assert "<secret>" in out


def test_wireguard_private_key_with_spaces_is_redacted():
    """Standard WireGuard formatting puts spaces around the separator."""
    wg = "[Interface]\nPrivateKey = aGVsbG93b3JsZGJhc2U2NHNlY3JldA=\nListenPort = 51820\n"
    out = redact_text(wg)
    assert "aGVsbG93b3JsZGJhc2U2NHNlY3JldA=" not in out
    assert "<secret>" in out


def test_wireguard_preshared_key_is_redacted():
    wg = "[Peer]\nPresharedKey = c2hhcmVkc2VjcmV0dmFsdWU=\n"
    out = redact_text(wg)
    assert "c2hhcmVkc2VjcmV0dmFsdWU=" not in out


def test_existing_token_patterns_still_redacted():
    """Guard against the widened regex breaking what already worked."""
    assert "abc123" not in redact_text("api_key=abc123")
    assert "s3cret" not in redact_text("password:s3cret")


def test_listen_port_is_not_redacted():
    """The widened regex must not swallow ordinary non-secret directives."""
    out = redact_text("[Interface]\nListenPort = 51820\n")
    assert "51820" in out
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_redaction_secrets.py -v
```

Expected: `test_networkmanager_psk_is_redacted`,
`test_wireguard_private_key_with_spaces_is_redacted`, and
`test_wireguard_preshared_key_is_redacted` FAIL (the secret string is still
present in the output). The other two PASS.

- [ ] **Step 3: Widen the regex**

In `halbert_core/halbert_core/ingestion/redaction.py`, replace line 8:

```python
TOKEN_RE = re.compile(r"(?i)(api|secret|token|key|password)[=:]\S+")
```

with:

```python
# Keyword list covers config formats staged into SourcePrep scopes:
# `psk` (NetworkManager WiFi), `privatekey`/`presharedkey` (WireGuard), plus
# the original generic terms. `\s*` around the separator is required —
# WireGuard's standard formatting is `PrivateKey = <value>`, which the
# original no-whitespace pattern silently missed.
TOKEN_RE = re.compile(
    r"(?i)(api|secret|token|key|password|psk|privatekey|presharedkey)\s*[=:]\s*\S+"
)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_redaction_secrets.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run the full suite to check for regressions**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/ -q 2>&1 | tail -20
```

Expected: no *new* failures. Pre-existing unrelated failures may be present
(`test_concept_seeder_swarm`, `test_pipeline_journal`, `test_recovery_manager`
have failed on main before this work); note the count before and after if
unsure.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "fix(redaction): catch psk and whitespace-separated key directives

TOKEN_RE missed NetworkManager psk= (WiFi passwords) and WireGuard
PrivateKey = (spaces around the separator), both of which are staged
into searchable SourcePrep scopes by the host config pipeline." \
  -- halbert_core/halbert_core/ingestion/redaction.py \
     halbert_core/tests/test_redaction_secrets.py
```

---

### Task 2: Add macOS identity redaction

macOS config files leak identity that the Linux-oriented rules miss.
`com.apple.smb.server.plist` contains the owner's real name and an LKDC
Kerberos realm hash.

**Files:**
- Modify: `halbert_core/halbert_core/ingestion/redaction.py`
- Test: `halbert_core/tests/test_redaction_secrets.py`

- [ ] **Step 1: Write the failing test**

Append to `halbert_core/tests/test_redaction_secrets.py`:

```python
def test_lkdc_realm_hash_is_redacted():
    """com.apple.smb.server.plist carries an LKDC Kerberos realm hash."""
    smb = (
        "<key>LocalKerberosRealm</key>\n"
        "<string>LKDC:SHA1.9F2C4E1A7B3D5F8E0C6A2B4D9E1F3A5C7B8D0E2F</string>\n"
    )
    out = redact_text(smb)
    assert "9F2C4E1A7B3D5F8E0C6A2B4D9E1F3A5C7B8D0E2F" not in out
    assert "<lkdc_realm>" in out


def test_plain_text_without_lkdc_is_untouched():
    text = "<key>NetBIOSName</key>\n<string>WORKSTATION</string>\n"
    assert redact_text(text) == "<key>NetBIOSName</key>\n<string>WORKSTATION</string>\n"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_redaction_secrets.py::test_lkdc_realm_hash_is_redacted -v
```

Expected: FAIL — the realm hash is still present.

- [ ] **Step 3: Add the pattern**

In `halbert_core/halbert_core/ingestion/redaction.py`, add after the `PEM_RE`
definition (line 17):

```python
# macOS: local Kerberos realm identifiers in com.apple.smb.server.plist and
# related SystemConfiguration plists. Format is LKDC:SHA1.<40 hex chars>.
LKDC_RE = re.compile(r"LKDC:SHA1\.[0-9A-Fa-f]{40}")
```

Then in `redact_text`, add before the `return` (after the `PEM_RE` line):

```python
    text = LKDC_RE.sub("<lkdc_realm>", text)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_redaction_secrets.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "fix(redaction): redact macOS LKDC Kerberos realm hashes

com.apple.smb.server.plist is staged by the macOS host manifest and
carries an LKDC:SHA1.<hash> realm identifier." \
  -- halbert_core/halbert_core/ingestion/redaction.py \
     halbert_core/tests/test_redaction_secrets.py
```

---

### Task 3: Stop the parser dropping files on error

`_parse_ini_like` uses `configparser` with the default `strict=True`. A
repeated key or a missing `[Section]` header raises, and because `snapshot.py`
wraps parsing *and* raw-text writing in one `try`, the whole file is dropped —
never written, never staged. Systemd drop-ins and NetworkManager dispatcher
scripts hit this routinely.

**Files:**
- Modify: `halbert_core/halbert_core/config/parser.py:49-65`
- Test: `halbert_core/tests/test_config_parser_robustness.py`

- [ ] **Step 1: Write the failing test**

Create `halbert_core/tests/test_config_parser_robustness.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Parser must degrade, never drop.

snapshot.py wraps parse + raw-text write in one try block, so any exception
escaping parse() means the file never reaches the knowledge base at all.
Config formats the role manifests harvest routinely violate strict ini rules.
"""
from __future__ import annotations

from halbert_core.config.parser import parse


def test_duplicate_keys_fall_back_to_text(tmp_path):
    """systemd drop-ins legitimately repeat directives."""
    p = tmp_path / "override.conf"
    p.write_text(
        "[Service]\n"
        "Environment=FOO=1\n"
        "Environment=BAR=2\n"
        "ExecStartPre=/bin/true\n"
        "ExecStartPre=/bin/echo hi\n"
    )
    result = parse(str(p))
    assert result["kind"] == "text"
    assert result["hash"]
    assert any("BAR=2" in line["text"] for line in result["lines"])


def test_missing_section_header_falls_back_to_text(tmp_path):
    """NetworkManager dispatcher scripts and bare KEY=value .conf files."""
    p = tmp_path / "dispatcher.conf"
    p.write_text("INTERFACE=eth0\nSTATUS=up\n")
    result = parse(str(p))
    assert result["kind"] == "text"
    assert any("INTERFACE=eth0" in line["text"] for line in result["lines"])


def test_valid_ini_still_parses_as_ini(tmp_path):
    """The fallback must not swallow files that parse cleanly."""
    p = tmp_path / "good.conf"
    p.write_text("[Unit]\nDescription=Test unit\n")
    result = parse(str(p))
    assert result["kind"] == "ini"
    assert result["sections"]["Unit"]["description"] == "Test unit"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_parser_robustness.py -v
```

Expected: `test_duplicate_keys_fall_back_to_text` FAILS with
`configparser.DuplicateOptionError`, `test_missing_section_header_falls_back_to_text`
FAILS with `configparser.MissingSectionHeaderError`. The third PASSES.

- [ ] **Step 3: Catch the errors and fall back**

In `halbert_core/halbert_core/config/parser.py`, replace `_parse_ini_like`
(lines 49–65) with:

```python
def _parse_ini_like(path: str, text: str, h: str) -> Dict[str, Any]:
    parser = configparser.ConfigParser(interpolation=None)
    # Allow ; and # comments
    try:
        parser.read_string(text)
    except configparser.Error:
        # Real config routinely violates strict ini rules: systemd drop-ins
        # repeat directives (Environment=, ExecStartPre=), and dispatcher
        # scripts / bare KEY=value files have no [Section] header. Degrading
        # to text keeps the content searchable; raising would drop the file
        # entirely, because snapshot.py wraps parse + raw-write in one try.
        return _parse_text(path, text, h)
    sections: Dict[str, Dict[str, Any]] = {}
    for section in parser.sections():
        items: Dict[str, Any] = {}
        for k, v in parser.items(section):
            items[k] = _normalize_scalar(v)
        sections[section] = items
    return {
        "path": path,
        "hash": h,
        "kind": "ini",
        "sections": sections,
        "lines": _lines(text),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_parser_robustness.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "fix(config): degrade to text instead of dropping unparseable ini

configparser's strict mode rejects repeated keys (systemd drop-ins) and
missing section headers (dispatcher scripts, bare KEY=value .conf).
snapshot.py wraps parse and raw-text write in one try block, so the
exception meant the file never reached the knowledge base at all." \
  -- halbert_core/halbert_core/config/parser.py \
     halbert_core/tests/test_config_parser_robustness.py
```

---

### Task 4: Add plist support to the parser

`parse()` has no `.plist` branch, so every plist flows through `_read_text`,
which opens with `errors="replace"`. Binary plists are corrupted into U+FFFD
soup and then *hashed in that corrupted form* — so drift detection compares
corruption against corruption. Plists are macOS's primary harvestable format,
which makes this blocking for `service_admin`.

**Files:**
- Modify: `halbert_core/halbert_core/config/parser.py`
- Test: `halbert_core/tests/test_config_parser_robustness.py`

- [ ] **Step 1: Write the failing test**

Append to `halbert_core/tests/test_config_parser_robustness.py`:

```python
import plistlib


def test_binary_plist_is_parsed_not_mangled(tmp_path):
    """Binary plists must not flow through the errors='replace' text path."""
    p = tmp_path / "com.example.daemon.plist"
    payload = {"Label": "com.example.daemon", "RunAtLoad": True, "KeepAlive": False}
    p.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_BINARY))

    result = parse(str(p))
    assert result["kind"] == "plist"
    assert result["tree"]["Label"] == "com.example.daemon"
    assert result["tree"]["RunAtLoad"] is True
    assert "�" not in "".join(line["text"] for line in result["lines"])


def test_xml_plist_is_parsed(tmp_path):
    """LaunchAgents/LaunchDaemons are XML; they must parse the same way."""
    p = tmp_path / "com.example.agent.plist"
    payload = {"Label": "com.example.agent", "ProgramArguments": ["/bin/echo", "hi"]}
    p.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML))

    result = parse(str(p))
    assert result["kind"] == "plist"
    assert result["tree"]["ProgramArguments"] == ["/bin/echo", "hi"]


def test_binary_and_xml_plist_hash_the_same_content_differently(tmp_path):
    """Hash must be computed over parsed content, so it is stable and real.

    Two plists with different content must hash differently — proving the
    hash is not being taken over identical U+FFFD replacement soup.
    """
    a = tmp_path / "a.plist"
    b = tmp_path / "b.plist"
    a.write_bytes(plistlib.dumps({"Label": "alpha"}, fmt=plistlib.FMT_BINARY))
    b.write_bytes(plistlib.dumps({"Label": "beta"}, fmt=plistlib.FMT_BINARY))
    assert parse(str(a))["hash"] != parse(str(b))["hash"]


def test_unreadable_plist_falls_back_to_text(tmp_path):
    """A corrupt or non-plist file named .plist must not raise."""
    p = tmp_path / "broken.plist"
    p.write_bytes(b"this is not a plist at all")
    result = parse(str(p))
    assert result["kind"] == "text"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_parser_robustness.py -v -k plist
```

Expected: `test_binary_plist_is_parsed_not_mangled`,
`test_xml_plist_is_parsed`, and
`test_binary_and_xml_plist_hash_the_same_content_differently` FAIL (`kind` is
`"text"`, no `tree` key). `test_unreadable_plist_falls_back_to_text` passes
incidentally.

- [ ] **Step 3: Add the plist branch**

In `halbert_core/halbert_core/config/parser.py`, add `plistlib` to the imports
at the top (after `import os`):

```python
import plistlib
```

Then replace `parse()` (lines 36–46) with:

```python
def parse(path: str) -> Dict[str, Any]:
    lower = path.lower()
    # Plists are checked before the text read: binary plists are not UTF-8,
    # and _read_text's errors="replace" would corrupt them into U+FFFD soup
    # that then gets hashed — making drift detection compare corruption to
    # corruption. plistlib handles both binary and XML natively.
    if lower.endswith(".plist"):
        parsed = _parse_plist(path)
        if parsed is not None:
            return parsed
    text = _read_text(path)
    h = _hash_bytes(text.encode("utf-8", errors="replace"))
    if lower.endswith((".ini", ".conf", ".service", ".timer")):
        return _parse_ini_like(path, text, h)
    if lower.endswith((".yaml", ".yml")) and yaml is not None:
        return _parse_yaml(path, text, h)
    if lower.endswith(".json"):
        return _parse_json(path, text, h)
    return _parse_text(path, text, h)
```

Then add `_parse_plist` after `_parse_json` (after line 93):

```python
def _parse_plist(path: str) -> Dict[str, Any] | None:
    """Parse a binary or XML plist. Returns None if it isn't a valid plist,
    so the caller falls through to the generic text path."""
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
    except Exception:
        return None
    # Re-serialize to XML text so the content is greppable, citable by line,
    # and hashable over real content rather than raw binary.
    try:
        text = plistlib.dumps(data, fmt=plistlib.FMT_XML).decode("utf-8")
    except Exception:
        return None
    return {
        "path": path,
        "hash": _hash_bytes(text.encode("utf-8")),
        "kind": "plist",
        "tree": data,
        "lines": _lines(text),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_parser_robustness.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Verify against a real macOS plist**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -c "
from halbert_core.config.parser import parse
r = parse('/Library/Preferences/SystemConfiguration/preferences.plist')
print('kind:', r['kind'])
print('hash:', r['hash'][:16])
print('top-level keys:', sorted(r['tree'].keys())[:5])
"
```

Expected: `kind: plist`, a real hash, and real key names such as
`CurrentSet`, `NetworkServices`, `Sets`, `System`. If this file does not exist
(non-macOS host), skip this step.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "feat(config): parse plists with plistlib instead of mangling them

parse() had no .plist branch, so every plist went through _read_text's
errors='replace' path. Binary plists became U+FFFD soup and were hashed
in that corrupted form, so drift detection compared corruption to
corruption. Plists are the primary harvestable format on macOS." \
  -- halbert_core/halbert_core/config/parser.py \
     halbert_core/tests/test_config_parser_robustness.py
```

---

### Task 5: Rewire host staging onto redacted snapshot output

This is the actual leak fix. `_stage_config_files()` copies live `/etc` paths
verbatim with `shutil.copy2()` into the SourcePrep-visible tree. Redaction
never runs on that path — `snapshot.py`'s redacted output is orphaned.

**Files:**
- Modify: `halbert_core/halbert_core/tools/register_host_project.py:104-150`
- Test: `halbert_core/tests/test_host_staging_redacted.py`

- [ ] **Step 1: Write the failing test**

Create `halbert_core/tests/test_host_staging_redacted.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Staged host config must be redacted before it becomes searchable.

_stage_config_files writes into the SourcePrep-visible tree. Anything that
lands there is indexed and returned by scoped queries, so a secret reaching
this directory is a secret in the knowledge base.
"""
from __future__ import annotations

from pathlib import Path

from halbert_core.tools.register_host_project import _stage_config_files


def test_staged_nmconnection_has_psk_redacted(tmp_path):
    src_dir = tmp_path / "etc" / "NetworkManager" / "system-connections"
    src_dir.mkdir(parents=True)
    conn = src_dir / "HomeWiFi.nmconnection"
    conn.write_text(
        "[connection]\nid=HomeWiFi\ntype=wifi\n\n"
        "[wifi-security]\nkey-mgmt=wpa-psk\npsk=hunter2supersecret\n"
    )

    staging = tmp_path / "staged"
    count = _stage_config_files([str(conn)], staging)

    assert count == 1
    staged_files = list(staging.rglob("HomeWiFi.nmconnection"))
    assert len(staged_files) == 1
    content = staged_files[0].read_text()
    assert "hunter2supersecret" not in content
    assert "<secret>" in content


def test_staged_wireguard_key_is_redacted(tmp_path):
    src = tmp_path / "etc" / "wireguard"
    src.mkdir(parents=True)
    wg = src / "wg0.conf"
    wg.write_text(
        "[Interface]\nPrivateKey = aGVsbG93b3JsZGJhc2U2NHNlY3JldA=\n"
        "Address = 10.0.0.1/24\nListenPort = 51820\n"
    )

    staging = tmp_path / "staged"
    _stage_config_files([str(wg)], staging)

    staged = list(staging.rglob("wg0.conf"))[0].read_text()
    assert "aGVsbG93b3JsZGJhc2U2NHNlY3JldA=" not in staged
    assert "51820" in staged  # non-secret content survives


def test_staged_directory_tree_is_redacted(tmp_path):
    """Directory staging walks recursively; every file must be redacted."""
    src = tmp_path / "etc" / "NetworkManager" / "system-connections"
    src.mkdir(parents=True)
    (src / "a.nmconnection").write_text("[wifi-security]\npsk=secretA\n")
    (src / "b.nmconnection").write_text("[wifi-security]\npsk=secretB\n")

    staging = tmp_path / "staged"
    count = _stage_config_files([str(src)], staging)

    assert count == 2
    all_text = "".join(p.read_text() for p in staging.rglob("*.nmconnection"))
    assert "secretA" not in all_text
    assert "secretB" not in all_text


def test_binary_plist_is_staged_as_readable_xml(tmp_path):
    """Binary plists must be converted, not copied as unreadable bytes."""
    import plistlib

    src = tmp_path / "Library" / "LaunchDaemons"
    src.mkdir(parents=True)
    p = src / "com.example.daemon.plist"
    p.write_bytes(
        plistlib.dumps({"Label": "com.example.daemon"}, fmt=plistlib.FMT_BINARY)
    )

    staging = tmp_path / "staged"
    _stage_config_files([str(p)], staging)

    staged = list(staging.rglob("com.example.daemon.plist"))[0].read_text()
    assert "com.example.daemon" in staged
    assert "�" not in staged


def test_missing_source_is_skipped_not_fatal(tmp_path):
    staging = tmp_path / "staged"
    assert _stage_config_files([str(tmp_path / "nope.conf")], staging) == 0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_host_staging_redacted.py -v
```

Expected: the four redaction/plist tests FAIL (secrets present verbatim,
plist staged as raw binary). `test_missing_source_is_skipped_not_fatal` PASSES.

- [ ] **Step 3: Rewrite `_stage_config_files` to redact**

In `halbert_core/halbert_core/tools/register_host_project.py`, add these
imports near the existing ones (after `from ..utils.paths import data_subdir`):

```python
from ..config.parser import parse as parse_config
from ..ingestion.redaction import redact_text
```

Then replace `_stage_config_files` (lines 104–150) entirely with:

```python
def _stage_one_file(src_file: Path, dest_file: Path) -> bool:
    """Stage a single config file through the redaction pipeline.

    Never a raw copy: anything landing under the staging root is indexed by
    SourcePrep and returned by scoped queries, so unredacted content here is
    unredacted content in the knowledge base. Binary formats (plists) are
    normalized to text by the parser before redaction so they are greppable
    and so redaction rules can actually match.

    Returns True if the file was staged.
    """
    try:
        canon = parse_config(str(src_file))
    except Exception as e:
        logger.debug(f"Skip {src_file} (parse failed): {e}")
        return False

    # `lines` is the canonical text form for every kind the parser emits,
    # including plists re-serialized to XML.
    text = "\n".join(line["text"] for line in canon.get("lines", []))
    if not text:
        return False

    try:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(redact_text(text), encoding="utf-8")
    except (PermissionError, OSError) as e:
        logger.warning(f"Cannot write staged copy {dest_file}: {e}")
        return False
    return True


def _stage_config_files(paths: List[str], staging_root: Path) -> int:
    """Stage config files/dirs into the staging directory, redacted.

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
                if _stage_one_file(src_path, dest):
                    count += 1
            elif src_path.is_dir():
                for root, dirs, files in os.walk(src_path):
                    rel = Path(root).relative_to(src_path)
                    dest_dir = dest / rel
                    for f in files:
                        if _stage_one_file(Path(root) / f, dest_dir / f):
                            count += 1
        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot stage {src_path}: {e}")

    return count
```

Note `shutil` may now be unused in this module — check with
`grep -n "shutil" halbert_core/halbert_core/tools/register_host_project.py`
and remove the import only if there are no remaining uses.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_host_staging_redacted.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run the full suite**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/ -q 2>&1 | tail -20
```

Expected: no new failures. `test_sourceprep_setup.py` in particular must still
pass — it exercises `apply()`'s call ordering, which reaches `_stage_host_tree`.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "fix(staging): redact host config before it reaches SourcePrep

_stage_config_files copied live /etc paths verbatim with shutil.copy2
into the SourcePrep-visible tree, with no redaction on that path at all —
only filename excludes for shadow/ssl. snapshot.py's redacted output was
orphaned, read by nothing. Staging now runs every file through the parser
(normalizing plists to text) and redact_text before writing." \
  -- halbert_core/halbert_core/tools/register_host_project.py \
     halbert_core/tests/test_host_staging_redacted.py
```

---

### Task 6: Verify the leak is closed on the real host

Automated tests use fixtures. This step confirms the fix against the actual
machine before anything ships.

**Files:** none (verification only)

- [ ] **Step 1: Check no SourcePrep build is running**

```bash
ps aux | grep -E 'staged_knowledge_embed|prep.cli serve' | grep -v grep
```

If a build is running, **stop here** and wait — do not proceed. A concurrent
run can clobber staged output.

- [ ] **Step 2: Stage the real host config to a scratch directory**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -c "
from pathlib import Path
from halbert_core.tools.register_host_project import _os_config_paths, _stage_config_files
out = Path('/tmp/halbert-stage-verify')
n = _stage_config_files(_os_config_paths(), out)
print(f'staged {n} files to {out}')
"
```

Expected: a non-zero file count.

- [ ] **Step 3: Grep the staged output for secret patterns**

```bash
grep -rEin 'psk[[:space:]]*=|privatekey[[:space:]]*=|presharedkey[[:space:]]*=' \
  /tmp/halbert-stage-verify/ | grep -v '<secret>' || echo "CLEAN: no unredacted secrets"
```

Expected: `CLEAN: no unredacted secrets`. Any other output is a real leak —
stop and fix before continuing.

- [ ] **Step 4: Confirm plists staged as readable text**

```bash
find /tmp/halbert-stage-verify -name '*.plist' | head -3 | while read f; do
  echo "--- $f"; head -3 "$f"
done
```

Expected: readable XML (`<?xml version=...`), not binary or U+FFFD
replacement characters. Skip if the host has no staged plists.

- [ ] **Step 5: Clean up**

```bash
rm -rf /tmp/halbert-stage-verify
```

---

## Phase B — Role scopes

### Task 7: Expand `~` in manifest patterns

`Manifest.iter_paths()` derives each glob's root with `os.path.dirname` and
walks it via `os.walk`, neither of which expands `~`. Several role paths are
per-user (`~/Library/LaunchAgents`, `~/.zshrc`), so without this they silently
match nothing.

**Files:**
- Modify: `halbert_core/halbert_core/config/manifest.py:20-27`
- Test: `halbert_core/tests/test_config_roles.py`

- [ ] **Step 1: Write the failing test**

Create `halbert_core/tests/test_config_roles.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_roles.py -v
```

Expected: the three home-expansion tests FAIL (`~` still literal).
`test_absolute_paths_are_unchanged` PASSES.

- [ ] **Step 3: Expand at load time**

In `halbert_core/halbert_core/config/manifest.py`, replace `from_file`
(lines 20–27) with:

```python
    @classmethod
    def from_file(cls, path: str) -> "Manifest":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # Role manifests reference per-user paths (~/Library/LaunchAgents,
        # ~/.zshrc). Neither os.path.dirname nor os.walk expands ~, so an
        # unexpanded pattern silently matches nothing.
        include = [os.path.expanduser(p) for p in data.get("include", [])]
        exclude = [os.path.expanduser(p) for p in data.get("exclude", [])]
        parsers = data.get("parsers", {})
        return cls(include, exclude, parsers)
```

`os` is already imported at the top of the file.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_roles.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "fix(config): expand ~ in manifest include/exclude patterns

Role manifests reference per-user paths (~/Library/LaunchAgents, ~/.zshrc).
Neither os.path.dirname nor os.walk expands ~, so those patterns matched
nothing at all." \
  -- halbert_core/halbert_core/config/manifest.py \
     halbert_core/tests/test_config_roles.py
```

---

### Task 8: Write the three role manifests

Path lists come from the design doc's wave-1 sections. Only real, static,
on-disk config — no command-output-only state.

**Files:**
- Create: `config/scopes/network.yml`, `config/scopes/service.yml`, `config/scopes/storage.yml`

- [ ] **Step 1: Create `config/scopes/network.yml`**

```yaml
# network_admin — interfaces, DNS, routing, wireless, VPN, name resolution.
#
# Firewall rule files are deliberately NOT here: they are primary to
# security_admin and aliased back into this scope by config/roles.py.
# Command-output-only state (ip/ss/networksetup/scutil) is excluded by
# definition — this manifest harvests files, not live state.
include:
  # ── Linux ──
  - /etc/NetworkManager/system-connections/*
  - /etc/NetworkManager/NetworkManager.conf
  - /etc/NetworkManager/conf.d/*
  - /etc/NetworkManager/dispatcher.d/*
  - /etc/systemd/network/*.network
  - /etc/systemd/network/*.netdev
  - /etc/systemd/network/*.link
  - /etc/systemd/resolved.conf
  - /etc/netplan/*.yaml
  - /etc/network/interfaces
  - /etc/wpa_supplicant/*.conf
  - /etc/iwd/main.conf
  - /etc/netctl/*
  - /etc/dnsmasq.conf
  - /etc/openvpn/*.conf
  - /etc/hosts
  - /etc/hostname
  - /etc/resolv.conf
  - /etc/nsswitch.conf
  # RHEL <= 8 (removed in RHEL 9 in favour of NM keyfiles)
  - /etc/sysconfig/network-scripts/ifcfg-*
  # SUSE uses a differently-shaped tree under the same parent
  - /etc/sysconfig/network/ifcfg-*
  - /etc/sysconfig/network/routes
  # ── macOS ──
  # preferences.plist is XML, world-readable, and holds the full
  # networksetup backing store (services, DNS, IPv4 config, service order).
  - /Library/Preferences/SystemConfiguration/preferences.plist
  - /etc/pf.conf
  - /etc/pf.anchors/*
  - /etc/networks
exclude:
  # WiFi PSK store — unreadable even to root (TCC), listed for intent.
  - /Library/Preferences/SystemConfiguration/com.apple.airport.preferences.plist
  - /etc/NetworkManager/system-connections/*.bak
```

- [ ] **Step 2: Create `config/scopes/service.yml`**

```yaml
# service_admin — what runs at boot/login and how it is supervised.
#
# macOS is the rich side here (LaunchDaemons/LaunchAgents, 100% XML).
# Linux is deliberately NARROW: every systemd unit routes to its own
# subsystem first (.mount -> storage, .network -> network), so only the
# service-manager's own config and unclaimed units belong here.
include:
  # ── macOS (rich) ──
  - /Library/LaunchDaemons/*.plist
  - /Library/LaunchAgents/*.plist
  - ~/Library/LaunchAgents/*.plist
  # ── Linux (narrow by design) ──
  - /etc/systemd/system.conf
  - /etc/systemd/user.conf
  - /etc/init.d/*
  - /etc/rc.local
  - /etc/xinetd.d/*
  - /etc/tmpfiles.d/*.conf
  # OpenRC (Gentoo)
  - /etc/conf.d/*
  - /etc/runlevels/*
exclude:
  # Apple stock daemons (~422 files) are inventory, not host configuration.
  - /System/Library/LaunchDaemons/**
  - /System/Library/LaunchAgents/**
```

- [ ] **Step 3: Create `config/scopes/storage.yml`**

```yaml
# storage_admin — mount intent, encryption, RAID/LVM/pool config, backup
# policy.
#
# macOS is docs-only for this role: there is no /etc/fstab, and
# /etc/synthetic.conf does not exist on a stock machine. APFS state is
# command-output-only (diskutil apfs list). The autofs entries below are
# the only real macOS files, and only when autofs is in use.
include:
  # ── Linux: mount + encryption intent ──
  - /etc/fstab
  - /etc/crypttab
  - /etc/systemd/system/*.mount
  - /etc/systemd/system/*.automount
  - /etc/systemd/system/*.swap
  # ── Linux: RAID / LVM / multipath ──
  - /etc/mdadm/mdadm.conf      # Debian, SUSE
  - /etc/mdadm.conf            # RHEL, Arch
  - /etc/lvm/lvm.conf
  - /etc/lvm/profile/*
  - /etc/multipath.conf
  # ── Linux: ZFS / btrfs ──
  - /etc/zfs/zpool.cache
  - /etc/zfs/zed.d/*
  - /etc/zfs/vdev_id.conf
  - /etc/snapper/configs/*
  - /etc/default/snapper
  - /etc/sysconfig/btrfsmaintenance
  # ── Backup policy (folds into storage; see design doc) ──
  - /etc/borgmatic.d/*.yaml
  - /etc/restic/*
  - /etc/rsnapshot.conf
  - /etc/timeshift/timeshift.json
  - /etc/sanoid/sanoid.conf
  - /etc/btrbk/btrbk.conf
  # ── macOS: autofs only ──
  - /etc/auto_master
  - /etc/auto_home
  - /etc/autofs.conf
  - /etc/synthetic.conf
exclude:
  - /etc/lvm/archive/**
  - /etc/lvm/backup/**
```

- [ ] **Step 4: Verify all three parse and resolve**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -c "
from halbert_core.config.manifest import Manifest
for role in ('network', 'service', 'storage'):
    m = Manifest.from_file(f'../config/scopes/{role}.yml')
    print(f'{role}: {len(m.include)} includes, {len(m.exclude)} excludes, {len(m.iter_paths())} files match on this host')
"
```

Expected: each loads without error and prints counts. On macOS, `service`
should match a substantial number of files; `storage` may match zero or few —
that is correct and expected per the design doc.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "feat(config): add network/service/storage role manifests

Wave-1 role scopes from the role-scoped harvesting design. Paths cover
Linux distro divergence (RHEL vs SUSE ifcfg trees, Debian vs RHEL mdadm)
and macOS. Command-output-only state is excluded by definition; firewall
files live in security_admin and are aliased into network." \
  -- config/scopes/network.yml config/scopes/service.yml config/scopes/storage.yml
```

---

### Task 9: Build the role registry

A single module naming the roles, their manifests, their alias memberships,
and their platform gating — so the staging code and the scope-registration
code read from one source instead of each hardcoding the list.

**Files:**
- Create: `halbert_core/halbert_core/config/roles.py`
- Test: `halbert_core/tests/test_config_roles.py`

- [ ] **Step 1: Write the failing test**

Append to `halbert_core/tests/test_config_roles.py`:

```python
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


def test_storage_is_docs_only_on_macos():
    """macOS has no fstab; storage_admin ships docs-only there."""
    assert ROLES["storage_admin"].file_backed_on("Linux") is True
    assert ROLES["storage_admin"].file_backed_on("Darwin") is False


def test_network_is_file_backed_on_both_platforms():
    assert ROLES["network_admin"].file_backed_on("Linux") is True
    assert ROLES["network_admin"].file_backed_on("Darwin") is True


def test_roles_for_platform_excludes_docs_only_roles():
    linux = roles_for_platform("Linux")
    darwin = roles_for_platform("Darwin")
    assert "storage_admin" in linux
    assert "storage_admin" not in darwin
    assert "service_admin" in darwin


def test_firewall_files_alias_network_into_security():
    """Design decision: firewall is primary to security, aliased to network."""
    assert "security_admin" in ROLES["network_admin"].aliases_from


def test_role_scope_is_immutable():
    import dataclasses

    assert dataclasses.is_dataclass(RoleScope)
    assert ROLES["network_admin"].__dataclass_params__.frozen
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_roles.py -v
```

Expected: `ModuleNotFoundError: No module named 'halbert_core.config.roles'`.

- [ ] **Step 3: Create the registry**

Create `halbert_core/halbert_core/config/roles.py`:

```python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Role scope registry.

One source of truth for the role axis: which roles exist, which manifest
feeds each, where each stages, and which platforms each is file-backed on.
Both the staging code and the SourcePrep scope registration read from here
rather than hardcoding the list twice.

Names follow the DiscoveryType vocabulary in discovery/schema.py, in
underscore form so `id == display_name` and reconcile-by-name matches
query-by-id (the existing knowledge-linux/knowledge_linux split is a
hyphen/underscore mismatch we are not repeating).

Design: .handoff/ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List

# Repo-relative manifest directory. Manifests live outside halbert_core so
# they are editable as configuration, alongside config/config-registry.yml.
_MANIFEST_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "scopes")
)


@dataclass(frozen=True)
class RoleScope:
    """One role scope: its manifest, staging location, and platform reach."""

    name: str
    manifest: str
    #: platform.system() values where this role harvests real files.
    #: A role absent here is docs-only on that platform, not broken —
    #: e.g. storage_admin on macOS (no fstab, no stock synthetic.conf).
    file_backed_platforms: tuple = ()
    #: Roles whose primary-owned files are aliased INTO this scope.
    #: Membership is a mask over one shared index, so aliasing costs no
    #: extra indexing — see the design doc's primary+alias section.
    aliases_from: tuple = ()

    def file_backed_on(self, system: str) -> bool:
        return system in self.file_backed_platforms


ROLES: Dict[str, RoleScope] = {
    "network_admin": RoleScope(
        name="network_admin",
        manifest="network.yml",
        file_backed_platforms=("Linux", "Darwin"),
        # Firewall rule files are primary to security_admin (they answer
        # "is this machine hardened", not "how does this machine connect")
        # but a network question still needs them.
        aliases_from=("security_admin",),
    ),
    "service_admin": RoleScope(
        name="service_admin",
        manifest="service.yml",
        file_backed_platforms=("Linux", "Darwin"),
    ),
    "storage_admin": RoleScope(
        name="storage_admin",
        manifest="storage.yml",
        # macOS: no fstab, and /etc/synthetic.conf does not exist on a
        # stock host. Docs-only there by design.
        file_backed_platforms=("Linux",),
        aliases_from=("sharing_admin",),
    ),
}


def manifest_path_for(role: str) -> str:
    """Absolute path to a role's manifest file."""
    return os.path.join(_MANIFEST_DIR, ROLES[role].manifest)


def staging_subdir_for(role: str) -> str:
    """Directory name under sourceprep/host/ for a role's staged files."""
    return role.removesuffix("_admin")


def roles_for_platform(system: str) -> List[str]:
    """Role names that harvest real files on this platform.

    Docs-only roles are excluded: staging them would create an empty scope,
    and under scope_mode="hard" an empty mask excludes everything.
    """
    return [name for name, role in ROLES.items() if role.file_backed_on(system)]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_roles.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "feat(config): add role scope registry

One source of truth for the role axis: manifest path, staging subdir,
platform gating, and alias membership per role. Docs-only roles are
gated out of staging because an empty scope under scope_mode=hard
excludes everything rather than narrowing." \
  -- halbert_core/halbert_core/config/roles.py \
     halbert_core/tests/test_config_roles.py
```

---

### Task 10: Stage role trees from their manifests

**Files:**
- Modify: `halbert_core/halbert_core/tools/register_host_project.py`
- Test: `halbert_core/tests/test_host_staging_redacted.py`

- [ ] **Step 1: Write the failing test**

Append to `halbert_core/tests/test_host_staging_redacted.py`:

```python
from halbert_core.tools.register_host_project import stage_role_tree


def test_stage_role_tree_writes_under_role_subdir(tmp_path, monkeypatch):
    src = tmp_path / "etc"
    src.mkdir()
    (src / "fake.conf").write_text("[Unit]\nDescription=Fake\n")

    man = tmp_path / "role.yml"
    man.write_text(f"include:\n  - {src}/*.conf\nexclude: []\nparsers: {{}}\n")

    staging = tmp_path / "sourceprep" / "host"
    count = stage_role_tree("network_admin", staging, manifest_path=str(man))

    assert count == 1
    assert (staging / "network").exists()
    staged = list((staging / "network").rglob("fake.conf"))
    assert len(staged) == 1
    assert "Description=Fake" in staged[0].read_text()


def test_stage_role_tree_redacts(tmp_path):
    src = tmp_path / "etc"
    src.mkdir()
    (src / "wifi.conf").write_text("[wifi-security]\npsk=topsecretvalue\n")

    man = tmp_path / "role.yml"
    man.write_text(f"include:\n  - {src}/*.conf\nexclude: []\nparsers: {{}}\n")

    staging = tmp_path / "host"
    stage_role_tree("network_admin", staging, manifest_path=str(man))

    text = "".join(p.read_text() for p in (staging / "network").rglob("*.conf"))
    assert "topsecretvalue" not in text


def test_stage_role_tree_empty_manifest_creates_no_dir(tmp_path):
    man = tmp_path / "role.yml"
    man.write_text("include:\n  - /nonexistent/**/*.conf\nexclude: []\nparsers: {}\n")

    staging = tmp_path / "host"
    count = stage_role_tree("storage_admin", staging, manifest_path=str(man))

    assert count == 0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_host_staging_redacted.py -v -k role_tree
```

Expected: `ImportError: cannot import name 'stage_role_tree'`.

- [ ] **Step 3: Implement `stage_role_tree`**

In `halbert_core/halbert_core/tools/register_host_project.py`, add after
`_stage_config_files`:

```python
def stage_role_tree(
    role: str,
    staging_root: Path,
    manifest_path: Optional[str] = None,
) -> int:
    """Stage one role's manifest-matched config under staging_root/<role>/.

    Files go through the same redaction path as _stage_config_files — the
    staging root is SourcePrep-visible, so nothing raw may land here.

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
    staged = _stage_config_files(paths, role_root)
    logger.info("Staged %d files for role %s under %s", staged, role, role_root)
    return staged
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_host_staging_redacted.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "feat(staging): stage per-role config trees from role manifests

stage_role_tree resolves a role's manifest, walks its include globs, and
stages matches under sourceprep/host/<role>/ through the same redaction
path as the flat host tree." \
  -- halbert_core/halbert_core/tools/register_host_project.py \
     halbert_core/tests/test_host_staging_redacted.py
```

---

### Task 11: Register the role scopes in the SourcePrep template

**Files:**
- Modify: `halbert_core/halbert_core/integrations/sourceprep_template.yml:45-62`
- Modify: `halbert_core/halbert_core/integrations/sourceprep_setup.py` (`_stage_host_tree`)
- Test: `halbert_core/tests/test_config_roles.py`

- [ ] **Step 1: Write the failing test**

Append to `halbert_core/tests/test_config_roles.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_roles.py -v -k template
```

Expected: the first three FAIL (role scopes absent);
`test_existing_scopes_are_preserved` PASSES.

- [ ] **Step 3: Add the scopes to the template**

In `halbert_core/halbert_core/integrations/sourceprep_template.yml`, add after
the `host` scope entry (after line 50, before `- id: knowledge-linux`):

```yaml
  # Role axis (wave 1). Additive to the flat `host` scope above — these are
  # narrower siblings, not replacements. Each points at the subdirectory
  # stage_role_tree() writes. A role that is docs-only on this platform is
  # not staged and its scope stays empty; roles.py gates that.
  - id: network_admin
    paths: ["host/network"]
    pipeline_profile: system_config
  - id: service_admin
    paths: ["host/service"]
    pipeline_profile: system_config
  - id: storage_admin
    paths: ["host/storage"]
    pipeline_profile: system_config
```

- [ ] **Step 4: Wire role staging into `apply()`**

In `halbert_core/halbert_core/integrations/sourceprep_setup.py`, replace
`_stage_host_tree` (lines 260–268) with:

```python
    def _stage_host_tree(self, root: Path) -> int:
        import platform as _platform

        from ..config.roles import roles_for_platform
        from ..tools.register_host_project import (
            _os_config_paths,
            _stage_config_files,
            stage_role_tree,
        )

        staged = _stage_config_files(_os_config_paths(), root / "host")
        logger.info("Staged %d host config files under %s/host", staged, root)

        # Role scopes stage into sibling subdirectories under host/. Only
        # roles that are file-backed on this platform are staged — an empty
        # scope under scope_mode="hard" excludes everything rather than
        # narrowing, so a docs-only role must not get an empty staged tree.
        for role in roles_for_platform(_platform.system()):
            try:
                staged += stage_role_tree(role, root / "host")
            except Exception as e:
                logger.warning("Role staging failed for %s (non-fatal): %s", role, e)

        return staged
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd /Volumes/4TB-BAD/Halbert/halbert_core
python -m pytest tests/test_config_roles.py tests/test_sourceprep_setup.py -v
```

Expected: all pass. `test_sourceprep_setup.py` exercises `apply()`'s call
ordering against a fake transport and must be unaffected.

- [ ] **Step 6: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "feat(sourceprep): register network/service/storage role scopes

Adds the three wave-1 role scopes to the unified project template and
stages each role's tree during apply(). Platform-gated via roles.py:
a docs-only role is not staged, because an empty scope under
scope_mode=hard excludes everything instead of narrowing." \
  -- halbert_core/halbert_core/integrations/sourceprep_template.yml \
     halbert_core/halbert_core/integrations/sourceprep_setup.py \
     halbert_core/tests/test_config_roles.py
```

---

### Task 12: Add scope-isolation queries to the quality gate

**Files:**
- Modify: `scripts/corpus_quality_gate.py` (the `SCOPED_QUERIES` list, around line 259)

- [ ] **Step 1: Confirm the entry shape**

```bash
cd /Volumes/4TB-BAD/Halbert
sed -n '263,270p' scripts/corpus_quality_gate.py
```

Expected: entries use the keys `id`, `query`, `scope`, `expected_terms`, and
`forbidden_path_prefix`. `expected_terms` are matched against chunk *text*
(lowercased), never against path strings. `forbidden_path_prefix` asserts no
returned chunk's `source_path` starts with that prefix — that is the isolation
assertion.

- [ ] **Step 2: Add role-scope queries**

Append these entries to the `SCOPED_QUERIES` list in
`scripts/corpus_quality_gate.py` (around line 320, after the last existing
entry and before the closing `]`):

```python
    # ── role scopes (wave 1) ──
    # Content queries: each role must return its own subsystem's config.
    {"id": "r01_network_dns", "query": "DNS resolver configuration",
     "scope": "network_admin", "expected_terms": ["nameserver", "dns"],
     "forbidden_path_prefix": "host/storage/"},
    {"id": "r02_network_iface", "query": "network interface address configuration",
     "scope": "network_admin", "expected_terms": ["interface"],
     "forbidden_path_prefix": "host/storage/"},
    {"id": "r03_service_launch", "query": "program that runs at login",
     "scope": "service_admin", "expected_terms": ["label"],
     "forbidden_path_prefix": "host/network/"},
    {"id": "r04_service_manager", "query": "service manager configuration",
     "scope": "service_admin", "expected_terms": ["launch"],
     "forbidden_path_prefix": "host/storage/"},
    {"id": "r05_storage_mounts", "query": "persistent filesystem mount options",
     "scope": "storage_admin", "expected_terms": ["mount"],
     "forbidden_path_prefix": "host/network/"},
    {"id": "r06_storage_crypt", "query": "encrypted volume mapping",
     "scope": "storage_admin", "expected_terms": ["crypt"],
     "forbidden_path_prefix": "host/network/"},
    # Isolation probes: a role scope must never surface knowledge/ docs,
    # which belong to the platform axis, not the role axis.
    {"id": "r07_iso_network_no_docs", "query": "network interface configuration",
     "scope": "network_admin", "expected_terms": [],
     "forbidden_path_prefix": "knowledge/"},
    {"id": "r08_iso_service_no_docs", "query": "startup daemon",
     "scope": "service_admin", "expected_terms": [],
     "forbidden_path_prefix": "knowledge/"},
```

Note: `r05`/`r06` will return zero chunks on a macOS host, because
`storage_admin` is docs-only there by design. Interpret a zero-chunk result on
those two as expected-on-macOS, not as a gate failure — the same way the
existing `s21`–`s24` cross-platform negatives are handled.

- [ ] **Step 3: Verify the file still parses**

```bash
cd /Volumes/4TB-BAD/Halbert
python -c "import ast; ast.parse(open('scripts/corpus_quality_gate.py').read()); print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
cd /Volumes/4TB-BAD/Halbert
git commit -m "test(gate): add role-scope isolation queries

Six content queries plus two cross-role isolation probes for the wave-1
role scopes, following the existing platform-scope pattern." \
  -- scripts/corpus_quality_gate.py
```

---

## Blocked on external verification

These cannot be completed from this machine — SourcePrep's source is not
reachable here (only its staged data directory under
`~/.local/share/halbert/sourceprep`). Both are recorded in the design doc's
"Unverified claims" section. **Confirm them against a running daemon before
treating the role scopes as production-ready.**

- [ ] **Confirm scope lookup fails closed.** Reportedly an unrecognized scope
  name yields `mask=None` and falls back to the global union with HTTP 200 — a
  typo'd scope would silently search the entire corpus, the exact inverse of
  narrowing. Test by issuing a scoped query with a deliberately bogus scope
  name and checking whether it returns results or an error.

- [ ] **Confirm `to_remove` actually removes.** `sourceprep_setup.py:334`
  computes `to_remove` from `rec.get("paths")`, sourced from `_list_scopes()`
  (`GET /projects/{pid}/scopes`). If that endpoint returns summaries without a
  `paths` key, `to_remove` is always empty and scope masks only ever grow. Test
  by inspecting the raw `GET /projects/{pid}/scopes` response for a `paths`
  key. If absent, fix by fetching `GET /scopes/{sid}` per scope.

- [ ] **Run the quality gate end-to-end** once a build has completed, and
  confirm the eight new role queries pass.

---

## Out of scope for this plan

Tracked in the design doc, deliberately not built here:

- Waves 2 and 3 (`security_admin`, `shell_admin`, `package_admin`,
  `boot_admin`, `sharing_admin`) — path sketches exist in the design doc.
- The `<role>_knowledge` tier and the adaptive "recently accessed" scope.
- Query-time auto-routing to a role scope. Role scopes are invoked by name
  for now.
- Curated high-priority docs bundles per role.
- Registering the macOS scanners. `discovery/engine.py::_register_default_scanners`
  registers none of `discovery/scanners/macos/*`, so macOS role scopes ship
  with harvested config but no live discovery behind them. Separate work.
- `declarative_config` degradation for NixOS and Gentoo.
