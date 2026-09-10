# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The load-time content scanner (A13-G5, SK-5, design §4.1).

A skill body is not data. It is folded into ``messages[0]`` as Halbert's
own instructions, above the cache boundary, on both LLM calls of a turn.
The loader checked the frontmatter's shape, the file's byte size, its
encoding and its symlink containment -- and then loaded whatever prose was
underneath, unread.

The origin scans markdown bodies, not just code, for exactly that reason
(OpenClaw ``src/skills/security/scanner.ts``: "content scanning for
prompt-injection phrasing in markdown bodies ... not just code for
malware"). This is that rule set plus Halbert's own control-tag surface,
which the origin has no equivalent of.

**Posture, from the design, and it is not a judgement call:** bundled
skills that trip the scanner FAIL CI (there is a test); user, workspace and
pack skills that trip it are REFUSED with the finding logged, *not*
scrubbed -- "silently rewriting an instruction file is how you get
instruction files you can't audit". Composition-time defanging stays on
regardless; this is the layer that decides whether the file loads at all.

**Two severities, and the line between them is not squeamishness.** A rule
fires either because the text is trying to SPEAK AS the daemon or ship data
off the machine -- injection phrasing, a forged system block, a control tag,
a fetch piped to a shell, credentials into a network call -- or because it
MENTIONS a dangerous practice. The first class is an attack on the boundary
and refuses the file. The second is content a legitimate runbook quotes,
often in order to forbid it: the bundled ``security-ops`` skill says "Never
widen permissions as a diagnostic step. `chmod 777` is not a test", and a
scanner that took that off the machine would be deleting the advice for
containing the string it warns about. Those are logged for review and load.
Nothing in the second class can act on its own anyway -- every command still
goes through the executor's approval chain.

Every rule is a literal-ish regex over the text. There is no model here and
there must never be one: a scanner that asks a model whether text is an
injection is a scanner an injection can talk to.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Pattern, Tuple

logger = logging.getLogger("halbert.skills.scanner")

__all__ = [
    "ContentFinding",
    "MAX_EXCERPT_CHARS",
    "REFUSING_RULES",
    "RULES",
    "refusing_findings",
    "scan_skill_body",
    "scan_skill_file",
    "scan_skill_tree",
]

#: A finding quotes the line it fired on. Bounded, because the line may be
#: the 128 KiB the file cap allows minus a newline.
MAX_EXCERPT_CHARS = 200


@dataclass(frozen=True)
class ContentFinding:
    """One rule, one line, and enough of the text to judge it by."""

    rule: str
    line: int
    excerpt: str
    path: Optional[str] = None

    @property
    def refuses(self) -> bool:
        """Whether this finding stops the file loading (see the module
        docstring: speaking as the daemon, or shipping data off it)."""
        return self.rule in REFUSING_RULES

    def __str__(self) -> str:
        where = f"{self.path}:" if self.path else ""
        return f"{where}{self.line}: {self.rule}: {self.excerpt}"


def _re(pattern: str) -> Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


#: ``(rule, pattern)``, in report order. Named for what an operator reading
#: a log line needs to understand, not for the regex.
RULES: Tuple[Tuple[str, Pattern[str]], ...] = (
    # The classic opener, and its three common spellings. \s+ between the
    # words: a body that writes them across a line break is the same
    # sentence to a reader and to the model.
    ("prompt-injection-override", _re(
        r"\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+|everything\s+)?"
        r"(?:you\s+were\s+told\s+)?"
        r"(?:previous|prior|preceding|earlier|above|before)\b"
        r"|\bignore\s+(?:all\s+)?(?:previous\s+)?instructions?\b"
        r"|\bforget\s+everything\b")),
    # Role reassignment: "you are now", "from now on you are", "act as ...
    # with no restrictions".
    ("prompt-injection-role", _re(
        r"\byou\s+are\s+now\s+(?:an?|the)\b"
        r"|\bfrom\s+now\s+on\s+you\s+are\b"
        r"|\bact\s+as\s+(?:the\s+|an?\s+)?[\w\s]{0,40}?"
        r"with\s+no\s+(?:rules|restrictions|limits)\b")),
    # A forged system/assistant block. The prompt has real ones.
    #
    # ``user`` is deliberately NOT in this list: ``<user>`` is ordinary
    # placeholder prose in a runbook (the bundled home-ops skill writes
    # ``sensor.<user>_room``) and it is not a tag Halbert's prompt uses --
    # the roles live in the messages array, not in the text.
    ("prompt-injection-system", _re(
        r"</?\s*(?:system|assistant)\s*>"
        r"|^\s*(?:system|assistant)\s*:\s*you\b")),
    # Halbert's own control-tag surface: continuity is the transcript
    # block's delimiter, and speech/text/modality_context are the modality
    # directives. A skill that writes one is speaking AS the daemon.
    ("control-tag", _re(
        r"</?\s*(?:continuity|speech|text|modality_context)\s*>")),
    # Do it without asking. The approval chain is the one thing a skill
    # must never be able to talk its way past.
    ("prompt-injection-approval", _re(
        r"\bwithout\s+(?:asking|requesting|waiting\s+for)\s+"
        r"(?:for\s+)?(?:approval|permission|confirmation|consent)\b"
        r"|\b(?:do\s*n[o']?t|never)\s+ask\s+(?:the\s+)?"
        r"(?:user|operator|owner|him|her|them)?\s*"
        r"(?:for\s+)?(?:approval|permission|confirmation)\b"
        r"|\bno\s+need\s+to\s+(?:ask|confirm)\b")),
    # curl|wget ... | sh. The origin's rule, verbatim in intent.
    ("shell-pipe-to-shell", _re(
        r"\b(?:curl|wget|fetch)\b[^\n|]{0,200}\|\s*(?:sudo\s+)?"
        r"(?:ba|z|k|da)?sh\b")),
    # Environment or key material into a network call.
    ("secret-exfiltration", _re(
        r"\b(?:curl|wget|nc|ncat)\b[^\n]{0,200}"
        r"(?:\$\(env\)|\benv\b|\$\{?[A-Z_]*(?:TOKEN|SECRET|KEY|PASSWORD)"
        r"|id_rsa|id_ed25519|\.aws/credentials)"
        r"|(?:\benv\b|id_rsa|id_ed25519|\.ssh/|\.aws/credentials)"
        r"[^\n]{0,200}\|\s*(?:curl|wget|nc|ncat)\b")),
    # rm -rf at a root: /, ~, $HOME, /*.
    # ``rm -rf`` whose TARGET is a root: /, /*, ~, ~/, $HOME. The target
    # must END there -- ``rm -rf /var/tmp/scratch`` is a scoped delete and
    # a scanner that cannot tell the two apart is a scanner people mute.
    # The terminator is "not a path character", so the pattern still fires
    # inside a markdown code span.
    ("destructive-delete", _re(
        r"\brm\s+(?:-[a-z]*[rf][a-z]*\s+)+"
        r"(?:/|/\*|~|~/|\$HOME|\$\{HOME\})(?![\w./~-])")),
    ("unsafe-permissions", _re(r"\bchmod\s+(?:-R\s+)?0?777\b")),
    # A blob in instruction position. Flagged for review rather than read:
    # the point is that nobody can tell what it says.
    ("opaque-blob", _re(r"[A-Za-z0-9+/=]{512,}")),
)

#: The rules that REFUSE the file, as against those that log it for
#: review. See the module docstring: an attack on the boundary versus a
#: runbook mentioning a dangerous practice.
REFUSING_RULES = frozenset({
    "prompt-injection-override",
    "prompt-injection-role",
    "prompt-injection-system",
    "prompt-injection-approval",
    "prompt-injection-hidden",
    "control-tag",
    "shell-pipe-to-shell",
    "secret-exfiltration",
})

#: HTML comments are invisible in a rendered README and fully present in a
#: prompt. A comment whose CONTENT trips a rule is its own finding, named
#: so the log says which half of the problem it is.
_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
_HIDDEN_RULES = {
    "prompt-injection-override", "prompt-injection-role",
    "prompt-injection-approval", "shell-pipe-to-shell",
    "secret-exfiltration", "destructive-delete",
}


def _excerpt(line: str) -> str:
    text = line.strip()
    if len(text) <= MAX_EXCERPT_CHARS:
        return text
    return text[: MAX_EXCERPT_CHARS - 1] + "…"


def scan_skill_body(text: str, *, path: Optional[str] = None) -> List[ContentFinding]:
    """Every rule this text trips, in line then rule order.

    One finding per (line, rule): a line that says the same thing twice is
    one problem, and a scanner that reports it twice teaches people to skim
    its output.
    """
    if not text:
        return []
    findings: List[ContentFinding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in RULES:
            if pattern.search(line):
                findings.append(ContentFinding(rule, number, _excerpt(line), path))

    # The hidden half. Scanned over the whole text because a comment spans
    # lines; reported at the line the comment opens on.
    for match in _COMMENT_RE.finditer(text):
        inner = match.group(1)
        for rule, pattern in RULES:
            if rule in _HIDDEN_RULES and pattern.search(inner):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(ContentFinding(
                    "prompt-injection-hidden", line, _excerpt(inner), path))
                break
    return findings


def scan_skill_file(path: Path) -> List[ContentFinding]:
    """Scan one file's text; an unreadable file scans clean.

    Unreadable is the loader's problem and it already refuses those -- a
    scanner that raised here would turn "cannot read" into "cannot load
    ANY skill", which is A13-G1 again.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_skill_body(text, path=str(path))


def scan_skill_tree(skill_file: Path) -> List[ContentFinding]:
    """The skill's own file plus every ``references/*.md`` beside it.

    Design §4.1 names the references explicitly, and it is right to: the
    body's whole job is often to tell the model to go read one.
    """
    skill_file = Path(skill_file)
    findings = scan_skill_file(skill_file)
    references = skill_file.parent / "references"
    if references.is_dir():
        try:
            entries = sorted(references.rglob("*.md"))
        except OSError:
            entries = []
        for reference in entries:
            findings.extend(scan_skill_file(reference))
    return findings


def refusing_findings(findings) -> List[ContentFinding]:
    """The subset that stops a file loading."""
    return [f for f in findings if f.refuses]
