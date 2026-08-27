# Knowledge-Tier Scopes — Phase 1 Measurement

2026-08-27

Measured against the **live daemon** (`127.0.0.1:8400`, project
`735a592e-a2da-499b-a614-854a5fc461f5`, 71k chunks indexed). Read-only —
no scopes were created, no build was triggered, nothing on the daemon was
modified.

A prior recommendation set a stop condition: *"If precision@5 doesn't move
materially, stop the program."* This is that test. **It did not stop.**

---

## Result

| | intended-cluster hit rate @ k=5 |
|---|---|
| unscoped (today) | **5/10 — 50%** |
| simulated giant-cluster quarantine | **8/10 — 80%** |
| delta | **+3 rescued, 0 lost** |

Ten probes, each a realistic sysadmin question whose correct answer lives in
a known *small* source directory. Simulation post-filters a `k=25` unscoped
query to remove the giant clusters, then takes the top 5 — approximating what
a hard scope pre-filter would return.

**Caveat on the simulation:** post-filtering is not identical to
`scope_mode="hard"`. The daemon pre-filters via `exclude_paths`, which changes
which candidates are retrieved at all and alters BM25 IDF statistics. The
direction and rough magnitude should hold; the exact number needs re-running
against real scopes.

## What is actually wrong, in order of size

### 1. arch-wiki dominates by document count — confirmed

At `k=25` on "nginx reverse proxy upstream block": **12 of 17 chunks were
arch-wiki**, against 1 for `linux/webserver-docs`, which is where the answer
lives. Across the 10-probe baseline, the two giant clusters took **14 of 28
filled slots (50%)**, arch-wiki alone 12.

This is a pure volume effect. arch-wiki holds 2,331 docs / 17 MB; the small
topic directories hold 10–70 docs each. It out-populates the candidate pool.

### 2. Two hypotheses tested and killed

Recording these so they are not re-litigated.

- **`max_chars` is not the binding constraint.** Same query at
  `max_chars=12000` and `max_chars=120000` both return 4 chunks / 5551 chars.
  The budget never binds.
- **arch-wiki chunks are not oversized.** Mean chunk length by cluster:
  arch-wiki 1249, freebsd-handbook 1602, webserver-docs 1396, man-pages 739,
  tldr 536. arch-wiki is mid-range. It is not eating the character budget —
  it is simply present more often.

Also: **`min_score` is not pruning.** At `k=5`, floors of `0.15` and `0.0`
both fill 28 of 50 slots. The under-delivery is `k` itself returning ~80% of
what is asked (17 chunks at `k=25`), not the score floor.

### 3. About 40% of misses are coverage gaps that no scope can fix

Each miss was re-asked at `k=25` with the floor removed, to see whether the
intended content exists anywhere in the ranking:

| probe | verdict |
|---|---|
| restic forget/prune | RANKING — exists at rank 6 |
| nginx reverse proxy | RANKING — exists at rank 8 |
| btrfs subvolume snapshot | RANKING — exists at rank 7 |
| nftables inet filter | **COVERAGE — absent at any depth** |
| journalctl --unit --since | **COVERAGE — absent at any depth** |

**3 of 5 are ranking problems, which scoping rescues. 2 of 5 are coverage
problems, which it cannot.** The simulation rescued exactly the three ranking
cases and left the two coverage cases missing — behaving precisely as the
diagnosis predicts.

That is the honest ceiling on this program: scoping takes the hit rate from
50% to 80%, and the remaining 20% needs *corpus work* — nftables and
journalctl documentation are simply not in the index.

---

## The design consequence: quarantine the giants, don't finely slice the rest

The measured win comes from **excluding a handful of huge clusters**, not from
partitioning the corpus into many topics. The simulation quarantined five
directories — `linux/arch-wiki`, `macos/man-pages`, `macos/homebrew`,
`common/tldr`, `linux/tldr` — and that alone produced the entire +30 points.

This is a materially cheaper intervention than the 12 topic scopes previously
recommended, and it inverts the framing:

- **Previously assumed:** build many narrow topic scopes so a query can target
  one precisely.
- **What the data supports:** build a few scopes that *hold the giants*, so
  everything else is no longer drowned by them.

The giants are also the easiest scopes to define — they are whole source
directories, addressable by path prefix with **zero ingestion work**. The fine
topic slicing that would require re-emitting markdown grouped by topic (over a
corpus where 77% of documents carry ≥2 topic labels) buys the remaining margin
at much higher cost, and should not be attempted until this cheaper change is
measured in place.

### Proposed Phase 1 scopes

Four scopes, all pure path prefixes over the existing tree:

| scope | paths | docs / size |
|---|---|---|
| `kb_arch_wiki` | `knowledge/linux/arch-wiki`, `knowledge/linux/arch-wiki-ext` | 2,331 / 18 MB |
| `kb_macos_manuals` | `knowledge/macos/man-pages` | ~5,280 / 42 MB |
| `kb_package_catalog` | `knowledge/macos/homebrew` | ~8,566 / 4 MB |
| `kb_cli_quickref` | `knowledge/common/tldr`, `knowledge/linux/tldr` | ~7,049 / 5 MB |

Together these hold the great majority of documents. Their purpose is
**containment first, targeting second**: a query that is genuinely about
Homebrew or a man page can target them, and every other query stops competing
with them.

The complementary piece — a default scope covering everything *except* these —
depends on whether the daemon supports exclusion-shaped scopes or only
inclusion. Verify before designing around it.

---

## What to do next

1. **Create the four scopes on the daemon and re-run this measurement against
   real `scope_mode="hard"`**, not a post-filter simulation. The simulation's
   +30 is directionally sound but not the number to quote.
2. **Do not build the 12-topic taxonomy yet.** It is not disproved, but the
   cheap intervention has not been measured in place, and the expensive one
   should not be authorised on a simulation.
3. **Treat the coverage gaps as separate work.** nftables and journalctl are
   missing from the index entirely. That is an ingestion problem, and no scope
   design addresses it — but it is 20 of the 50 points on the table here.
4. **Re-run with more probes.** Ten is enough to see a 30-point effect and not
   enough to size it precisely. The existing `scripts/corpus_quality_gate.py`
   harness is the natural home.

## Reproducing

The three probe scripts used are in this session's scratchpad, not committed:
baseline occupancy, ranking-vs-coverage diagnosis, and quarantine simulation.
All are read-only against the live daemon and take a few minutes each. Their
logic is small enough to re-derive from the tables above; the important part is
the method — **probe with questions whose answers you know the location of**,
then check whether the location survives top-k.
