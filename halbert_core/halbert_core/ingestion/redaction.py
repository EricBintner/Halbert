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
import ipaddress
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

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
# keyboard model, the Kubernetes schema version, and two macOS plist keys
# whose values are well-known identifiers rather than secrets. Compared by
# whole-key equality, never as a substring, so a longer name that merely
# contains one of these (`keymap_secret`) cannot slip through the exemption.
#
# The two macOS entries were both observed in real staged output on this host:
#
#   * `SHAuthorizationRight` names an authorization *right*. Its value is a
#     documented identifier -- `system.preferences` -- and `authorization`
#     fired on the name of the right rather than on a credential.
#   * `SecureSocketWithKey` names the *environment variable* launchd should
#     publish a socket's file descriptor under, so its value is a variable
#     name such as `DISPLAY`. `key` fired on an env-var name.
_NON_SECRET_KEYS = frozenset(
    {
        "apiversion",
        "key-mgmt",
        "key_mgmt",
        "keyboard",
        "keymap",
        "securesocketwithkey",
        "shauthorizationright",
    }
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


def _redact_token(match: "re.Match[str]") -> str:
    """TOKEN_RE body: ask the one predicate about the *whole* key.

    TOKEN_RE's match begins at the keyword rather than at the start of the
    key, so on `SecureSocketWithKey = DISPLAY` it matched `Key = DISPLAY` and
    the keyword-vs-key distinction `_NON_SECRET_KEYS` exists to draw was
    invisible to it: the line pass exempted the key and this pass undid it,
    yielding `SecureSocketWith<secret>`. Scanning back to the key's start over
    the same delimiters `_iter_pairs` uses puts this path on the same
    predicate as every other, which is what the module claims to guarantee.
    """
    text, head = match.string, match.group(0)
    start = match.start()
    while start > 0 and text[start - 1] not in _TOKEN_KEY_STOPS:
        start -= 1
    sep = next(i for i, ch in enumerate(head) if ch in "=:")
    if not _is_secret_key(text[start : match.start()] + head[:sep]):
        return head
    return SECRET


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
# An IPv6 address in text is either the *compressed* form -- it contains a
# `::` run -- or the full eight groups. There is no third shape, so a
# colon-separated run that has neither cannot be an address whatever its
# digits are. The three branches below are exactly those two shapes, with the
# compressed one split by whether anything precedes the `::`.
#
# The previous pattern (`\b([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b`) asked
# only for two-to-seven colon-separated groups and so matched any decimal
# triple. Verified before this change: `MaxStartups 10:30:100` -- a real sshd
# tunable -- became `MaxStartups <ip6>`; the `05:11:21` clock inside
# sshd_config's OpenBSD RCS ID became `<ip6>`; and, because `{0,4}` admits
# empty groups, `Acquire::http::Proxy` became `Acquire<ip6>http<ip6>Proxy`.
#
# `\b` is replaced by explicit lookarounds. A word boundary cannot anchor
# before a leading colon, so `::1` was never matched at all -- it survived the
# old blanket redaction by accident rather than by rule.
_H16 = r"[0-9A-Fa-f]{1,4}"
_H16_TAIL = rf"(?:{_H16}(?::{_H16}){{0,6}})?"
IPV6_RE = re.compile(
    r"(?<![0-9A-Za-z.:])"
    r"(?:"
    rf"(?:{_H16}:){{7}}{_H16}"  # full eight groups, no compression
    rf"|(?:{_H16}:){{1,7}}:{_H16_TAIL}"  # compressed, groups before the `::`
    rf"|::{_H16_TAIL}"  # compressed, `::` leads
    r")"
    r"(?![0-9A-Za-z.:])"
)
MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}\b")

# --- Addresses: non-routable is operational data, not a secret ------------
#
# Halbert administers the machine it runs on, so its own loopback and private
# addressing is core operational data rather than a secret it must keep from
# itself. Blanket redaction gutted the files that carry it: `/etc/hosts`
# became `<ip> localhost` / `<ip>` / `<ip> broadcasthost`, and a stock
# `#ListenAddress 0.0.0.0` became `#ListenAddress <ip>`.
#
# A *public* address is different. It can identify this host or a remote peer
# to an outside observer, and harvested config reaches an LLM that may be
# cloud-hosted, so those still go.
#
# `ipaddress.is_private` is deliberately NOT the predicate, despite reading
# like it. Verified on CPython 3.10, its IPv4 list is
#
#   0.0.0.0/8  10/8  127/8  169.254/16  172.16/12  192.0.0.0/29
#   192.0.0.170/31  192.0.2.0/24  192.168/16  198.18/15  198.51.100.0/24
#   203.0.113.0/24  240.0.0.0/4  255.255.255.255/32
#
# and its IPv6 list includes 2001:db8::/32. That list means "not globally
# routable", which sweeps in the RFC 5737 / RFC 3849 documentation ranges and
# the whole of 240/4 -- so `is_private` reports True for 203.0.113.5,
# 192.0.2.1, 198.51.100.5 and 2001:db8::1, every one of which must still be
# redacted. The class predicates that *are* exactly right come from the
# stdlib; the private ranges are named explicitly because the stdlib has no
# predicate for "RFC1918" alone.
#
# `is_private` does subsume loopback, link-local and unspecified for IPv4,
# and 255.255.255.255 as well (via 240/4) -- but since it is unusable for the
# reason above, all four are asked for by name.
#
# fc00::/7 is the v6 half of the same rule. RFC 4193 unique-local addressing
# is what a real dual-stack host numbers its own LAN out of (in practice
# fd00::/8, the locally-assigned half), it is not globally routable, and it
# identifies this machine to an outside observer no more than 192.168.1.42
# does. It is asked for by name for the same reason the RFC1918 ranges are:
# the stdlib's nearest predicates are both wrong here -- `is_private` sweeps
# in 2001:db8::/32, and `is_site_local` is fec0::/10, a *different*
# deprecated range that must still be redacted.
_EXEMPT_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "10.0.0.0/8",  # RFC1918
        "172.16.0.0/12",  # RFC1918
        "192.168.0.0/16",  # RFC1918
        "255.255.255.255/32",  # limited broadcast (`/etc/hosts` broadcasthost)
        "fc00::/7",  # RFC 4193 unique-local (the v6 RFC1918)
    )
)

_IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _is_netmask(addr: ipaddress.IPv4Address) -> bool:
    """True for a dotted quad that is a valid IPv4 subnet mask.

    A mask is not an address. It names no host and no peer, it is pure
    configuration, and every `ifcfg-*` file on RHEL and SUSE carries one --
    all of which the network_admin manifest harvests. Redacting it turned
    `NETMASK=255.255.255.0` into `NETMASK=<ip>`, destroying the one field
    that says how big the subnet is.

    Detected by **value shape** -- contiguous leading ones, the defining
    property of a valid mask -- rather than by key name. Two reasons:

    * A mask has no single key. RHEL writes `NETMASK=`, Debian writes
      `netmask `, ISC dhcpd writes `option subnet-mask`, and rsyncd's
      `hosts allow = 192.168.1.0/255.255.255.0` puts one after a slash with
      no key of its own. A key-name rule needs a vocabulary that grows every
      time a new file format is harvested, and is silently wrong until
      someone notices the gap. The shape rule is complete on day one.
    * The exemption is safe *because* it is shape-based. There are exactly
      33 valid masks, they are the same 33 on every machine on earth, and
      none of them is an assignable host address -- they are prefix
      boundaries. A value drawn from a fixed, universally-known 33-element
      set carries no bits that could identify this host or a remote peer,
      which is the only thing address redaction exists to protect. The
      converse worry -- that a bare `255.255.255.0` in `/etc/hosts` is a
      host entry rather than a mask -- costs nothing either way: it would be
      an entry for a /24's broadcast address, equally non-identifying.

    Implemented by inverting: a run of ones followed by a run of zeros
    inverts to a run of zeros followed by a run of ones, i.e. one less than
    a power of two. `255.0.255.0` has a hole and fails; `255.255.255.255`
    and `0.0.0.0` pass, and were already exempt as broadcast and
    unspecified respectively.
    """
    inverted = int(addr) ^ 0xFFFFFFFF
    return inverted & (inverted + 1) == 0


def _is_exempt_address(addr: _IPAddress) -> bool:
    """True when an address is non-routable and so not a secret.

    `is_loopback` covers 127.0.0.0/8 and ::1; `is_link_local` covers
    169.254.0.0/16 and fe80::/10; `is_unspecified` covers 0.0.0.0 and ::.
    Network containment is version-aware (`IPv4Network.__contains__` returns
    False for an IPv6 address rather than raising), so the v4-only networks
    above are safe to test against either family.

    Netmasks are the one exemption here that is not about routability -- see
    `_is_netmask`. There is no v6 equivalent: IPv6 prefixes are written as
    `/64`, never as a mask address.
    """
    if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
        return True
    if isinstance(addr, ipaddress.IPv4Address) and _is_netmask(addr):
        return True
    return any(addr in net for net in _EXEMPT_NETWORKS)


def _redact_address(match: "re.Match[str]", placeholder: str) -> str:
    """Substitution body for IPV4_RE/IPV6_RE: exempt the non-routable ones."""
    text = match.group(0)
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        # The pattern claimed this was an address and cannot be believed.
        # Fail closed: an unparseable candidate is redacted, never exempted.
        return placeholder
    return text if _is_exempt_address(addr) else placeholder

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
# `_iter_pairs` works a line at a time and so never meets a newline; the
# TOKEN_RE backstop runs over the whole text and must stop at one.
_TOKEN_KEY_STOPS = _KEY_STOP_CHARS | {"\n"}


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
    * An **unquoted** value on a line that carries exactly one *directive*,
      starting the line, runs to end of line. That is the config-file shape --
      one directive, and everything after the separator is its value -- and it
      is what redacts `psk=correct horse battery staple` in full. Which
      candidate pairs count as directives is `_directive_pairs`' question, not
      this one's.
    * Otherwise the value ends at the next delimiter, comma or whitespace. A
      line with several directives is an option list or a log message, not a
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


def _directive_pairs(
    line: str, pairs: List[Tuple[int, str, int, int]]
) -> List[Tuple[int, str, int, int]]:
    """The candidates from `_iter_pairs` that are genuinely sibling directives.

    `_iter_pairs` offers a pair for every `=`/`:` on the line, including the
    ones that sit *inside* a value. Counting those as directives is what made
    a credential containing punctuation leak: `psk=my:pass phrase` looked like
    two pairs, so the line lost single-directive status, and `_value_end`'s
    multi-pair branch cut the value at the first space -- yielding
    `<secret> phrase`. Every secret with a `:` or an `=` in it leaked from its
    second word onwards, which for base64 (WireGuard keys end in `=`) and for
    passphrases is the common case rather than the exotic one.

    The test is positional: a candidate whose key begins before the end of the
    previous directive's value is inside that value, not beside it. The
    previous value's extent is measured with the *conservative* multi-pair
    rule, because whether the line is single-directive is exactly what is
    being decided here -- and that direction of error is the safe one. It can
    only admit a phantom, never reject a real sibling.

    That is what separates the fstab case from the leaks:

        username=alice,password=x,uid=1000     `alice` ends at the comma, so
                                               `password` starts outside it
                                               -- a real sibling.
        psk=my:pass phrase                     `my:pass` runs to the space, so
                                               `pass` starts inside it -- a
                                               phantom.

    Only the *count* is affected. `_redact_inline` still visits every
    candidate, because a phantom can carry a real credential of its own:
    systemd's `Environment="DB_PASS=hunter2"` puts a genuine `KEY=VALUE`
    inside another directive's quoted value, and demoting the pair must not
    demote the redaction with it.
    """
    kept: List[Tuple[int, str, int, int]] = []
    guard = 0
    for pair in pairs:
        key_start, _key, _sep, value_start = pair
        if key_start < guard:
            continue
        kept.append(pair)
        if value_start >= len(line):
            continue  # key with no value: nothing of it extends along the line
        end = _value_end(line, value_start, False)
        # A container that opens here and closes on a later line covers the
        # whole remainder of this one.
        guard = max(guard, len(line) if end is None else end)
    return kept


def _redact_inline(line: str) -> str:
    """Redact every inline `key<sep>value` pair whose key is a credential."""
    pairs = list(_iter_pairs(line))
    if not pairs:
        return line
    # "One directive, and it starts the line" is the single-directive shape
    # that earns end-of-line value extent; see `_value_end`.
    directives = _directive_pairs(line, pairs)
    whole_line_value = (
        len(directives) == 1 and directives[0][0] == len(_leading_ws(line))
    )
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


# --- Credentials with no `key<sep>value` shape ----------------------------
#
# Everything above needs an `=` or a `:` to find a value, and so does the
# TOKEN_RE backstop. Three real shapes in harvested files have neither, and
# staged verbatim until this section existed:
#
#   * `wpa-psk hunter2` -- Debian ifupdown takes WPA credentials as
#     space-separated directives (`/etc/network/interfaces`, network.yml).
#   * `myd --password SUPERSECRET` -- a command-line flag in an init script
#     (`/etc/init.d/*`, service.yml) or a launchd `ProgramArguments` array.
#   * `smbfs://alice:hunter2@fileserver/share` -- credentials inside a URL
#     (`/etc/auto_master`, storage.yml; `http_proxy=` in `/etc/environment`).
#
# All three are matched against **small, exact, whole-token vocabularies**,
# not against `_is_secret_key`. That predicate is a substring test tuned for
# key names, and these positions are far more exposed: the first token of a
# line and a `--flag` are both places where ordinary config carries a
# credential *keyword* without carrying a credential. `sshd_config` alone --
# staged into the flat host tree -- supplies `PasswordAuthentication`,
# `PubkeyAuthentication`, `KbdInteractiveAuthentication`, `HostKey` and
# `AuthorizedKeysFile`, none of them secret. Over-redaction here destroys the
# configuration the assistant exists to reason about, so coverage is traded
# for precision deliberately.

# Directives whose entire first token is the keyword and whose value is the
# rest of the line. Kept to the spellings that are unambiguous on their own:
# a line beginning with exactly `psk` or `wpa-passphrase` is a credential in
# every format that writes it that way.
_SPACE_DIRECTIVE_KEYWORDS = frozenset(
    {
        "passphrase",
        "password",
        "psk",
        "secret",
        "wireless-key",
        "wpa-passphrase",
        "wpa-psk",
    }
)

# Flag names, compared after stripping the leading dash(es).
#
# `key` is deliberately absent. `--key`, `--keyfile`, `--ssl-key` and
# `--keytab` all take a *path*, and redacting the path hides which material a
# service loads while protecting nothing -- the file itself is never staged.
# For the same reason the match is whole-name: `--pass-fd 3` (a file
# descriptor) and `--secret-file /etc/x` (a path) must survive, and they do
# because neither name is in this set.
#
# Single-letter flags are absent too. `-p` is a password to mysql and a port
# to almost everything else, and there is no way to tell from the line which
# program is being invoked.
_CREDENTIAL_FLAG_NAMES = frozenset(
    {
        "access-token",
        "api-key",
        "apikey",
        "auth-token",
        "client-secret",
        "pass",
        "passphrase",
        "passwd",
        "password",
        "psk",
        "secret",
        "secret-key",
        "token",
        "wireless-key",
        "wpa-psk",
    }
)

# PAM's four management groups open every rule in `/etc/pam.d/*`, and one of
# them is spelled exactly `password` -- so `password required pam_unix.so` has
# the whole-line directive shape without being a credential. Found by running
# this module over the whole of /etc: eight files on a stock macOS host lost
# the line that says which module authenticates password changes.
#
# The tell is the second field, which in a PAM rule is a control word or a
# bracketed control expression. A credential that happens to be exactly the
# word `sufficient` is not a trade worth worrying about.
_PAM_CONTROL_WORDS = frozenset(
    {"include", "optional", "required", "requisite", "substack", "sufficient"}
)

_SPACE_DIRECTIVE_RE = re.compile(r"^([ \t]*)([A-Za-z][A-Za-z0-9_.\-]*)([ \t]+)(\S.*)$")
# A credential flag, then whitespace, then its value.
#
# The names are compiled *into* the pattern rather than filtered afterwards.
# Matching any `-flag value` and then asking about the name let a
# non-credential flag consume the credential inside its own argument:
# `/bin/sh -c 'myd --password hunter2'` matched at `-c`, whose quoted value
# swallowed the whole command, so the scan resumed past the leak. With the
# vocabulary in the pattern the engine simply walks on to `--password`.
#
# `(?![A-Za-z0-9_.\-])` is what makes the name whole rather than a prefix, so
# `--pass-fd 3` cannot match on `pass`. `(?!--)` keeps `--password --verbose`
# from redacting the following flag. A bare value stops at whitespace, at `<`
# (so a value inside a plist `<string>` does not swallow the closing tag) and
# at a quote (which in the `sh -c '...'` case is the shell's string
# terminator, not part of the password).
_FLAG_VALUE_RE = re.compile(
    r"""(?<![^\s>"'])(-{1,2}(?:%s))(?![A-Za-z0-9_.\-])([ \t]+)"""
    r"""("[^"]*"|'[^']*'|(?!--)[^\s<'"]+)"""
    % "|".join(
        sorted((re.escape(n) for n in _CREDENTIAL_FLAG_NAMES), key=len, reverse=True)
    ),
    re.IGNORECASE,
)
_FLAG_TOKEN_RE = re.compile(r"^-{1,2}[A-Za-z]")
# `scheme://user:password@host`. The password runs to the `@`; scheme, user
# and host are kept so the mount or proxy stays legible.
URL_CREDENTIAL_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9+.\-]*://)([^\s:/@]+):([^\s/@]+)@"
)


def _placeholder_for(line: str) -> str:
    """`<secret>` reads as an element inside XML; plists get the text marker."""
    return PLIST_REDACTION if _PLIST_OPEN_RE.search(line) else SECRET


def _is_credential_flag(token: str) -> bool:
    return token.lstrip("-").lower() in _CREDENTIAL_FLAG_NAMES


def _redact_space_directive(line: str) -> str:
    """Redact `<keyword> <value>` where the keyword is the whole first token."""
    m = _SPACE_DIRECTIVE_RE.match(line)
    if not m or m.group(2).lower() not in _SPACE_DIRECTIVE_KEYWORDS:
        return line
    value = m.group(4)
    if value[:1] == "[" or value.split()[0].lower() in _PAM_CONTROL_WORDS:
        return line  # a PAM rule, not an assignment
    return m.group(1) + m.group(2) + m.group(3) + _placeholder_for(line)


def _redact_flag_values(line: str) -> str:
    """Redact the value of every `--credential-name VALUE` flag on the line.

    The value is one token, not the rest of the line: an argv carries other
    flags after it and `--user alice` must survive. The `=` spelling
    (`--password=x`) is already a `key<sep>value` pair and is owned by
    `_redact_inline`.
    """
    placeholder = _placeholder_for(line)
    return _FLAG_VALUE_RE.sub(
        lambda m: m.group(1) + m.group(2) + placeholder, line
    )


def _redact_url_credentials(text: str) -> str:
    """Redact the password inside every `scheme://user:pass@host` in `text`."""

    def sub(match: "re.Match[str]") -> str:
        whole = match.string
        start = whole.rfind("\n", 0, match.start()) + 1
        stop = whole.find("\n", match.end())
        line = whole[start:] if stop == -1 else whole[start:stop]
        return f"{match.group(1)}{match.group(2)}:{_placeholder_for(line)}@"

    return URL_CREDENTIAL_RE.sub(sub, text)


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
            if k > row and "<key>" in lines[k].lower():
                # The element was never closed and the next dictionary entry
                # has already begun, so the value cannot extend any further.
                # Without this bound the search ran on to some later
                # `</string>` and blanked every `<key>` in between, destroying
                # the record instead of just the credential.
                break
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


_PLIST_FLAG_RE = re.compile(
    r"<string>\s*(-{1,2}[A-Za-z][A-Za-z0-9_.\-]*)\s*</string>", re.IGNORECASE
)
_PLIST_STRING_RE = re.compile(r"<string>([^<]*)</string>", re.IGNORECASE)


def _handle_plist_argument_flag(lines: List[str], row: int) -> Optional[int]:
    """Redact the array member that follows a credential flag.

    launchd's `ProgramArguments` is a flat `<array>` of `<string>` elements,
    so `--token hunter2` arrives as two adjacent members and the credential
    has no `<key>` naming it. `_handle_plist_key` has nothing to match on and
    `_iter_pairs` finds no separator, so the value staged verbatim.

    The value is the next `<string>`, on this line or the one below -- argv
    arrays are written one member per line. A member that is itself a flag is
    left alone: `--token` immediately followed by `--verbose` has no value.
    """
    for m in _PLIST_FLAG_RE.finditer(lines[row]):
        if not _is_credential_flag(m.group(1)):
            continue
        k = row
        nxt = _PLIST_STRING_RE.search(lines[row], m.end())
        if nxt is None and row + 1 < len(lines):
            k = row + 1
            nxt = _PLIST_STRING_RE.search(lines[k])
        if nxt is None:
            continue
        value = nxt.group(1).strip()
        if not value or _FLAG_TOKEN_RE.match(value):
            continue
        lines[k] = lines[k][: nxt.start(1)] + PLIST_REDACTION + lines[k][nxt.end(1) :]
        return k
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
    handlers = (_handle_plist_key, _handle_plist_argument_flag, _handle_deferred_value)
    while i < len(lines):
        for handler in handlers:
            consumed = handler(lines, i)
            if consumed is not None:
                i = max(consumed, i)
                break
        else:
            # Inline pairs first: the shapes below have no separator, so a
            # line they match is one the pair scanner already declined.
            line = _redact_inline(lines[i])
            line = _redact_space_directive(line)
            lines[i] = _redact_flag_values(line)
        i += 1
    return "\n".join(line + eol for line, eol in zip(lines, endings))


def redact_text(text: str) -> str:
    # Must run first: TOKEN_RE would otherwise eat the `|` off `password: |`
    # and orphan the block body.
    text = redact_structured_values(text)
    text = TOKEN_RE.sub(_redact_token, text)
    text = HOME_RE.sub("/home/<user>", text)
    # Before EMAIL_RE: `bob:pass@proxy.example.com` reads as an email address
    # from `pass` onwards, so the email pass used to redact the credential by
    # accident and take the proxy host with it -- leaving
    # `http://bob:<email>:3128/`, which hides the leak and destroys the one
    # field that says where the proxy is.
    text = _redact_url_credentials(text)
    text = EMAIL_RE.sub("<email>", text)
    text = IPV4_RE.sub(lambda m: _redact_address(m, "<ip>"), text)
    text = MAC_RE.sub("<mac>", text)  # MAC before IPv6 (IPv6 pattern is greedy)
    text = IPV6_RE.sub(lambda m: _redact_address(m, "<ip6>"), text)
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
