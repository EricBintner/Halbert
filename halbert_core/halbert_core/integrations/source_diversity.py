# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
Per-Source-Directory Diversity Cap

Retrieval *policy*, not transport: pure ranking functions over an already
-retrieved chunk list. No HTTP, no daemon, no I/O — unit-testable on synthetic
input.

WHY THIS EXISTS
---------------
The knowledge corpus is skewed by document count, not by chunk size.
``knowledge/linux/arch-wiki`` holds 2,331 documents and
``knowledge/macos/man-pages`` ~5,280, while the topic directories that usually
hold the precise answer (``webserver-docs``, ``backup-docs``, ``systemd-docs``,
``filesystem-docs``…) hold 10-70 each. The giants therefore out-populate the
candidate pool and win top-k on volume alone: six of the first six chunks on an
nginx query are arch-wiki, while ``webserver-docs`` — which has the answer —
appears once, further down.

The fix is a degenerate MMR over a categorical provenance feature: pull a
deeper candidate list than the caller wants, keep at most ``per_source`` chunks
per source directory in the daemon's own ranking order, then trim to the
requested count.

Measured against the live daemon over 15 probes — 10 whose answer lives in a
small directory, 5 controls where a giant source genuinely IS correct
(see documentation/design/KNOWLEDGE-SCOPE-REVISION-2026-08-27.md):

    baseline k=5                      6/10 small   3/5 controls   9/15
    raise max_chars alone             6/10 small   3/5 controls   9/15
    deep pull + cap 1 per directory   9/10 small   5/5 controls  14/15
    cap 2 per directory               8/10 small   5/5 controls  13/15
    blanket exclusion of the giants  10/10 small   1/5 controls  11/15

Blanket exclusion wins the small probes and destroys the controls — a
build-time exclusion cannot be undone by the caller, so when the user asks
about Homebrew the Homebrew corpus is simply gone. The cap is strictly more
robust: it keeps a giant's single best chunk when the giant is right.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, TypeVar

#: A retrieved chunk. Capping neither inspects nor rebuilds chunks beyond
#: reading their source path, so whatever goes in comes back out unchanged.
Chunk = TypeVar("Chunk")

#: Chunks per source directory kept by default. Measured optimum (14/15);
#: 2 and 3 both score 13/15.
DEFAULT_PER_SOURCE = 1

#: Candidates requested from the daemon before capping. Measured at 50; the
#: cap can only choose from what the candidate list contains, so a shallow
#: pull leaves it nothing to promote.
DEFAULT_PULL_K = 50


def source_directory(source_path: Any) -> Optional[str]:
    """The directory a chunk came from, or ``None`` when there isn't one.

    SourcePrep's ``source_path`` is a corpus-relative POSIX path:

        ``knowledge/linux/arch-wiki/arch_wiki_23.md`` -> ``knowledge/linux/arch-wiki``
        ``host/etc/ssh/sshd_config``                  -> ``host/etc/ssh``

    The key is the **full** parent directory, leading segment included. Two
    consequences are deliberate:

    * ``host/**`` (this machine's live config tree) keeps its ``host`` prefix,
      so it can never collide with a same-named knowledge directory, and its
      naturally narrow directories stay at their own granularity.
    * ``knowledge/linux/man-pages`` and ``knowledge/macos/man-pages`` stay
      distinct, because they are distinct corpora.

    Returning ``None`` rather than ``""`` for an unkeyable path is the point of
    this function's contract. A path with no directory component — empty,
    missing, a bare filename, a non-string — carries **no evidence** that the
    chunk shares a source with any other chunk. Bucketing them all under ``""``
    would let one malformed path collapse an entire result set to a single
    chunk. Callers must treat ``None`` as "unique, do not cap".
    """
    if not isinstance(source_path, str):
        return None
    # Normalise away leading/trailing and duplicated separators so that
    # "/etc/ssh/x", "etc/ssh/x" and "etc//ssh/x" agree on one key.
    cleaned = "/".join(segment for segment in source_path.strip().split("/") if segment)
    cut = cleaned.rfind("/")
    if cut < 1:
        return None
    return cleaned[:cut]


def cap_by_source_directory(
    chunks: Iterable[Chunk],
    limit: int,
    *,
    per_source: int = DEFAULT_PER_SOURCE,
    backfill: bool = True,
    path_key: str = "source_path",
) -> List[Chunk]:
    """Keep at most *per_source* chunks per source directory, then trim to *limit*.

    The daemon's ranking is authoritative and is never re-sorted: chunks are
    consumed in the order given, the first *per_source* seen for a directory
    are kept, later ones spill.

    Args:
        chunks: Ranked chunks, best first. Any iterable; entries are expected
            to be mappings with a *path_key*, but anything else is passed
            through uncapped rather than dropped.
        limit: Maximum chunks to return. ``<= 0`` returns ``[]``.
        per_source: Chunks kept per directory. ``<= 0`` disables capping
            entirely and just truncates to *limit* — the exact pre-cap
            behaviour, so measurement can A/B against it.
        backfill: When the capped set is short of *limit*, top it up from the
            spilled chunks in rank order. This only engages when the candidate
            list holds fewer than *limit* distinct directories, i.e. when there
            is genuinely nothing else to show; returning more of the only
            source that matched beats under-delivering. Backfilled chunks are
            appended **after** the diverse ones.
        path_key: Mapping key holding the source path.

    Returns:
        A new list; neither the input list nor any chunk is mutated.
    """
    if limit <= 0:
        return []

    if per_source <= 0:
        out: List[Chunk] = []
        for chunk in chunks:
            out.append(chunk)
            if len(out) >= limit:
                break
        return out

    kept: List[Chunk] = []
    spilled: List[Chunk] = []
    seen: Dict[str, int] = {}

    for chunk in chunks:
        raw = chunk.get(path_key) if isinstance(chunk, dict) else None
        directory = source_directory(raw)

        if directory is None:
            # No evidence of a shared source — always unique, never capped.
            kept.append(chunk)
            continue

        if seen.get(directory, 0) < per_source:
            seen[directory] = seen.get(directory, 0) + 1
            kept.append(chunk)
        else:
            spilled.append(chunk)

    if backfill and len(kept) < limit and spilled:
        kept.extend(spilled[: limit - len(kept)])

    return kept[:limit]
