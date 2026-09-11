# Where everything stands — 2026-09-10

A map, not a plan. `ROADMAP.md` and `DECISIONS.md` remain the spine; the rows
below marked **→ ROADMAP** are the ones that should graduate there.

## How we got here, in five lines

The opus remediation batch finished and merged. Verifying one of its own fixes
(the SQLite WAL warning) meant checking whether a Python upgrade would clear
it — which found that the **shipped sidecar execs an interpreter from a
user-writable path**. That is a real finding, and it is why the runtime thread
exists. Separately, the memory-boundary question the founder raised turned into
research, and the research produced one mechanism (the disagreement meter) that
two other applications want. Nothing was abandoned; three threads are open at
once.

---

## 1. Done and merged

| | |
|---|---|
| **OSS pass 2 — opus tier** | All twelve packets. Merged `55ecef87`, pushed. Suite 8569 passed, 0 failed. |
| **MCP package preflight (FD-10)** | Built by a concurrent session, reviewed, adversarially passed, founder-ratified. Merged `c9e70623`. |
| **WAL-reset correction** | The audit's mechanism was wrong (a data race, not a crash bug); severity downgraded to INFO; predicate corrected to exact patched versions. `87b6418e`. |
| **Six SKILL.md descriptions** | FD-20 answered — written rather than trimmed; over-limit set now empty. `4defc08c`. |
| **Attunement Phase C prerequisites** | Haloysius' 2026-09-10 handoff §2.1 and §2.2, both landed. Shadow mode calls `decide()` and records both verdicts on one row; dismiss / snooze / "propose fix" label the attempt; the ignored sweep runs hourly. Reviewed and two criticals fixed before merge — a reaction could land on a suppressed attempt (the ordinary path, not an edge case), and every shadow margin carried a fixed −0.25 from a counter the wiring could not advance. `feat/attunement-phase-c-prereqs`. Suite 8641 passed, 0 failed. |

## 2. Ready to build — nothing blocking

**→ ROADMAP** · **Runtime and SQLite pinning.**
`.handoff/HANDOFF-RUNTIME-AND-SQLITE-PINNING-2026-09-10.md`. Dispatchable.
Contains the security finding: the signed app's sidecar is a bash script that
execs `$HOME/.local/share/halbert/repo/.venv/bin/python`, so anything that can
write there runs with every TCC grant Halbert holds. Fix and the SQLite pin are
one change: a uv-pinned interpreter, frozen, shipped inside the bundle.
*Highest value of anything open.*

**→ ROADMAP** · **Secure Enclave entitlement spike.** An afternoon, and it
kills or confirms the whole local re-auth route. If a Tauri-bundled,
Developer-ID-signed `.app` cannot carry a `keychain-access-groups` entitlement
via an embedded provisioning profile, the sound design dies and the fallback is
a biometry-gated HMAC. Do this before any re-auth code.

**Disagreement meter, Phase 0.** Haloysius `docs/DISAGREEMENT-METER-SPEC.md`.
Phase 0 is **decisions, then vectors** — five contract items must be settled
first (§5.1–5.4). Buildable now; needs none of the pending memory decisions.

**A07-G8, the yield primitive.** Small, in scope, unblocked since R-01 Phase B
landed. Interrupting during a long foreground command currently parks the
delivery until the command exits.

## 3. Blocked, and on what

| Item | Blocked on |
|---|---|
| **R-12 turn-loop wiring** | The sonnet batch's R-12 Phase A (`agents/threads.py`). Both halves are written and neither has a caller. One commit once Phase A lands. |
| **Memory boundary implementation** | Five founder decisions, §8 of the memo. |
| **Rung 3 (characterisation)** | Nothing technical — it is unbuilt by anyone and is the natural first joint build across applications. Wants a decision that it *is* joint. |
| **Sonnet batch: R-03, R-12 Phase A** | Not ours. Their branch, still open. |

## 4. Decisions waiting on the founder

**Memory boundary** — `.handoff/DESIGN-MEMORY-BOUNDARY-2026-09-10.md` §8, five
ordered, first two are deletions:
1. Ratify that the two-store split holds (on the deployable/ownership ground).
2. Replace the curated core with ranked claim keys → the engine.
3. Approve partitioning by **acquisition mode** (observed vs asserted).
4. Approve the merge-type declaration (`LWW` / `SET` / `ASK`, default `SET`).
5. Approve building the disagreement meter before any provenance column.

**Attunement, two rows** (Haloysius handoff §4.1 and §4.2, plus one of ours):
1. `ATN-1` — Halbert's attachment ceilings. The engine's are a companion's and
   it invites a consumer to set its own; ours are shipped as
   `max_proactive_per_day=24` (a runaway guard, not a ration — the dial is the
   volume policy) and `new_relationship_*=0` (a machine-minder's first week is
   when it has the most to say). **Built on the default; ratify or overrule.**
2. `ATN-2` — the engine's daily cap is the only gate that does not yield to
   `Utterance.authority`, while `new_relationship_sessions` in the same struct
   does. Pinned engine-side as a conformance vector, so either way is a
   decision. Reaches us only if Halbert ever emits rulings — a guest persona
   citing the machine's rules is the shape that would.
3. `ATN-3` — F1's threshold: how much evidence before Halbert *suggests* a dial
   change, and is a suggestion itself an interruption that has to pass the gate
   it is about? The engine will not answer this; it is a judgment about our
   surface. Not blocking: Phase C's reader is buildable without it, and the
   adjuster must not ship until both arms have real rows either way.

**Twelve `pending` rows in `DECISIONS.md`** dated 2026-09-09 — the founder
defaults the opus batch proceeded on under §7's "work proceeds on the default
unless overruled". Several are posture decisions worth overruling.

**Still open, deliberately:** whose namespace the claim keys are; cross-store
ordering for `LWW`; and Fable's Q1/Q3 on the memory memo (unsent, nearly no
credits).

## 5. Newly surfaced, not yet triaged

- **`memory_v2` already ships an unmeasured resolver.** `smart_add` runs a
  binary contradiction test from a hand-maintained regex table, and its caller
  writes. It is a third instance of the problem the meter measures, the natural
  first consumer of the nomination phase, and its existing meaning of
  "contradiction" collides with the frozen vocabulary. Recorded in the engine
  spec §7; no work scheduled.
- **A built mechanism with no caller is invisible to every test that mocks
  it.** `SuppressionRecorder` and `update_reaction` both shipped, were both
  tested, and neither had a production caller for four days — the suppression
  log was writing nothing and nobody could tell from the suite. The tests that
  now pin the wiring (`test_attunement_recorder_wiring.py`) are the cheap
  guard; whether other recently-landed seams have the same shape is not
  checked.
- **`./wt_pytest.py` run bare picks the wrong interpreter.** The shebang is
  `/usr/bin/env python3`, which on this machine resolves to
  `~/.local/bin/python3` — pytest without `pytest-asyncio`, so the wrapper's
  own `--asyncio-mode=auto` is rejected as an unrecognised argument. It reads
  as a broken wrapper and is a PATH fact. `arch -arm64 .venv/bin/python
  ./wt_pytest.py <args>` works; `CLAUDE.md` documents the bare form.
- **Two stale `uv` installs and six interpreter sources** on this machine. The
  runtime packet must pin the uv version, not only `.python-version` and
  `uv.lock`.
- **Removing the Intel Homebrew** — founder ruling: machine hygiene, **out of
  scope** for any Halbert packet. Recorded so it is not rediscovered.

## 6. Recommended order

1. **Entitlement spike** — an afternoon, and it decides whether a whole route
   exists.
2. **Runtime + sidecar** — highest value; a live weakness and the product
   directive have the same fix.
3. **Meter Phase 0** — decisions and vectors. Produces the evidence the memory
   decisions want, so it is not competing with them.
4. **A07-G8** — small, closes the last non-gated remediation item.
5. R-12 wiring, when the sonnet branch lands.

## 7. What is deliberately not being done

Auto-continue of interrupted turns (FD-1); the OSV preflight was built after
being deferred, so that row is closed; the promotion ranker's consumer (FD-22,
and the memo now gives it a better reason than "unreviewed" — the design behind
it was wrong); rungs 3–5 of the ladder inside the meter packet; and any
migration or back-compat shim.
