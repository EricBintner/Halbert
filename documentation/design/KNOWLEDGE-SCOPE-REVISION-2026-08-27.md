# Knowledge Scopes — Plan Cancelled, Replaced by a Per-Source Cap

2026-08-27 · supersedes `KNOWLEDGE-SCOPE-MEASUREMENT-2026-08-27.md`

The four-scope containment plan is **cancelled, not deferred**. A client-side
per-source cap beats it on measurement, costs ~15 lines, needs no scopes, no
daemon writes, and no rebuild.

All numbers measured against the live daemon (`127.0.0.1:8400`, project
`735a592e…`, ~71k chunks). Read-only.

---

## The measurement that settles it

Fifteen probes. Ten whose correct answer lives in a **small** source directory;
five **controls** where a giant source genuinely *is* the right answer
(`pacman install`, `brew install cask`, `launchctl load plist`, `tar extract`,
`arch linux network configuration`). Any intervention that helps the first ten
by wrecking the last five is not an improvement.

| intervention | small (10) | controls (5) | **combined (15)** |
|---|---|---|---|
| baseline (`k=5`, default `max_chars`) | 6 | 3 | 9 |
| `max_chars` 12k → 60k alone | 6 | 3 | 9 |
| **per-source cap n=1 over a deep pull** | 9 | **5** | **14** |
| per-source cap n=2 | 8 | 5 | 13 |
| per-source cap n=3 | 8 | 5 | 13 |
| **blanket exclusion (the four-scope plan)** | **10** | **1** | 11 |

The four-scope plan is the *best* on small-cluster probes and the *worst*
overall. It scores 1/5 on the controls because a build-time exclusion cannot be
undone by the caller: when the user asks about Homebrew, the Homebrew corpus is
gone.

**Per-source cap n=1 is the winner** — 9/10 small, 5/5 controls, no regression
anywhere.

## Why scopes cannot win here

A scope is **candidate removal plus a constant score offset**. Verified
directly: comparing unscoped against `scope=knowledge_linux, scope_mode=hard`,
every shared chunk moved by the same `+0.10166` (one query showed a second
delta of `+0.116548`; the effect is overwhelmingly uniform), and intra-scope
rank order was preserved.

A scope therefore does **not** re-rank, does not change IDF, and does not
change `avgdl`. It does exactly what `exclude_paths` does — and
`exclude_paths` is already a **per-request** parameter. Four build-time scopes
are a more expensive, less flexible reimplementation of something the caller
can already vary per query.

This also refutes a plausible hypothesis from the literature review: that
global BM25 IDF/`avgdl` skew from the 42 MB man-pages and 17 MB arch-wiki was
the underlying mechanism, which would have argued *for* partitioning to get
separate term statistics. The flat constant delta shows partitioning buys no
such thing here.

## Corrections to the previous measurement doc

Two claims in `KNOWLEDGE-SCOPE-MEASUREMENT-2026-08-27.md` are wrong.

**1. "`max_chars` never binds" — WRONG.** It binds, and the default (12000) is
the binding value. Same query at `k=25`:

| `max_chars` | chunks |
|---|---|
| 12000 (default) | 9 |
| 60000 | 17 |
| 400000 | 17 |

The original test compared 12k against 120k **at `k=5`**, where `k` was the
limiting factor, and the conclusion was over-generalised to all `k`. Every
deep measurement in that document was silently truncated at 12k.

**2. "2 of 5 misses are coverage gaps" — WITHDRAWN.** A 40-probe sweep found
**zero** genuine corpus gaps; `webserver_docs_01.md` does return at `k=25`
unscoped. The original verdict was an artifact of scoring by intended
directory at a truncated depth. The real split is roughly **95% ranking, 5%
ingestion**. One genuine gap survives: **RHEL/Fedora** (`rpm -qa` appears in
zero files) and Debian depth — one ingestion ticket, ~15–25 MB, scheduled
*after* retrieval work, because ingestion value cannot be measured against a
broken ranker.

The one finding from that document that **stands**: arch-wiki dominates by
document count, not chunk size. Six of the first six chunks on a nginx query
are arch-wiki.

## Atlas: not a routing axis

`atlas_deep_dirs: ["knowledge"]` cannot do what it appears to. The grouping
function matches only the first path segment, so `"knowledge/linux"` can never
match — per-source segments would need an upstream code change, not config.
Its existing segments (`host`, `knowledge-linux/macos/common/bsd`) are the
platform axis rediscovered. It is descriptive, not addressable at the
granularity routing needs. Worth a 2-line upstream fix someday; irrelevant to
this work.

## The plan

**S0 — raise `max_chars`.** One default in `sourceprep_client.py`. Worth
nothing alone (9/15, unchanged) but it is the **prerequisite** for S1: the deep
pull needs the budget or the candidate list is truncated before the cap can
choose from it.

**S1 — deep pull plus per-source cap.** Retrieve at `k=50`, group returned
chunks by source directory (`source_path` → `knowledge/<platform>/<dir>`), keep
at most **1** per directory, return the top 5. ~15 lines, client-side, no
daemon changes.

This is the literature's per-source cap — a degenerate MMR over a categorical
provenance feature — and it is strictly more robust than exclusion: when a
giant *is* the right source it keeps its slot instead of losing everything.

**Not doing:** the four containment scopes, the 12-topic taxonomy, and any
build-time partitioning of the knowledge corpus. The router evidence alone
(best-in-class 43.7% vs a 60.8% oracle, against a corpus where 77% of documents
carry ≥2 topic labels) rules out fine-grained topic scopes permanently.

**Success criterion for S1:** combined hit rate ≥14/15 on the probe set above,
with **zero regression on the five giant-source controls**. If the cap
regresses the controls, do not fall back to scopes — that failure mode is
precisely what scopes make permanent.

## Two upstream bugs found along the way

Neither blocks this work; both are worth filing against CoDRAG.

1. **Per-file dedup is hardcoded.** `core/index.py:1425-1431` keeps only the
   highest-scoring chunk per file, unconditionally, after `search(k)`. It is
   currently the *only* source-balancing mechanism in the system — which is
   why lifting it would likely *raise* dominance, not lower it. Do not "fix"
   it without measuring.
2. **Chunk metadata mislabelling.** A journalctl chunk returned from
   `tldr_02.md` carried `section: "ausyscall"`. Worth a separate look at the
   lexical index and chunk labelling.
