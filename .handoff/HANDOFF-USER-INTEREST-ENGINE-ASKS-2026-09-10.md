# Handoff: three engine findings from building the user-interest half

**From:** Halbert, `feat/user-interest-memory` · **Date:** 2026-09-10
**To:** Haloysius engine context
**Answers:** `HANDOFF-OBSERVATION-LENSES-UPSTREAM-ASKS-2026-09-06.md` — the four
asks all landed and are in use. These are three more found while building on them.
**All three measured**, not read off the source: the probes are in this document.

---

## 1. The handoff's confidence advice is incomplete, and the gap is silent

It tells a writer building its own `PersonaMemory`:

> If the writer builds its own `PersonaMemory` rather than calling `teach()`,
> it must set `source="user"` itself.

Measured on `main` as it stands, `Provenance.USER_ORGANIC` alone calibrates at
**0.7** — the conversation-extraction default, which is exactly the confidence
the fix was meant to raise it above. The 0.9 gate is:

```python
if provenance == Provenance.USER_ORGANIC and "user_stated" in tags:
    initial_conf = 0.9
```

`teach()` and `update_preference()` both set that tag internally, so the engine
is self-consistent — but a consumer following the handoff gets a stated fact
stored at the inferred confidence, which is the original defect wearing a
different hat.

| what the writer sets | confidence |
|---|---|
| `source=USER_ORGANIC` only (the handoff's advice) | **0.7** |
| `source=USER_ORGANIC` + `user_stated` tag (what `teach()` does) | **0.9** |
| nothing | 0.7 |
| `source=CONSOLIDATION` | 0.6 |

**Ask:** either say so in the handoff, or — better — calibrate on provenance
alone and let the tag be decoration. A two-part gate where one part is a bare
string in a list is going to be got wrong by the next consumer too.

Halbert sets both and pins it with a test through a real store rather than
against its own tag list, so the test still fails if the gate moves.

---

## 2. `ObservationStore` can mark by memory but cannot delete by memory

`mark_stale_by_memory(source_memory_id)` exists. There is no
`delete_by_memory`, and no getter returns a row by `source_memory_id` —
`get_active` filters by category and excludes stale rows, `search` is FTS over
text. So a consumer doing a hard forget cannot enumerate the rows it wrote.

Halbert's forget path currently enumerates through FTS and keeps only exact
`source_memory_id` matches: the search enumerates, it never decides. That
works, and it is not what a seam should look like — an FTS miss is
indistinguishable from "there was nothing to delete", so the per-plane report
has to say "not reached" on a case that may simply have had no mirror.

**Ask:** `delete_by_memory(source_memory_id) -> int`, symmetric with the
marking one. Same FTS retirement, `secure_delete` and WAL checkpoint that
`delete()` already does.

---

## 3. `_extract_subject` returns `None` for `"X: Y"` when Y is the payload — and unrelated memories then collide

This is the sharpest of the three, and it cost the most to find.

The engine's own docstring lists `"X: Y" format -> X` as a supported pattern,
and the regex is `^(\w+(?:\s+\w+)?):\s*` — anchored at the **start**. For
content shaped `User is interested in: sailing` nothing matches at the start,
the "interested in" pattern no longer matches either because the colon
intervenes, and the function returns `None`.

With `None` as the subject, **every interest reads as contradicting every
other**. Measured, six stated interests written in sequence:

```
vintage thinkpads -> ADD     New memory added
thinkpads         -> UPDATE  Replaced interest_vintage-thinkpads
sailing           -> UPDATE  Replaced interest_thinkpads
vintage radios    -> ADD     New memory added
zfs               -> UPDATE  Replaced interest_sailing
zfs send          -> UPDATE  Replaced interest_zfs

stored: 2 of 6
```

`sailing` replaced `thinkpads`. Those are not contradictions in any sense; they
are different facts about a person, and four of the six were destroyed.

```python
store._extract_subject("User is interested in: sailing")  # -> None
store._extract_subject("User is interested in sailing")   # -> 'interest in sailing'
```

Halbert's fix is its own: drop the colon from the canonical content. Six of six
now store, and the withdrawal form still supersedes, which is the property
`4f95418` added and the colon was quietly defeating.

**Two asks, in order of value:**

1. **Make `_is_contradiction` fail closed on an unextractable subject.** A
   `None` subject currently behaves as *"matches everything"*; it should behave
   as *"matches nothing"*. That is one branch, and it turns a silent
   data-destroying default into a no-op. Every consumer benefits, including
   ones whose content shape nobody has looked at.
2. Optionally, extend `_extract_subject` to handle `interested in: X`. Lower
   value than (1): the first fix protects shapes nobody has thought of yet,
   this one protects a shape we have now stopped using.

**Worth checking upstream:** any other consumer whose memory content contains a
colon in a `"<prose>: <payload>"` shape is in the same position, silently.
`teach()` writes `f"User's {subject}: {fact}"` — which *does* match the
start-anchored pattern via `User's`, so it is fine; the hazard is consumers
writing their own content, which is exactly what the handoff's §1 advice
invites.

---

## Not an ask: the dedup interaction, recorded

`smart_add`'s semantic duplicate check (0.85) collapses near-miss topics —
`thinkpads` into `vintage thinkpads` — so a near-miss pair is one memory
regardless of what a consumer does with its own keys. Halbert's `topic_slug`
deliberately keeps those apart; the engine joins them anyway. Not a defect in
either, but it means the fragmentation question is settled by the engine, and
a consumer's dedup key is narrower in effect than it looks. Recorded so the
next person who reads `topic_slug` and expects two rows is not surprised.
