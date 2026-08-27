# Scope Axes — Reconciliation

2026-08-27

Two designs were produced independently, on the same day, that partition the
same thing. Neither references the other. This document reconciles them before
either builds further.

> **Amended 2026-08-27 by the skills-design owner.** §7's questions are
> answered in **§8**, which also corrects two claims here that were checked
> against the live daemon and did not hold. **§2 recommends a destructive
> daemon migration to fix a bug that does not exist — do not run it.**

| | Role-scoped config harvesting | Role-scoped skills |
|---|---|---|
| Doc | `.handoff/ROLE-SCOPED-CONFIG-HARVESTING-DESIGN-2026-08-26.md` | `documentation/design/ROLE-SCOPED-SKILLS-2026-08-27.md` |
| Status | **Shipped** — merged `511dd5d` on `model-picker-frontend` | Design only |
| Scope names | `network_admin`, `service_admin`, `storage_admin` | `host-network`, `host-storage`, `host-security`, `host-services` |
| Path model | Stage a **second physical copy** into `host/<role>/` | **Masks** over the flat tree: `paths: ["host/etc/fstab", …]` |
| Routing | None — unreachable (see below) | `skills/matcher.py` → `composer.py` |
| Bridge | Scope name | `assigned_to_role` + `resolve_mask(role=)` |

The skills doc's header says *"Reviewed against implementation 2026-08-27 —
see §16 before building"*, but **the file contains no §16** — it ends at §15.
Whatever that review concluded is not in the document. That is worth
recovering before trusting the doc's "verified" claims, several of which are
load-bearing.

---

## 1. Where the skills design is right and the shipped code is wrong

**Adopt the skills design's path model.** It specifies scopes as *masks over
the flat host tree*:

```yaml
- id: host-storage
  paths: ["host/etc/fstab", "host/etc/zfs/", "host/etc/mdadm/"]
```

The shipped implementation instead stages a **second physical copy** into
`host/<role>/`. That is already recorded as a KNOWN LIMITATION in the
harvesting design: staging goes 42 → 99 files with 40 duplicated, and because
`remap_edges_for_unified_root` maps only to `host/`, `trace_expand` finds no
edges inside a role scope.

The harvesting doc listed two candidate fixes and deferred choosing without a
built index. **The skills design independently arrived at option (a).** That
is convergent evidence from two directions, and it settles the question:
role scopes should be path masks, not staged copies.

Migrating is not just a config edit — `stage_role_tree()` and its tests assume
the copy model, and the template's `paths` would change from `["host/network"]`
to an enumerated list derived from the manifest. But it removes the duplication
*and* restores `trace_expand` inside role scopes.

## 2. Where the shipped code is right and the skills design is wrong

> ⚠️ **This section is incorrect — verified against the live daemon, see §8.1.**
> Hyphenated ids in the *template* are correct and already working: the daemon
> stores them as `display_name` and derives its own underscored `id`. The
> proposed migration would orphan four indexed scopes to fix nothing. The
> conclusion that skills should *declare* underscored names still stands; the
> premise and the fix do not.

**Do not use hyphenated scope ids.** The skills design proposes
`host-storage`, `host-network`, `knowledge-linux` throughout — while its own
§5.3 correctly documents that *"if a query passes an unrecognized hyphenated
name, SourcePrep silently falls back to an unscoped global union."*

Its proposed names would therefore fail open, which is precisely the bug
already live in `sourceprep_template.yml` (registered `knowledge-linux`, router
requests `knowledge_linux` — see `.handoff/TODO-ROLE-SCOPED-CONFIG-2026-08-27.md`
§0b). §5.3 proposes `canonical_scope_id()` normalization as the mitigation,
which works, but the simpler fix is to not write hyphens in the first place.

The shipped `_admin` scopes are already underscored.

## 3. Naming — proposal

Two schemes for one concept. Rather than rename shipped-and-indexed scopes,
keep the scope id and let `assigned_to_role` carry the skill-facing name:

```yaml
- id: storage_admin           # scope identity — shipped, underscored, indexed
  paths: [...]                # masks over the flat tree (per §1)
  assigned_to_role: storage-ops   # skill identity — what the skill declares
  pipeline_profile: system_config
```

This works because the two names address different layers, and the daemon
already supports both: `resolve_mask()` accepts `role=` as a peer of `scope=`.
A skill declares `scope: storage-ops` (its role), the daemon resolves which
scope carries it, and the scope id never needs to match the skill name.

Constraint to respect, from the skills doc's daemon verification: **a role is
unique per project**, so one skill maps to at most one role-scope and two
skills cannot share a role. That rules out two skills sharing `storage_admin`.

## 4. The third axis, and what the axes actually are

Three axes now exist or are proposed:

1. **Platform** — `knowledge_linux`, `knowledge_macos`, `knowledge_bsd`,
   `knowledge_common`. Live (but see §0b of the TODO: currently failing open).
2. **Role over host config** — `*_admin`. Shipped, indexed, **unreachable at
   query time**.
3. **Skills** — a bundle of prompt + scope + safety + model tier + budget.
   Design only.

Axis 3 is not a peer of 1 and 2 — **it is the consumer of them.** A skill
selects a scope from axes 1 and 2. That is what makes the skills work the
routing layer the harvesting work lacks, and it resolves an open question in
the harvesting TODO (§0d item 4: "give the agent an explicit scope-by-name
tool"). Skills are a better answer than a raw tool, because they carry safety
and model tier along with the scope.

A fourth axis was under consideration — **knowledge-tier topic scopes**
(`kb_arch_wiki`, `kb_package_catalog`, …), recommended at ~12. That work should
**not** start until axes 1–3 are observable, for the reason in §5.

## 5. The shared prerequisite: nothing here is observable

> ⚠️ **Substantially out of date — see §8.2.** The daemon *does* report scope
> resolution (`applied_scope`, `scope_warning`); Halbert was discarding those
> fields, which is now fixed. `scope_mode="hard"` is live daemon-side and
> genuinely pre-filters — cross-platform leak probes that failed 4/4 on
> 2026-08-26 now pass. The section's *conclusion* — build observability first —
> was right, and that build is done.

Both designs assume a scope request either works or fails visibly. It does
neither.

- An unrecognized scope name returns **HTTP 200 with global-union results**,
  byte-identical to a correctly-scoped 200 (documented at
  `sourceprep_retrieval_backend.py:37-38`).
- `scope_mode` is **absent from the shipped branch entirely** — it exists only
  as an uncommitted edit. So scoping is a rank *boost*, not a filter.
- Nothing asserts that returned `source_path`s fall inside the requested scope.

Consequences for each design:

- The skills design's **§5.3 fallback chain** (`host_storage` → `host` →
  global) cannot work. It is specified to trigger when a scope is "absent", but
  an absent scope does not report absence — it silently returns union results
  that look like success. The chain needs a scope-existence check against the
  daemon's scope list, not an inference from the response.
- The harvesting design's **`file_backed_platforms` gate** is justified by "an
  empty mask under `scope_mode=hard` excludes everything rather than
  narrowing". With `scope_mode` unlanded, that justification is currently
  false. The decision still holds; the stated reason does not.
- Any measurement of whether scoping improves retrieval — including the
  knowledge-tier phase-1 disproof — is measuring a rank boost, not a filter.

**So the first build, for both workstreams, is the observability layer.** It is
not a nice-to-have: finding §0b went undetected precisely because nothing
checks, and every downstream decision depends on measurements that are
currently unsound.

## 6. Proposed build order

1. **Observability + correctness** (shared foundation, blocks both):
   assert returned paths match the requested scope; validate scope names
   against the daemon's list and fail loudly on unknown; retry unscoped on
   zero results and label it; land `scope_mode`; fix the hyphen/underscore
   mismatch and its daemon migration.
2. **Routing** — skills matcher/composer, which makes the `_admin` scopes
   reachable for the first time.
3. **Path-mask migration** — convert role scopes from staged copies to masks
   (§1), removing the duplication and restoring `trace_expand`.
4. **Knowledge-tier topic scopes** — only after 1–3, and only if phase-1
   measurement under a real hard filter shows precision gains.

## 7. Open questions for whoever owns the skills design

1. **Where is §16?** The header instructs a reader to consult it before
   building, and it is not in the file. Several "Verified 2026-08-27" claims
   (daemon-side `assigned_to_role`, role uniqueness, `resolve_mask(role=)`)
   presumably rest on it.
2. **Does `resolve_mask(role=)` fail closed on an unknown role?** The
   scope-name path demonstrably does not. If the role path fails open too, the
   `assigned_to_role` bridge inherits the same silent-widening bug.
3. **Multi-scope.** The design wants "union scopes" across composed skills, and
   correctly notes v1 must pick one. Confirmed independently: the client's
   `scope` parameter is `Optional[str]`, a single value. Composition of two
   skills with different scopes is not expressible today.
4. **Do the four proposed `host-*` scopes replace the three shipped `*_admin`
   scopes, or coexist?** They cover overlapping ground with different
   boundaries — the shipped set has no `security` role (deferred to wave 2),
   and the proposed set has no `boot`/`package`/`shell`. A single agreed list
   should exist before either grows.

---

## 8. Verified answers (skills-design owner, 2026-08-27)

All of the below was reproduced against the **live daemon** (`localhost:8400`,
standalone project `735a592e`) and SourcePrep's source at
`/Volumes/4TB-BAD/HumanAI/CoDRAG`.

### 8.1 The hyphen/underscore mismatch is not a bug — do not migrate

§2 and TODO §0b both conclude that `sourceprep_template.yml`'s hyphenated ids
mean *"every knowledge-scoped query has been returning full-corpus results."*
That is not what happens. The pipeline is deliberate and three-stage:

```
template `id: knowledge-linux`   →   daemon display_name "knowledge-linux"
                                 →   daemon id           "knowledge_linux"
scope_for_query() emits          →   "knowledge_linux"    ✓ matches the id
```

`resolve_mask()` looks up `scope_store.get(project_id, scope)` — **by id**, not
by display_name. Live scope listing:

| daemon `id` | `display_name` | `assigned_to_role` |
|---|---|---|
| `host` | `host` | null |
| `knowledge_linux` | `knowledge-linux` | null |
| `knowledge_macos` | `knowledge-macos` | null |
| `knowledge_bsd` | `knowledge-bsd` | null |
| `knowledge_common` | `knowledge-common` | null |

Direct probe: `scope=knowledge_macos` → `applied_scope: "knowledge_macos"`,
no warning, macOS-only results. A genuinely unknown scope (`host_storage`) →
`applied_scope: "global"` **plus** `scope_warning`. So the two cases are *not*
byte-identical, which §5 and §0b both assert.

§0b's evidence is the code comment at `sourceprep_retrieval_backend.py:37-38`.
That comment is accurate — *unrecognized* hyphenated names do fail open — but
`knowledge_linux` is the recognized id, so the inference doesn't follow. The
underlying issue was already fixed in `e479c61`, which is why the router emits
underscores.

**The proposed fix is actively harmful.** `_reconcile_scopes` keys on
`display_name`, so renaming the template ids would create four new scopes and
orphan the four that hold all 71,050 indexed chunks. The independent
`HANDOFF-SCOPE-FILTER-REVIEW-2026-08-26.md` reached the same warning from the
other direction (F4): *"the same trap that produced `e479c61` — don't 'align'
the scope ids."*

What survives from §2: **skills should declare underscored names**, because a
name a skill invents has no daemon-side display_name mapping to save it.

### 8.2 Observability exists daemon-side, and is now wired in Halbert

§5's premise — that a scope request "either works or fails visibly. It does
neither" — was half right. The daemon reports; Halbert wasn't reading.

The context response carries `applied_scope`, `applied_role`, and
`scope_warning`. `context/adapters.py` discarded all three. Now fixed:

- `SourcePrepRetrievalBackend.resolve_scope()` validates the requested scope
  against the daemon's real scope list **before** the request, and walks
  `host_storage → host → deliberate-unscoped`. This is exactly the
  "scope-existence check against the daemon's scope list, not an inference
  from the response" that §5 prescribes.
- `_check_applied_scope()` logs whenever `applied_scope` differs from what was
  asked, or a `scope_warning` comes back.
- It **fails open** (keeps the requested scope) when the scope list can't be
  read, so a daemon hiccup doesn't widen retrieval.

`scope_mode="hard"` is live daemon-side and genuinely pre-filters. The F3 leak
probes from `HANDOFF-SCOPE-FILTER-REVIEW` now pass:

| probe | scope | 2026-08-26 | 2026-08-27 |
|---|---|---|---|
| `homebrew brew install cask` | `knowledge_linux` | leaked `homebrew_18.md` | linux-only ✓ |
| `pacman install package arch` | `knowledge_macos` | leaked `arch_wiki_13.md` | macos-only ✓ |

F1 (LOD file-head substitution) and F2 (empty host scope) are also resolved:
`scope=host` now returns `host/etc/ssh/sshd_config` chunks **with** `text`, and
compression genuinely compresses (4451 → 3730 chars).

### 8.3 Answers to §7

**Q1 — Where is §16?** It exists now. `23c3c33` snapshotted the file mid-edit:
the header was written before §16 was appended. §16 has eight subsections and
carries the daemon verification behind the "Verified 2026-08-27" claims.

**Q2 — Does `resolve_mask(role=)` fail closed on an unknown role?**
**No — and it is worse than the scope path.** Probed live with an unassigned
`role=storage-ops`:

```
applied_scope : "global"        ← silently widened
applied_role  : "storage-ops"   ← echoed back as though honoured
scope_warning : null            ← no warning at all
chunks        : FreeBSD handbook, for a ZFS query, on a macOS host
```

The scope path at least sets `scope_warning`; the role path sets nothing. So
the §3 bridge cannot send `role=` over the wire as designed.

**Resolution:** Halbert never sends `role=`. `resolve_role()` maps role → scope
id locally against `assigned_to_role` in the scope list, then routes through
the hardened scope path. An unassigned role returns None and the caller falls
back to its own scope rather than querying by role. The §3 design is otherwise
adopted intact — scope ids and skill names stay decoupled.

**Q3 — Multi-scope.** Confirmed: `scope` is `Optional[str]`, single-valued.
v1 picks the highest-priority skill's scope, per the skills design §4.2.

**Q4 — Do `host-*` replace or coexist with `*_admin`?** **Replace**, with the
shipped names kept. Per §3 the scope id is `storage_admin` (shipped, indexed,
underscored) and `assigned_to_role: storage-ops` carries the skill name. The
skills design's `host-storage`/`host-network`/`host-services` are the *same
partitions* under different names, so adopting them as new ids would duplicate
indexed scopes for no gain. Agreed single list, to be maintained here:

| scope id (daemon) | role (skill) | status |
|---|---|---|
| `storage_admin` | `storage-ops` | shipped, needs role assigned |
| `network_admin` | `network-ops` | shipped, needs role assigned |
| `service_admin` | `service-ops` | shipped, needs role assigned |
| `security_admin` | `security-ops` | not built — wave 2 |
| `config_admin` | `config-ops` | not built — wave 2 |

`boot`/`package`/`shell` from the skills design are deferred; `security` was
deferred by the harvesting design and is the most-requested gap. Role
uniqueness (§3) means each row is 1:1 and no two skills may share a role.

### 8.4 Where this leaves the build order

§6 item 1 is **done** for the observability half (see §8.2) and its
hyphen/underscore item should be **dropped**, not done (§8.1). What remains:

1. ~~Observability + correctness~~ — done. `scope_mode` still needs committing
   from the dirty checkout (TODO §0c).
2. **Routing** — unchanged and now the critical path. TODO §0a is exact:
   `scope_for_query` can only return `None`/`host`/`knowledge_*`, so the three
   `*_admin` scopes are indexed and dead. The skills matcher is what reaches
   them. This is skills Phase 1 + 2.
3. **Assign roles** — set `assigned_to_role` on the three shipped scopes
   (§8.3 Q4 table). Small, and it activates `resolve_role()`.
4. **Path-mask migration** — unchanged (§1). Independent of routing; can run in
   parallel.
5. **Knowledge-tier topic scopes** — unchanged; still gated on 1–4.

Agreed with §4: skills are the consumer of the platform and role axes, not a
peer of them.
