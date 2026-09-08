# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
AppleScript / JXA safety classifier (A2).

AppleScript can do anything on this machine: Finder deletes and moves to
trash, Mail sends real email, ``do shell script`` runs arbitrary shell
code as the user. This module classifies a script by risk level BEFORE
the executor spawns ``osascript``, feeding the existing
ToolSafetyFramework / confirmation-gating flow (tools/safety.py,
tools/executor.py): SAFE auto-executes, MEDIUM executes with a warning,
HIGH requires explicit confirmation, CRITICAL is blocked outright.

THE DEFAULT IS HIGH (founder ruling, 2026-09). The plan's original text
said "default to MEDIUM for anything that doesn't match a known-safe
pattern"; the founder overruled that: an unclassified script classifies
HIGH and waits for confirmation. Only statements that positively match a
read-only pattern (``get``, ``count``, ``exists``, ``name of`` and
friends) with no risky token anywhere in them may classify SAFE and
auto-execute.

``do shell script`` is an escape hatch that bypasses AppleScript safety
entirely: it classifies HIGH at minimum, and CRITICAL (blocked outright)
when its payload contains a destructive shell token (``rm``, ``sudo``,
``dd``, ``diskutil``, ``mkfs``, ``shred``, power verbs, redirects to a
device).

Honest limits of a pattern classifier. AppleScript is Turing-complete
and this is regex over its text, not a semantics pass:

* Computed targets and payloads defeat it. ``set cmd to "rm" & " -rf /"``
  followed by ``do shell script cmd`` shows only an innocent
  ``do shell script`` — still HIGH, never SAFE, but the CRITICAL payload
  detection cannot see the composed ``rm``.
* Handler bodies are classified where they are written, but a script can
  load or run other scripts at runtime (``run script``, ``load script``,
  a compiled .scpt) whose text never passes through here. Those verbs
  are themselves unclassified and therefore HIGH.
* String literals are matched like code: ``get name of item "delete me"``
  classifies HIGH (fail closed) rather than trying to be clever about
  which ``delete`` is "real".
* A multi-statement block classifies at its highest-risk statement, but
  a ``repeat`` loop re-running a HIGH statement is still just one HIGH
  classification — it does not (and cannot) escalate by iteration count.

The HIGH default is the mitigation for all of these: the classifier can
be wrong in the dangerous direction only when a matched "known" pattern
is itself wrong, never merely because a script was clever.

JXA (``run_jxa``) is classified HIGH, ALWAYS. It is a full JavaScript
runtime with the ObjC bridge — no regex can vouch for it as read-only —
so it never auto-executes, whatever it says.

Fail-closed: if the classifier itself raises, the result is HIGH with a
classifier-error reason — never an auto-execute.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from .safety import RiskLevel, SafetyCheckResult, _RISK_ORDER

logger = logging.getLogger("halbert.tools.applescript_safety")

#: The two tools this classifier speaks for (both execute via osascript
#: in tools/applescript_tools.py). ToolSafetyFramework routes them here
#: instead of its unknown-tool MEDIUM default.
APPLESCRIPT_TOOLS = ("run_applescript", "run_jxa")


# ─────────────────────────────────────────────────────────────────────────────
# Statement text hygiene
# ─────────────────────────────────────────────────────────────────────────────

def _strip_comments(script: str) -> List[str]:
    """The script's lines with comments removed, quote-aware.

    ``-- …`` runs to end of line; ``(* … *)`` spans lines. Both are
    stripped only when they occur OUTSIDE a string literal — a ``--``
    inside ``"a--b"`` is text, and stripping there could hide executable
    code that follows on the same line (``set x to "a--" & do shell
    script …``), which would classify too LOW.
    """
    lines: List[str] = []
    in_block = False
    for raw in script.splitlines():
        out: List[str] = []
        in_str = False
        i, n = 0, len(raw)
        while i < n:
            ch = raw[i]
            if in_block:
                if raw.startswith("*)", i):
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue
            if in_str:
                out.append(ch)
                if ch == '"' and (i == 0 or raw[i - 1] != "\\"):
                    in_str = False
                i += 1
                continue
            if ch == '"':
                in_str = True
                out.append(ch)
                i += 1
                continue
            if raw.startswith("--", i):
                break  # the rest of the line is a comment
            if raw.startswith("(*", i):
                in_block = True
                i += 2
                continue
            out.append(ch)
            i += 1
        lines.append("".join(out))
    return lines


def _join_continuations(lines: List[str]) -> List[str]:
    """Join AppleScript continuation lines (a statement ending in ``¬``
    continues on the next line) so a verb split across two lines is
    still seen as one statement."""
    statements: List[str] = []
    buf = ""
    for line in lines:
        stripped = line.rstrip()
        if stripped.endswith("¬"):
            buf += stripped[:-1] + " "
            continue
        statements.append(buf + line)
        buf = ""
    if buf:
        statements.append(buf)
    return statements


def _split_statements(script: str) -> List[str]:
    """Comment-stripped, continuation-joined statement lines."""
    return _join_continuations(_strip_comments(script))


# ─────────────────────────────────────────────────────────────────────────────
# Structural parsing
# ─────────────────────────────────────────────────────────────────────────────

#: A ``tell`` line, block opener or one-liner. The application name (or
#: process / front-application target) is the context every statement
#: inside the block classifies under.
_TELL = re.compile(
    r'^tell\s+(?:'
    r'(?:application|app)\s+(?:id\s+)?"(?P<app>[^"]*)"'
    r'|current\s+application'
    r'|me'
    r'|(?P<other>process\s+"[^"]*"|front\s+application|script\s+"[^"]*")'
    r')\s*(?:to\s+(?P<body>.*))?$',
    re.I,
)

_END_TELL = re.compile(r"^end\s+tell$", re.I)

#: Purely structural lines (block openers/closers, handler definitions,
#: branch headers with no statement attached). A line is structural ONLY
#: if it carries no risky token — anything else classifies on its content.
_STRUCTURAL = re.compile(
    r'^(?:'
    r'end(?:\s+\w+)?'
    r'|try\b'
    r'|on\s+error\b.*'
    r'|on\s+\w+\s*\(.*'
    r'|to\s+\w+\s*\(.*'
    r'|using\s+terms\s+from\b.*'
    r'|with\s+(?:timeout|transaction)\b.*'
    r'|considering\b.*'
    r'|ignoring\b.*'
    r'|repeat\b.*'
    r'|if\b.*\bthen\s*$'
    r'|else(?:\s+if\b.*\bthen\s*)?$'
    r')$',
    re.I,
)

#: Statements that positively identify as read-only. Start-anchored, so a
#: read must BE the statement — and the caller additionally requires that
#: no risky token appears anywhere in it.
_SAFE_READ = re.compile(
    r'^(?:the\s+)?(?:get|count|exists|name\s+of|id\s+of|class\s+of|'
    r'properties\s+of|contents\s+of)\b',
    re.I,
)

_DO_SHELL = re.compile(r"\bdo\s+shell\s+script\b", re.I)

#: ``do shell script`` payload tokens that mean disk destruction,
#: recursive deletion, or privilege escalation. CRITICAL — never runs.
#: Conservative by design: these only ever apply INSIDE a `do shell
#: script` payload, so their words can never flip a SAFE read to
#: CRITICAL; plain `find`/`curl`/`wget` stay HIGH (only the destructive
#: combination escalates — see the tests).
_CRITICAL_SHELL_TOKENS = tuple(
    re.compile(p, re.I)
    for p in (
        r"\brm\b",
        r"\bsrm\b",
        r"\bsudo\b",
        r"\bdd\b",
        r"\bmkfs(?:\.\w+)?\b",
        r"\bdiskutil\b",
        r"\bshred\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bhalt\b",
        r"\bpoweroff\b",
        r">\s*/dev/",
        # find + -delete: as destructive as rm, and never legitimate in
        # an agent-generated payload; plain `find` is NOT in this list.
        r"\bfind\b[^\n]*\s-delete\b",
        # pipe-to-shell remote-code execution
        r"\b(?:curl|wget)\b[^\n]*\|\s*(?:ba|z|da|k)?sh\b",
    )
)

#: Statement rules, checked in order (first match wins; CRITICAL-able
#: rules sit above the generic ones they specialize). A rule's regex
#: searches anywhere in the statement text.
_STATEMENT_RULES: Tuple[Tuple[re.Pattern, RiskLevel, str, str], ...] = (
    (_DO_SHELL,
     RiskLevel.HIGH,
     "'do shell script' runs arbitrary shell commands",
     "applescript.do_shell_script"),
    (re.compile(r"\bempty\s+(?:the\s+)?trash\b", re.I),
     RiskLevel.HIGH,
     "Empties the Trash (permanent deletion)",
     "applescript.empty_trash"),
    (re.compile(r"\bdelete\b", re.I),
     RiskLevel.HIGH,
     "Deletes objects",
     "applescript.delete"),
    (re.compile(r"\bmove\b[^\n]*\btrash\b", re.I),
     RiskLevel.HIGH,
     "Moves items to the Trash",
     "applescript.move_to_trash"),
    (re.compile(r"\bsend\b", re.I),
     RiskLevel.HIGH,
     "Send command",
     "applescript.send"),
    (re.compile(r"\berase\b[^\n]*\b(?:disk|volume|drive)s?\b", re.I),
     RiskLevel.CRITICAL,
     "Erases a disk or volume",
     "applescript.erase_disk"),
    (re.compile(r"\berase\b", re.I),
     RiskLevel.HIGH,
     "Erase command",
     "applescript.erase"),
    (re.compile(r"\bkeystroke\b|\bkey\s+code\b", re.I),
     RiskLevel.HIGH,
     "Simulates keyboard input (System Events UI scripting)",
     "applescript.keystroke"),
    (re.compile(r"\bclick\b", re.I),
     RiskLevel.HIGH,
     "Clicks UI elements (System Events UI scripting)",
     "applescript.click"),
    (re.compile(r"\bmake\b", re.I),
     RiskLevel.MEDIUM,
     "Creates objects ('make')",
     "applescript.make"),
    (re.compile(r"\bset\b", re.I),
     RiskLevel.MEDIUM,
     "Sets properties or variables ('set')",
     "applescript.set"),
)

#: Every risky pattern — the guard a "known safe read" must survive.
_RISK_PATTERNS = tuple([_DO_SHELL] + [rule[0] for rule in _STATEMENT_RULES])


def _risky(text: str) -> bool:
    return any(p.search(text) for p in _RISK_PATTERNS)


def _explain(rule_name: str, reason: str, app: Optional[str]) -> str:
    """Fold the parsed target-application context into the reason."""
    if rule_name == "applescript.send":
        low = (app or "").lower()
        if "mail" in low:
            return "Sends real email via Mail"
        if any(word in low for word in ("message", "ichat", "text")):
            return f"Sends real messages{f' via {app}' if app else ''}"
        return "Send command"
    if rule_name in ("applescript.delete", "applescript.empty_trash",
                     "applescript.move_to_trash"):
        return f"{reason}{f' in {app}' if app else ''}"
    return reason


def _classify_statement(stmt: str, app: Optional[str]) -> Tuple[RiskLevel, str, str]:
    """One statement's (risk_level, reason, matched_rule)."""
    if _SAFE_READ.match(stmt) and not _risky(stmt):
        return (RiskLevel.SAFE,
                "Read-only query (get/count/exists)",
                "applescript.read")

    m = _DO_SHELL.search(stmt)
    if m:
        # The shell payload is everything after the verb on this
        # statement. A destructive token there is CRITICAL, always.
        payload = stmt[m.end():]
        for token_re in _CRITICAL_SHELL_TOKENS:
            hit = token_re.search(payload)
            if hit:
                token = hit.group(0).strip()
                return (RiskLevel.CRITICAL,
                        f"'do shell script' payload contains '{token}'",
                        "applescript.do_shell_script.critical")
        return (RiskLevel.HIGH,
                "'do shell script' runs arbitrary shell commands",
                "applescript.do_shell_script")

    for pattern, level, reason, rule_name in _STATEMENT_RULES:
        if pattern.search(stmt):
            return (level, _explain(rule_name, reason, app), rule_name)

    # Founder ruling: unclassified statements default HIGH — the script
    # waits for confirmation rather than executing on a shrug.
    return (RiskLevel.HIGH,
            "Unclassified statement — defaulting to HIGH (founder ruling)",
            "applescript.default_high")


def _result(level: RiskLevel, reason: str, matched_rule: str) -> SafetyCheckResult:
    return SafetyCheckResult(
        risk_level=level,
        allowed=level != RiskLevel.CRITICAL,
        requires_confirmation=level == RiskLevel.HIGH,
        reason=reason,
        matched_rule=matched_rule,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def classify_applescript(script: str, jxa: bool = False) -> SafetyCheckResult:
    """Classify an AppleScript (or JXA) script by risk level.

    SAFE only when every statement positively matches a read-only
    pattern; the block classifies at its highest-risk statement; the
    default for anything unclassified is HIGH (founder ruling); the
    classifier fails closed on its own errors.
    """
    try:
        if jxa:
            # A full JavaScript runtime with the ObjC bridge: no pattern
            # can vouch for it as read-only, so it always waits for
            # confirmation — never auto-executes.
            return _result(
                RiskLevel.HIGH,
                "JXA is a full JavaScript runtime with ObjC bridge access; "
                "it always requires confirmation",
                "applescript.jxa.always_high",
            )

        if not isinstance(script, str) or not script.strip():
            return _result(
                RiskLevel.HIGH,
                "Empty or unclassified script — defaulting to HIGH (founder ruling)",
                "applescript.default_high",
            )

        app_stack: List[Optional[str]] = []
        best: Optional[Tuple[int, RiskLevel, str, str]] = None
        for raw in _split_statements(script):
            stmt = raw.strip()
            if not stmt:
                continue

            m = _TELL.match(stmt)
            if m is not None:
                app = m.group("app") or m.group("other")
                body = m.group("body")
                if body is None:
                    # A tell BLOCK opener: statements inside inherit this
                    # application as their context.
                    app_stack.append(app)
                    continue
                # A one-line `tell … to <statement>`: classify the body
                # under this application's context.
            else:
                if _END_TELL.match(stmt):
                    if app_stack:
                        app_stack.pop()
                    continue
                if _STRUCTURAL.match(stmt) and not _risky(stmt):
                    continue
                app = app_stack[-1] if app_stack else None
                body = stmt

            level, reason, rule_name = _classify_statement(body, app)
            order = _RISK_ORDER[level.value]
            if best is None or order > best[0]:
                best = (order, level, reason, rule_name)

        if best is None:
            return _result(
                RiskLevel.HIGH,
                "No executable statement found — defaulting to HIGH (founder ruling)",
                "applescript.default_high",
            )
        return _result(best[1], best[2], best[3])

    except Exception as e:
        logger.warning("AppleScript classifier failed (fail-closed HIGH): %s", e)
        return _result(
            RiskLevel.HIGH,
            f"Classifier error ({e}); failing closed to HIGH",
            "applescript.classifier_error",
        )


def classify_applescript_tool(tool_name: str, args: Dict) -> SafetyCheckResult:
    """Classify a run_applescript / run_jxa tool call for the safety
    framework. A missing or non-string script fails closed to HIGH (the
    handler refuses it anyway; nothing executes either way)."""
    script = args.get("script") if isinstance(args, dict) else None
    if not isinstance(script, str):
        script = ""
    return classify_applescript(script, jxa=(tool_name == "run_jxa"))