# RQ-B Scrutiny — Reverse-Engineering the Predicate Extensibility Findings

**Created:** 2026-08-22
**Purpose:** Scrutinize the RQ-B findings in `DEEP-RESEARCH-QUESTIONS-2026-08-22.md` (lines 359-542) by re-verifying every claim against the actual code. Document what holds, what is imprecise, and what was missed.

---

## Methodology

Each claim from the original RQ-B findings was traced back to the source code it depends on. The scrutiny checked:
1. Does the code actually say what the findings claim?
2. Are there edge cases, coupling points, or failure modes the findings overlooked?
3. Is the implementation path (§8) sound given the real code structure?

---

## Claims that HOLD (verified correct)

### H1. The ledger (TemporalStateLedger) is schema-free

**Claim:** `record()` accepts any string for subject/predicate/object. No enum, no validation.
**Verification:** `temporal_graph.py` lines 101-140. The `record()` method takes `persona_id, subject, predicate, object, source, confidence, priority` as parameters. The SQL INSERT uses `?` placeholders with no validation on subject/predicate/object values. The only constrained field is `priority` (defaults to "medium", ranked by `PRIORITY_RANK` dict, but unknown values fall back to rank 3 via `.get(t.priority, 3)`).
**Verdict:** CORRECT.

### H2. The cognitive tick never touches the ledger

**Claim:** `advance_turn()` operates on in-memory `PersonaCognition` and never reads from or writes to the state ledger.
**Verification:** `cognition_tick.py` lines 1-495. Imports: `.cognition`, `.beliefs`, `.belief_decay`, `.thought_triggers`, `.thought_generator`, `.thought_promoter`, `.interaction_engine`, `.event_bus`. No import of `temporal_graph`, `get_state_ledger`, or `continuity`. The function body operates on `cognition.drives`, `cognition.worries`, `cognition.emotional_state`, `cognition.beliefs`, `cognition.thoughts` — all in-memory objects.
**Verdict:** CORRECT.

### H3. The seam does not expose the ledger

**Claim:** `seam.py` has no `StateLedger` or `StateRenderer` protocol.
**Verification:** `seam.py` lines 1-169. Four protocols: `ModelBackend`, `RetrievalBackend`, `GovernancePolicy`, `AppSeam`. No state-related protocol. The ledger is accessed via direct import (`from haloysius.memory_v2.temporal_graph import get_state_ledger`).
**Verdict:** CORRECT.

### H4. continuity._advance() hardcodes clothing/location state machines

**Claim:** `_advance()` calls `update_clothing_from_message` and `update_location_from_message`, which are persona-shaped.
**Verification:** `continuity.py` lines 77-106. `_advance()` imports and calls both functions in try/except blocks. These parse chat text for clothing/location changes.
**Verdict:** CORRECT.

### H5. The medium and minimal renderer tiers handle all subjects generically

**Claim:** `_render_structured` (medium) and `_render_minimal` iterate all subjects in `grouped.values()`.
**Verification:** `state_renderer.py` lines 120-134. `_render_structured` iterates `grouped.values()` and renders each triple as `f"{_label(t.predicate)}: {t.object}"`. `_render_minimal` iterates `grouped.values()` and joins `t.object` values. Both iterate ALL subjects, not just persona/user/scene/world.
**Verdict:** CORRECT.

### H6. temporal_graph.py has only core dependencies

**Claim:** The ledger module is pure core.
**Verification:** `temporal_graph.py` imports: `logging`, `sqlite3`, `threading`, `dataclasses`, `datetime`, `typing` (all stdlib), and `haloysius.paths` (core). No app-side dependencies.
**Verdict:** CORRECT.

---

## Issues found (corrections needed)

### C1. CRITICAL — `_render_natural` silently drops unknown subjects

**Original claim (§1, Layer 2):** "All other predicates fall into an `other` bucket that renders as `f'{_label(t.predicate)}: {t.object}'` — the same generic fallback. So `disk_health` renders as 'Disk Health: sda: SMART warning' even in the natural tier."

**What the code actually does:** `state_renderer.py` lines 80-118. `_render_natural` has four `if` blocks:
```python
if "persona" in grouped:  # iterates grouped["persona"], unknown predicates -> "other" bucket
if "user" in grouped:     # renders grouped["user"]
if "scene" in grouped:    # renders grouped["scene"]
if "world" in grouped:    # renders grouped["world"]
```
**There is no `else` clause and no final loop over remaining subjects.** Subjects other than `persona`, `user`, `scene`, `world` are in the `grouped` dict (added by `_group_by_subject`) but are never iterated. They are **silently dropped** — not rendered at all.

**Impact on Halbert:** If Halbert uses subjects like `self`, `service:nginx`, `config`, `network`, `security`, `backup` (as proposed in §6), and the render tier is `xlarge` or `large` (natural), **all system-state triples would disappear from the prompt**. The LLM would see no system state at all.

**The "other" bucket only applies to unknown predicates WITHIN the `persona` subject** — it does not apply to unknown subjects. The original claim conflated "unknown predicates within persona" with "unknown subjects."

**Fix options (in priority order):**
1. **Use the medium tier (the default).** `DEFAULT_TIER = "medium"` in `continuity.py`. If Halbert calls `render_state_block("halbert")` without specifying a tier, it gets medium, which renders all subjects. This is the simplest fix — no code changes, just don't pass `tier="xlarge"`.
2. **Map Halbert's subjects to `persona` and `world`.** Since Halbert IS the persona ("I am the computer"), subject=`persona` is semantically correct for its own state (disk_health, thermal_state, etc.). External entities (services, network) use subject=`world`. Both render in the natural tier. Per-entity tracking requires unique predicates (e.g., `service_status_nginx` instead of `service_status` with subject `service:nginx`).
3. **Fix `_render_natural` to iterate all subjects** (core change). Add a final loop after the `world` block:
   ```python
   for subj, triples in grouped.items():
       if subj in ("persona", "user", "scene", "world"):
           continue
       facts = [f"{_label(t.predicate)}: {t.object}" for t in triples]
       parts.append(f"{subj.replace('_', ' ').title()}: " + ", ".join(facts) + ".")
   ```
   This is ~5 lines and makes the natural tier handle any subject.

**Recommendation:** Use option 1 (medium tier) for MVP. If natural-tier prose is needed later, apply option 3 (the 5-line fix). Option 2 works but constrains the subject schema to work around a renderer limitation, which is the wrong design driver.

**Severity:** CRITICAL for the natural tier. NON-ISSUE for the medium tier (the default).

---

### C2. MISLEADING — "memory_v2 has no predicate validation" conflates ledger with PersonaMemoryStore

**Original claim (§5 table):** "Does the memory store care about predicate shape? NO. The ledger is schema-free SQLite; memory_v2 has no predicate validation."

**What the code actually does:** The claim is correct for `TemporalStateLedger` (in `temporal_graph.py`), which is schema-free. But `memory_v2` also contains `PersonaMemoryStore` (in `store.py`), which has a `MemoryType` enum (`EPISODIC`, `SEMANTIC`, `TACIT`, `EMOTIONAL`, `THINKING`, `INVENTED`) — see `types.py` lines 37-57. `PersonaMemoryStore` is NOT schema-free; it enforces memory types.

**However:** `PersonaMemoryStore` is a DIFFERENT store from `TemporalStateLedger`. The ledger stores state triples (continuity predicates). PersonaMemoryStore stores semantic memories (episodic/semantic/emotional). RQ-B is about the continuity ledger, not PersonaMemoryStore. The claim is correct for the ledger but the mention of "memory_v2" broadly is imprecise.

**Correction:** The table row should read: "Does the **continuity ledger** care about predicate shape? NO. `TemporalStateLedger` is schema-free SQLite with no predicate validation. (Note: `PersonaMemoryStore` in the same `memory_v2` package has a `MemoryType` enum, but that is a separate store for semantic memories, not state predicates.)"

**Severity:** LOW (imprecise wording, not a factual error about the ledger itself).

---

### C3. OMISSION — Continuity functions are not called by any Haloysius code

**Original claim (§3, §8):** "Halbert calls `render_state_block('halbert')` during prompt assembly." Stated as if it's a straightforward integration.

**What the code actually does:** Grep for `render_state_block`, `advance_from_user_message`, `advance_from_response` across all of `src/haloysius/` returns matches ONLY in:
- `continuity.py` itself (the definitions)
- Test files (`test_clothing_state_machine.py`, `test_continuity_integration.py`)

**No Haloysius chat handler, conversation module, or API layer calls these functions.** They are a library API that the consuming app must wire in explicitly. Haloysius is a library, not an app — it has no chat handler.

**Impact:** Halbert's prompt assembly must explicitly call `render_state_block("halbert")` at the right point in the prompt assembly pipeline. There is no automatic integration where Haloysius "just works" — Halbert builds the call site. This is consistent with the §8 implementation path but should be stated explicitly so no one assumes automatic wiring.

**Severity:** LOW (the §8 path is correct, but the implicit assumption of automatic integration should be made explicit).

---

### C4. OMISSION — Packaging dependency on WP-12

**Original claim (§3):** "Direct import — `from haloysius.memory_v2.temporal_graph import get_state_ledger`. This works today, no core change."

**What the code actually says:** `context/__init__.py` lines 6-11:
```
Subtractive note: budget_manager and continuity are pure-stdlib and always
available from the core. budget_v2, state_renderer, and prompt_pipeline depend
on app-side modules (hardware, memory_v2) that are not part of the core wheel
yet; they are optional re-exports that degrade to None when those deps are
absent, so `import haloysius.context` succeeds in a thin install.
They migrate fully as WP-12/13/14 move hardware/memory_v2 into the core.
```

This means:
- **Today (full Haloysius install):** `from haloysius.memory_v2.temporal_graph import get_state_ledger` works. All modules are present.
- **After WP-12 (memory_v2 moved to `packages/core/`):** Works. memory_v2 is core.
- **Subtractive install before WP-12:** `memory_v2` may not be in the core wheel. The import could fail with `ModuleNotFoundError`.

**However:** `temporal_graph.py` itself only depends on `haloysius.paths` (core). The `context/__init__.py` comment groups `state_renderer` with `memory_v2` as "not part of the core wheel," but `state_renderer.py`'s only non-stdlib import is `from haloysius.memory_v2.temporal_graph import StateTriple, PRIORITY_RANK` — which chains to `haloysius.paths`. So the dependency is: `state_renderer → memory_v2.temporal_graph → haloysius.paths`. If `temporal_graph.py` is included in the core wheel, `state_renderer` works. The comment may be overly conservative (grouping all of `memory_v2` together when only `store.py` has heavy dependencies like sentence-transformers).

**Correction:** Add a note: "The consumer-side approach depends on `memory_v2.temporal_graph` being available. In the current full install, this works. After WP-12 moves `memory_v2` to `packages/core/`, it works in the subtractive install. Before WP-12, in a subtractive core-only install, the import may fail. Halbert should either use the full Haloysius install or wait for WP-12."

**Severity:** MEDIUM (timing dependency that affects when the approach can be used in a subtractive install, but not whether it works at all).

---

### C5. OMISSION — persona_id namespace collision risk

**Original claim (§6):** "Halbert's `persona_id` in the ledger will be `'halbert'` (or the user-renamed value)."

**What the code actually does:** The ledger is keyed by `persona_id` in every query (`WHERE persona_id=?`). If Halbert uses `persona_id="halbert"` and no Haloysius persona has that ID, no collision. But if the user renames Halbert to a name that matches a Haloysius persona (e.g., `"cera"` — a demo persona), their triples would coexist in the same `persona_id` namespace. `clear_persona("cera")` would delete both Halbert's system-state triples and the persona's clothing/location triples.

**Impact:** Low probability (requires the user to rename Halbert to a specific persona name), but high consequence (data loss for one or both). The risk is that `clear_persona()` is a destructive operation that doesn't distinguish between triple sources.

**Correction:** Add a note: "Halbert should use a persona_id that cannot collide with Haloysius persona names. Options: (a) prefix with `halbert:` (e.g., `halbert:default`), (b) use a separate ledger DB path (`get_state_ledger(db_path=...)`), (c) validate against loaded persona names at startup. Option (b) is the strongest isolation — a separate SQLite file eliminates all collision risk."

**Severity:** LOW (edge case, but the fix is simple — use a separate db_path).

---

### C6. OMISSION — Ledger DB sharing in the same process

**What the code does:** `get_state_ledger(db_path=None)` caches instances by `db_path` in `_ledger_instances` dict. The default key is `"_default"`. If Halbert and Haloysius personas run in the same process and both use the default db_path, they share the same SQLite file.

**Impact:** Different `persona_id` values don't collide in the schema (every query filters by `persona_id`). But the DB file is shared, which means:
- Concurrent writes are serialized by the ledger's `threading.Lock` (fine).
- `clear_persona()` for one persona_id doesn't affect others (fine).
- A single DB corruption event affects all personas (low risk with WAL mode).

**Correction:** This is acceptable for MVP. If isolation is desired, Halbert should pass a separate `db_path` to `get_state_ledger()`. This connects to C5 — a separate db_path solves both the sharing and collision concerns.

**Severity:** LOW (acceptable for MVP, simple fix if needed).

---

### C7. MINOR — Source field values not specified

**What the code does:** The `source` field in `StateTriple` is a free-form string identifying who wrote the triple. Existing writers use values like `"clothing_sm"`, `"emotional_state"`, `"location_sm"`.

**Impact:** Halbert's `SystemStateSync` should use consistent source strings for traceability (e.g., `"storage_scanner"`, `"config_drift_detector"`, `"thermal_scanner"`). The original findings mentioned source modules but didn't specify exact source strings.

**Severity:** TRIVIAL (implementation detail).

---

### C8. MINOR — invalidate() and get_history() not mentioned

**What the code does:** The ledger supports:
- `invalidate(persona_id, subject, predicate)` — closes the current value without recording a new one. Useful when a service is uninstalled or a disk is removed.
- `get_history(persona_id, subject, predicate)` — returns all values a predicate has held, oldest first. Useful for "when did this disk start failing?" queries.

**Impact:** These are useful capabilities for Halbert that the original findings didn't mention. `invalidate()` is needed for entity removal (service uninstalled, disk removed). `get_history()` enables temporal queries about system state changes.

**Severity:** TRIVIAL (omission of useful capabilities, not an error).

---

## Revised assessment

The original verdict — "consumer-side is feasible with ZERO core changes" — **holds for the medium tier (the default)**. The critical correction is that the natural tier (xlarge/large) silently drops unknown subjects, which the original findings missed. This doesn't invalidate the verdict because:

1. The default tier is "medium", which renders all subjects.
2. Halbert can explicitly pass `tier="medium"` to `render_state_block()`.
3. If natural-tier prose is needed, a 5-line fix to `_render_natural` (iterating remaining subjects) is the minimal core change.

The optional §7 enhancement (injectable renderer for first-person prose) becomes slightly more motivated: if Halbert wants natural-tier rendering with system-state prose, the renderer needs to handle unknown subjects anyway. The injectable renderer approach lets Halbert control this without modifying core's `_render_natural`.

### Corrected implementation path for Phase 4

1. **Halbert creates a `SystemStateSync` class** that reads from `DiscoveryEngine.get_all()` and config snapshot/drift, maps to predicates, and calls `get_state_ledger().record("halbert", subject, predicate, object, source, priority)`.
2. **Halbert calls `render_state_block("halbert", tier="medium")`** during prompt assembly. **Explicitly pass `tier="medium"`** to avoid the natural-tier subject-dropping issue. Or accept the default (which is already "medium").
3. **Halbert does NOT call** `continuity.advance_from_user_message()` or `advance_from_response()`.
4. **Use a dedicated `persona_id`** (e.g., `"halbert"`) that cannot collide with Haloysius persona names. For strongest isolation, pass a separate `db_path` to `get_state_ledger()`.
5. **Optional later:** implement a `StateRenderer` for first-person prose and register via the seam. This also solves the natural-tier subject-dropping issue if Halbert wants xlarge/large tier rendering.
6. **Packaging note:** ensure `memory_v2` is available (full install today, or after WP-12 moves it to core).

### Subject schema revision (addressing C1)

If using the medium tier (recommended), the original subject schema from §6 works as-is — all subjects render. If the natural tier is needed, map subjects to `persona` and `world`:

| Original subject | Natural-tier subject | Rationale |
|-----------------|---------------------|-----------|
| `self` | `persona` | Halbert IS the persona; its state is persona state |
| `service:nginx` | `world` + predicate `service_status_nginx` | Services are part of the world; unique predicates for per-entity tracking |
| `config` | `persona` | Config is Halbert's own physiology |
| `network` | `world` | Network is external infrastructure |
| `security` | `persona` (anomalies) / `world` (posture) | Security anomalies are self-state; posture is external |
| `backup` | `world` | Backups are external services |

This mapping is only needed if the natural tier is used. With the medium tier, the original schema works unchanged.

---

## Summary of corrections

| ID | Severity | Claim | Correction |
|----|----------|-------|------------|
| C1 | CRITICAL (natural tier only) | "Unknown predicates fall into an `other` bucket" in natural tier | Unknown SUBJECTS are silently dropped in `_render_natural`. Use medium tier (default) or fix the renderer. |
| C2 | LOW | "memory_v2 has no predicate validation" | True for `TemporalStateLedger`; `PersonaMemoryStore` has `MemoryType` enum but is a separate store. Clarify wording. |
| C3 | LOW | Implied automatic integration | Continuity functions are a library API; no Haloysius code calls them. Halbert must wire them explicitly. |
| C4 | MEDIUM | "This works today, no core change" | Works in full install. Subtractive install needs WP-12 to move `memory_v2` to core. |
| C5 | LOW | persona_id = "halbert" | Collision risk if user renames Halbert to a Haloysius persona name. Use separate db_path for isolation. |
| C6 | LOW | (not mentioned) | Ledger DB is shared by default. Acceptable for MVP; separate db_path for isolation. |
| C7 | TRIVIAL | (source strings not specified) | Specify consistent source strings (e.g., "storage_scanner"). |
| C8 | TRIVIAL | (invalidate/get_history not mentioned) | Useful capabilities for entity removal and temporal queries. |

**Bottom line:** The core verdict (consumer-side, zero core changes for MVP) holds. The critical correction is about the natural tier's subject-dropping behavior, which is avoided by using the default medium tier. The packaging timing dependency (C4) is the only item that could block implementation in a subtractive install before WP-12.
