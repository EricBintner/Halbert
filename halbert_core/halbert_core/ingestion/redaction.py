# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Strip credentials out of harvested host configuration before indexing.

`redact_text` is the last thing that runs before a host's live config text is
staged into a searchable knowledge scope, so the guarantee it owes is narrow
and absolute: no plaintext credential reaches the index.

Two passes cooperate:

* a **line pass** (`redact_structured_values`) that classifies every line in
  its own format's terms -- plist XML, JSON, YAML, ini/systemd/NetworkManager
  keyfiles, fstab option lists -- and redacts the values it recognises as
  credentials;
* a set of **substitutions** (`TOKEN_RE` and friends) for shapes that are not
  key/value at all: emails, addresses, JWTs, PEM blocks.

The line pass owns every `key<separator>value` pair, *including inline ones*.
An earlier version bailed out the moment a value was inline and handed the
decision back to `TOKEN_RE`, which is format-blind. That single boundary
error caused most of the leaks this module has had, because a format-aware
question -- where does this value end? -- was being answered with `\\S+`.
"""
from __future__ import annotations
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

SECRET = "<secret>"
# Inside XML a literal `<secret>` reads as an unknown element and breaks the
# document; plist values get a marker that lives in the text node instead.
PLIST_REDACTION = "[redacted]"

# --- The one keyword predicate -------------------------------------------
#
# Every path in this module asks `_is_secret_key()` and nothing else. Before
# this rewrite there were two tests with different semantics -- `TOKEN_RE`
# required the keyword to sit immediately against the separator, while the
# line pass matched it as a substring -- so the same key name got opposite
# outcomes depending only on whether its value happened to be inline.
# `wep-key0=` leaked for exactly that reason.

# Tier 1: matched as a substring anywhere in the normalised key, so
# `wifi-password`, `admin_token`, `wep-key0` and `encryption_passphrase` are
# all covered without listing each spelling.
#
# `api` and `key` are the two loose entries -- they will also fire inside
# unrelated words. They predate this rewrite and harvested manifests already
# depend on them, so they stay; `_NON_SECRET_KEYS` below carves out the small
# set of real config keys they misfire on. `privatekey`/`presharedkey` used to
# be listed separately and are dropped as redundant: `key` subsumes both.
_SECRET_SUBSTRINGS: Tuple[str, ...] = (
    "api",
    "authorization",
    "bearer",
    "credential",
    "key",
    "oauth",
    "passcode",
    "passcommand",
    "passphrase",
    "passwd",
    "password",
    "psk",
    "secret",
    "token",
)

# Tier 2: matched only when the key's *last* word is one of these. These are
# the short spellings real configs use (`pass=`, `auth=`, `pin=`, `seed=`),
# and every one is unsafe as a plain substring -- "pin" occurs inside
# "mapping", "pass" inside "bypass" and "compass", "seed" inside "seeded".
#
# Last word rather than any word, because in `key=value` naming the head noun
# says what the value *is*: `db_pass` holds a pass, but `auth-alg` holds an
# algorithm (NetworkManager writes `auth-alg=open`) and
# `smtpd_sasl_auth_enable` holds a boolean. Matching any word redacted both of
# those. The cost is that a trailing qualifier hides the noun -- `seed_value`
# is missed where `seed` is caught -- which is the same shape of trade the
# tier-1 substrings make in the other direction.
_SECRET_WORDS = frozenset(
    {"auth", "cred", "mfa", "otp", "pass", "pin", "pw", "pwd", "seed", "totp"}
)

# Keys that contain a tier-1 substring but are demonstrably not credentials:
# the NetworkManager/wpa_supplicant security *mode*, the console keymap and
# keyboard model, and the Kubernetes schema version. Compared by whole-key
# equality, never as a substring, so a longer name that merely contains one
# of these (`keymap_secret`) cannot slip through the exemption.
_NON_SECRET_KEYS = frozenset(
    {"apiversion", "key-mgmt", "key_mgmt", "keyboard", "keymap"}
)

# Key normalisation: drop XML element tags, then trim surrounding quotes,
# braces, dashes and other punctuation, so `"password"`, `{"api_key"`,
# `--password` and `<key>Password</key>` all reduce to the same token.
_XML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
_KEY_TRIM_RE = re.compile(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$")
# Split on punctuation and on camelCase humps: `wifi-password` -> wifi,
# password; `ListenPort` -> Listen, Port.
_WORD_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])")


def _normalize_key(raw: str) -> str:
    return _KEY_TRIM_RE.sub("", _XML_TAG_RE.sub("", raw).strip())


def _is_secret_key(raw: str) -> bool:
    """True when a key's *value* must be treated as a credential."""
    key = _normalize_key(raw)
    if not key:
        return False
    low = key.lower()
    if low in _NON_SECRET_KEYS:
        return False
    if any(needle in low for needle in _SECRET_SUBSTRINGS):
        return True
    words = [w for w in _WORD_SPLIT_RE.split(key) if w]
    return bool(words) and words[-1].lower() in _SECRET_WORDS


# --- Substitution patterns ------------------------------------------------
#
# TOKEN_RE is now a *backstop*, not the main event: the line pass reaches
# every `key<sep>value` shape it can match, so in practice this only fires on
# text the line pass declined. It is kept because `redact_event` feeds it log
# messages, which are prose rather than config, and because a second net
# costs nothing. Its vocabulary is generated from the tier-1 list above so
# there is a single place to add a keyword. Longest alternative first, so the
# alternation prefers `password` over `passwd` where both could match.
TOKEN_RE = re.compile(
    r"(?i)(?:%s)[ \t]*[=:][ \t]*\S+"
    % "|".join(sorted((re.escape(s) for s in _SECRET_SUBSTRINGS), key=len, reverse=True))
)
HOME_RE = re.compile(r"/home/[^/\s]+")
# The local part is bounded (RFC 5321 caps it at 64) and guarded by a
# lookbehind that refuses to start in the middle of a local-part run.
# Without both, `[A-Za-z0-9._%+-]+@` retried from every offset of a long
# unbroken word and the match cost grew quadratically: measured 35 ms at
# 5,000 characters, 569 ms at 20,000 and 5,111 ms at 60,000. Line breaks used
# to bound that, but this module now runs over whole files, where a one-line
# base64 blob or a long JSON token is ordinary.
EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}"
)
IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
IPV6_RE = re.compile(r"\b([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b")
MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}\b")
# JWT (very rough): three base64url segments
JWT_RE = re.compile(r"\beyJ[0-9A-Za-z_-]*\.[0-9A-Za-z_-]*\.[0-9A-Za-z_-]*\b")
# PEM headers/footers
PEM_RE = re.compile(r"-----BEGIN [^-]+-----[\s\S]+?-----END [^-]+-----", re.MULTILINE)
# macOS: local Kerberos realm identifiers in com.apple.smb.server.plist and
# related SystemConfiguration plists. Format is LKDC:SHA1.<40 hex chars>.
LKDC_RE = re.compile(r"LKDC:SHA1\.[0-9A-Fa-f]{40}")


# --- Indentation ----------------------------------------------------------


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def _indent_width(ws: str) -> int:
    """Visual width of an indent, with tabs expanded to 8-column stops.

    Comparing raw string lengths made one tab (len 1) look like a dedent from
    four spaces (len 4), which silently ended a value early. YAML forbids tabs
    in indentation, but ini, systemd and fstab all use them, and this module
    sees those files too.
    """
    width = 0
    for ch in ws:
        width = (width // 8 + 1) * 8 if ch == "\t" else width + 1
    return width


# --- Line classification: is a child line a value, or structure? ----------
#
# The hard case is telling a child line that is a *value* from one that is
# *structure*:
#
#     password:                 api:
#       "pa55:word:here"          endpoint: https://x
#
# Both are "keyword key, separator at end of line, indented child". Shape
# decides it, not a keyword: `- ` is a sequence item, and an unquoted or
# quoted `key:`/`key =` prefix opens a nested mapping.
_KEY_LINE_RE = re.compile(r"^([ \t]*)([^\s:=#][^\s:=]*)[ \t]*[=:][ \t]*(.*)$")
# YAML block scalar header: | or >, with optional indentation and chomping
# modifiers (|-, |+, >-, |2, |2-), plus an optional trailing comment. YAML
# permits `password: | # note`; without the comment branch the header was not
# recognised, TOKEN_RE ate the `|`, and the whole block body was orphaned in
# plaintext -- the exact failure the pass ordering exists to prevent.
_BLOCK_HEADER_RE = re.compile(r"^[|>][0-9]*[-+]?(?:[ \t]+#.*)?$")
_SEQUENCE_ITEM_RE = re.compile(r"^-(?:\s|$)")
# A colon opens a mapping only when it is followed by whitespace or the end of
# the line; `pa55:word:here` is a plain scalar, not a mapping. (Verified
# against PyYAML: `yaml.safe_load('password:\n  pa55:word:here\n')` yields
# `{'password': 'pa55:word:here'}`.) An earlier comment here asserted the
# opposite -- that YAML reads `pa55:word` as a mapping -- which a parser
# contradicts, and the loose pattern it justified left that scalar unredacted.
# `=` needs no such guard: ini and systemd have no `key=value` ambiguity.
_MAPPING_ITEM_RE = re.compile(r"^[^\s:=#][^\s:=]*[ \t]*(?:=|:(?:[ \t]|$))")
# A *quoted* token can also be a mapping key -- netplan writes SSIDs that way
# (`"HomeNet":`). Treating a leading quote as decisive proof of "scalar" ate
# the first entry of `keys:` mappings and left the rest, producing a
# half-destroyed file.
_QUOTED_MAPPING_RE = re.compile(r"""^("[^"]*"|'[^']*')[ \t]*(?:=|:(?:[ \t]|$))""")


def _is_structure(content: str) -> bool:
    """True when a child line opens structure rather than being a scalar value.

    `content` is the line with indentation stripped, and must not be a comment
    -- the caller filters those out first, because a comment is neither a
    value nor a terminator.

    Two known consequences of the mapping rule, both accepted deliberately:

    * A bare URL alone on a child line (`https://host/path`) has no space
      after its colon, so it classifies as a scalar and gets redacted. Under
      a secret-keyword parent that is arguably the right answer, and it is
      the price of not leaking `pa55:word:here`.
    * The `=` branch spares a YAML scalar that happens to contain one:
      PyYAML reads `password:\\n  foo=bar` as `{'password': 'foo=bar'}`, but
      the shape is indistinguishable from an ini/systemd `key=value`, which
      the branch exists to protect. A credential of that literal form is left
      in place. Narrowing this is a format-detection problem, not a pattern
      one.

    Not covered: a sequence item that is itself a secret (`passwords:\\n  -
    hunter2`). The `- ` guard exists to protect `api:\\n  - foo`, which is
    ordinary harvested netplan/cloud-init structure, and the two cannot be
    told apart by shape. The guard wins; sequence-item credentials are a known
    gap rather than an oversight.
    """
    if _SEQUENCE_ITEM_RE.match(content):
        return True
    if content[:1] in ('"', "'"):
        return bool(_QUOTED_MAPPING_RE.match(content))
    return bool(_MAPPING_ITEM_RE.match(content))


# --- Inline `key<sep>value` on a single line ------------------------------

# Characters that end a key token when scanning backwards from a separator.
# Quotes are deliberately absent: they belong to the key and are removed by
# `_normalize_key`, which is what lets `"password":` and `{"api_key":` be
# recognised at all.
_KEY_STOP_CHARS = frozenset(" \t\r,;{}[]()<>=:/|&")


def _iter_pairs(line: str) -> Iterator[Tuple[int, str, int, int]]:
    """Yield `(key_start, key_text, separator_index, value_start)` per pair.

    Every `=` and `:` on the line is a candidate; the key is the run of
    characters before it, back to a delimiter. Separators with no key in front
    of them (`Acquire::http`) are skipped.
    """
    n = len(line)
    for sep, ch in enumerate(line):
        if ch not in "=:":
            continue
        end = sep
        while end > 0 and line[end - 1] in " \t":
            end -= 1
        start = end
        while start > 0 and line[start - 1] not in _KEY_STOP_CHARS:
            start -= 1
        if start == end:
            continue
        value = sep + 1
        while value < n and line[value] in " \t":
            value += 1
        yield start, line[start:end], sep, value


def _closing_quote(line: str, start: int) -> Optional[int]:
    quote = line[start]
    i = start + 1
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == quote:
            return i
        i += 1
    return None


_BRACKET_PAIRS = {"{": "}", "[": "]"}


def _matching_bracket(line: str, start: int) -> Optional[int]:
    """Index of the bracket closing the one at `start`, on this line only.

    Quote-aware, so a bracket inside a JSON string does not unbalance it.
    """
    stack: List[str] = []
    i = start
    while i < len(line):
        ch = line[i]
        if ch in "\"'":
            close = _closing_quote(line, i)
            if close is None:
                return None
            i = close + 1
            continue
        if ch in _BRACKET_PAIRS:
            stack.append(_BRACKET_PAIRS[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
            if not stack:
                return i
        i += 1
    return None


def _value_end(line: str, value_start: int, whole_line_value: bool) -> Optional[int]:
    """Where the value that begins at `value_start` ends, or None to skip it.

    The rule, and the tradeoff it settles:

    * A **quoted** value ends at its closing quote. This is what stops
      `password = "correct horse battery"` from leaking everything after the
      first word.
    * A value that opens a **JSON object or array** ends at the matching
      close bracket. If the container spans lines the pair is skipped
      entirely (None) and its members are classified on their own terms --
      better than redacting to end of line, which would leave an unbalanced
      brace and orphan the members' text.
    * An **unquoted** value on a line that carries exactly one pair, starting
      the line, runs to end of line. That is the config-file shape -- one
      directive, and everything after the separator is its value -- and it is
      what redacts `psk=correct horse battery staple` in full.
    * Otherwise the value ends at the next delimiter, comma or whitespace. A
      line with several pairs is an option list or a log message, not a
      single-valued directive. This is what keeps `uid=1000,gid=1000` in an
      /etc/fstab cifs line instead of destroying the mount, and what keeps a
      log message readable enough for the email/address substitutions to still
      find their targets.

    Two residual gaps, deliberately accepted:

    * A credential that both contains whitespace *and* shares its line with
      another `key=value` pair loses only its first word. Closing that would
      mean swallowing the rest of every log line, which destroys more than it
      protects.
    * A multi-line JSON container under a secret-sounding key protects only
      the members whose own names look secret. Plists get the stronger
      treatment (see `_redact_plist_container`) because XML close tags make
      the container's extent unambiguous line by line; JSON's do not.
    """
    n = len(line)
    ch = line[value_start]
    if ch in "\"'":
        close = _closing_quote(line, value_start)
        return n if close is None else close + 1
    if ch in _BRACKET_PAIRS:
        close = _matching_bracket(line, value_start)
        return None if close is None else close + 1
    if whole_line_value:
        return n
    end = value_start
    while end < n and line[end] not in " \t,":
        end += 1
    return end


def _redact_inline(line: str) -> str:
    """Redact every inline `key<sep>value` pair whose key is a credential."""
    pairs = list(_iter_pairs(line))
    if not pairs:
        return line
    # "One pair, and it starts the line" is the single-directive shape that
    # earns end-of-line value extent; see `_value_end`.
    whole_line_value = len(pairs) == 1 and pairs[0][0] == len(_leading_ws(line))
    out: List[str] = []
    cursor = 0
    for key_start, key_text, _sep, value_start in pairs:
        if key_start < cursor or not _is_secret_key(key_text):
            continue
        if value_start >= len(line):
            # No value on this line. `redact_structured_values` owns that
            # shape (next-line scalar or block body); redacting the bare key
            # here would destroy `password:` and `keys:` headers.
            continue
        end = _value_end(line, value_start, whole_line_value)
        if end is None:
            continue  # container opens here and closes on a later line
        out.append(line[cursor:key_start])
        out.append(SECRET)
        cursor = end
    if not out:
        return line
    out.append(line[cursor:])
    return "".join(out)


# --- Property list (XML plist) --------------------------------------------
#
# macOS puts credentials in plists, where the key and the value are separate
# *elements*: `<key>Password</key>` followed by `<string>hunter2</string>`.
# No `key<sep>value` pattern can see that, so plists need their own extractor.
_PLIST_KEY_RE = re.compile(r"<key>([^<]*)</key>", re.IGNORECASE)
_TAG_RE = re.compile(r"<(/?)\s*([A-Za-z][A-Za-z0-9_.-]*)([^>]*?)(/?)>")
_PLIST_VALUE_TAGS = frozenset({"string", "data", "integer", "real"})
_PLIST_CONTAINER_TAGS = frozenset({"dict", "array"})
_PLIST_TEXT_RE = re.compile(
    r"(<(string|data|integer|real)\b[^>]*>)(.+?)(</\2>)", re.IGNORECASE
)
_PLIST_OPEN_RE = re.compile(r"<(string|data|integer|real)\b[^>]*>", re.IGNORECASE)
# A malformed plist must not let a container walk run away over the whole
# document; past this many lines we stop looking for the closing tag.
_PLIST_SPAN_LIMIT = 2000


def _redact_plist_element(lines: List[str], row: int, start: int, name: str) -> int:
    """Replace the text of one value element, keeping the XML well-formed."""
    close = "</" + name
    last = min(len(lines), row + _PLIST_SPAN_LIMIT)
    for k in range(row, last):
        idx = lines[k].lower().find(close, start if k == row else 0)
        if idx == -1:
            continue
        if k == row:
            if idx > start:
                lines[row] = lines[row][:start] + PLIST_REDACTION + lines[row][idx:]
            return row
        lines[row] = lines[row][:start] + PLIST_REDACTION
        for blank in range(row + 1, k):
            lines[blank] = ""
        lines[k] = _leading_ws(lines[k]) + lines[k][idx:]
        return k
    # No closing tag in range: drop what is on the opening line and stop
    # rather than blanking the remainder of the document.
    lines[row] = lines[row][:start] + PLIST_REDACTION
    return row


def _redact_plist_line(text: str) -> str:
    return _PLIST_TEXT_RE.sub(lambda m: m.group(1) + PLIST_REDACTION + m.group(4), text)


def _unclosed_value_tag(text: str) -> Optional[re.Match]:
    """The first value tag on this line whose close tag is on a later line."""
    lowered = text.lower()  # hoisted: this loop runs once per open tag
    m = _PLIST_OPEN_RE.search(text)
    while m:
        if ("</" + m.group(1).lower()) in lowered[m.end() :]:
            m = _PLIST_OPEN_RE.search(text, m.end())
            continue
        return m
    return None


def _redact_plist_container(lines: List[str], row: int, start: int) -> int:
    """Redact every string/data leaf inside a `<dict>`/`<array>`.

    Deliberately blunt: a container named by a secret key has its whole
    subtree redacted, because a leaked credential is worse than a lost
    inventory. `<key>` elements are preserved, so the shape of the record --
    which settings exist -- survives even though the values do not.
    """
    depth = 1
    pending: Optional[str] = None
    last = min(len(lines), row + _PLIST_SPAN_LIMIT)
    for k in range(row, last):
        line = lines[k]
        head, tail = (line[:start], line[start:]) if k == row else ("", line)
        if pending:
            idx = tail.lower().find("</" + pending)
            if idx == -1:
                tail = ""  # still inside the value element: drop the content
            else:
                tail = _leading_ws(line) + tail[idx:]
                pending = None
        if pending is None:
            tail = _redact_plist_line(tail)
            open_tag = _unclosed_value_tag(tail)
            if open_tag:
                pending = open_tag.group(1).lower()
                tail = tail[: open_tag.end()] + PLIST_REDACTION
        lines[k] = head + tail
        for m in _TAG_RE.finditer(tail):
            if m.group(2).lower() in _PLIST_CONTAINER_TAGS and not m.group(4):
                depth += -1 if m.group(1) else 1
        if depth <= 0:
            return k
    return last - 1


def _redact_plist_value(lines: List[str], row: int, start: int) -> Optional[int]:
    """Redact the plist value element that follows a secret `<key>`."""
    found = None
    limit = min(len(lines), row + _PLIST_SPAN_LIMIT)
    k, pos = row, start
    while k < limit:
        found = _TAG_RE.search(lines[k], pos)
        if found:
            break
        k, pos = k + 1, 0
    if not found or found.group(1) or found.group(4):
        return None  # close tag, self-closing (`<true/>`), or no value at all
    name = found.group(2).lower()
    if name in _PLIST_CONTAINER_TAGS:
        return _redact_plist_container(lines, k, found.end())
    if name in _PLIST_VALUE_TAGS:
        return _redact_plist_element(lines, k, found.end(), name)
    return None


def _handle_plist_key(lines: List[str], row: int) -> Optional[int]:
    for m in _PLIST_KEY_RE.finditer(lines[row]):
        if _is_secret_key(m.group(1)):
            return _redact_plist_value(lines, row, m.end())
    return None


# --- Values that live on a later line than their key ----------------------


def _handle_deferred_value(lines: List[str], row: int) -> Optional[int]:
    """Redact a next-line scalar or a `|`/`>` block scalar body.

    Returns the index of the last line redacted, or None when this line does
    not have a deferred value -- in which case the caller falls through to the
    inline scanner. That fall-through is the ownership inversion: the line
    pass, which knows the format, keeps the decision instead of handing an
    inline value back to a format-blind regex.
    """
    m = _KEY_LINE_RE.match(lines[row])
    if not m or not _is_secret_key(m.group(2)):
        return None
    rest = m.group(3).strip()
    if rest.startswith("#"):
        rest = ""  # `password: # note` still defers its value to later lines
    is_block = bool(_BLOCK_HEADER_RE.match(rest))
    if rest and not is_block:
        return None  # inline value: `_redact_inline` owns it
    key_indent = _indent_width(m.group(1))

    last: Optional[int] = None
    j = row + 1
    while j < len(lines):
        line = lines[j]
        content = line.strip()
        if not content:
            j += 1  # a blank line does not terminate the value
            continue
        if _indent_width(_leading_ws(line)) <= key_indent:
            break  # dedent: a sibling, not part of the value
        if not is_block:
            if content.startswith("#"):
                # A comment does not terminate the value either -- PyYAML
                # reads `password:\n  # c\n  realsecret` as
                # `{'password': 'realsecret'}`. Treating it as a terminator
                # left the value below it in plaintext. Inside a block scalar
                # a `#` is literal text, so this skip is non-block only.
                j += 1
                continue
            if _is_structure(content):
                break
        lines[j] = _leading_ws(line) + SECRET
        last = j
        if not is_block:
            break  # a plain next-line scalar is a single line
        j += 1
    return last


# --- The line pass --------------------------------------------------------


def redact_structured_values(text: str) -> str:
    """Redact credential values, classifying every line in its own format.

    Preserves the total line count and each line's original ending, so a CRLF
    file stays CRLF rather than acquiring mixed endings on the lines that were
    rewritten.
    """
    raw = text.split("\n")
    endings = ["\r" if ln.endswith("\r") else "" for ln in raw]
    lines = [ln[:-1] if ln.endswith("\r") else ln for ln in raw]

    i = 0
    while i < len(lines):
        for handler in (_handle_plist_key, _handle_deferred_value):
            consumed = handler(lines, i)
            if consumed is not None:
                i = max(consumed, i)
                break
        else:
            lines[i] = _redact_inline(lines[i])
        i += 1
    return "\n".join(line + eol for line, eol in zip(lines, endings))


def redact_text(text: str) -> str:
    # Must run first: TOKEN_RE would otherwise eat the `|` off `password: |`
    # and orphan the block body.
    text = redact_structured_values(text)
    text = TOKEN_RE.sub(SECRET, text)
    text = HOME_RE.sub("/home/<user>", text)
    text = EMAIL_RE.sub("<email>", text)
    text = IPV4_RE.sub("<ip>", text)
    text = MAC_RE.sub("<mac>", text)  # MAC before IPv6 (IPv6 pattern is greedy)
    text = IPV6_RE.sub("<ip6>", text)
    text = JWT_RE.sub("<jwt>", text)
    text = PEM_RE.sub("<pem_block>", text)
    text = LKDC_RE.sub("<lkdc_realm>", text)
    return text


def redact_event(evt: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(evt)
    msg = out.get("message")
    if isinstance(msg, str):
        out["message"] = redact_text(msg)
    data = out.get("data")
    if isinstance(data, dict):
        red = {}
        for k, v in data.items():
            if isinstance(v, str):
                red[k] = redact_text(v)
            else:
                red[k] = v
        out["data"] = red
    return out
