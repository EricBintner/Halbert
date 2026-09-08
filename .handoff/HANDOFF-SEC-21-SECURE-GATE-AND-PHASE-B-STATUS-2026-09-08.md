# HANDOFF FOR REVIEW: SEC-21 secure-gate fix, APPLE-1 interim hardening, and where Phase B actually stands

**Date**: 2026-09-08 · **Status**: SEC-21/APPLE-1 **merged**; Phase B **assessed, not touched**
**Merged into `main`**: `7c5cf0d0` (merge of `9b593ebc`, branch `fix/sec-15-cloud-suffix`)
**Suite on the branch**: `7771 passed, 15 skipped, 6 xfailed, 1 failed` — the failure is pre-existing on `main` (§4)
**Issues closed**: `.handoff/ISSUE-SEC-15-CLOUD-SUFFIX-BYPASSES-SECURE-GATE-2026-09-07.md` (canonical id **SEC-21**), `.handoff/ISSUE-APPLE-1-FOUNDATION-MODELS-INTEGRATION-PATH-WRONG-2026-09-07.md` (interim only)
**Decisions**: `DECISIONS.md`, four rows dated 2026-09-08

---

## 0. What a reviewer should do with this

Every claim below is checkable and §7 gives the commands. Three places deserve
scepticism over trust: §2's five-site claim (I found the extra three, so I am
the wrong judge of whether there is a sixth), §3's stated consequence (it
changes what you will experience on this machine), and §5, where I describe a
process failure of my own that pushed another session's work.

---

## 1. What was found

Two issue docs were filed by a Devin session on 2026-09-07 with no branch, no
commit and no plan behind them. Both were real, and the first was **live**.

**SEC-21 — the secure-model gate inferred locality from the URL.** Ollama's
`:cloud` models are served from `localhost:11434` and proxied to ollama.com at
inference time. The gate saw a loopback address, declared the model local, and
let a *secure* turn — one the context assembler had flagged as carrying
secrets — leave the machine.

This was not a constructed attack path. It was this machine's configuration
at the moment I looked:

| slot | model | endpoint | provider |
|---|---|---|---|
| `secure_model` | `apple-foundation-3b` | `127.0.0.1:11435` — **nothing listening** | `apple-foundation` |
| `chat_model` | `deepseek-v4-flash:cloud` | `localhost:11434` | `ollama` |
| `specialist_model` | `deepseek-v4-pro:cloud` | `localhost:11434` | `ollama` |

Every secure turn tried the dead Apple slot, failed on connect, fell back to
the guide, passed the URL check, and went to ollama.com. Six `:cloud` models
are pulled on this machine.

**APPLE-1 — the trigger.** The Apple Intelligence endpoint was provisioned at
some earlier boot when the FoundationModels bridge answered a probe. The bridge
was never built (nothing has ever listened on 11435 in any committed form), and
the boot path skipped provisioning entirely once the endpoint existed — which
is precisely the case where a re-check was needed. So the dead assignment was
never revisited.

---

## 2. What shipped (`9b593ebc`)

`being_config.py` had already stated the rule, in three clauses: reject any
tag ending in `:cloud`; reject any provider outside the local set; **never
infer locality from the endpoint URL**. Every gate in the tree implemented
only the negation of the third clause. The fix is one function implementing
all three, used everywhere a locality verdict is made.

**`llm_config.is_local_model(model, url, provider)`** — the single choke point.
An unnamed model reads as *not* local: on a secure gate, a default that reads
as local is the whole bug.

**Five sites, not the two the issue named:**

| site | what was wrong |
|---|---|
| `agent._resolve_turn_model` → `gate()` | URL-only; took no model name |
| `agent._fallback_to_guide` | URL-only; **this is the path that fired live** |
| `agent._resolve_turn_model` dedicated secure-slot branch | `return`ed **before** `gate()` — a `:cloud` tag in the secure slot itself was checked nowhere |
| `llm_config.normalise` | let a `:cloud` `secure_model` on a loopback endpoint **save as enabled** |
| `capabilities._probe_secure_model` / `_probe_local_llm` | reported `CAP_SECURE_MODEL` (which is what lets the resolver try the dedicated slot at all) and `CAP_LOCAL_LLM` (→ `sys.local_llm` in the persona permission layer) as present for a `:cloud` model on loopback |

`client.LOCAL_GPU_PROVIDERS` now re-exports `llm_config.LOCAL_RUNTIME_PROVIDERS`
so there is one provider set; `llm_config` does not import `client`, so it had
to move that direction.

**One correction to the issue's proposed fix.** It suggested `/api/show`'s
`remote_host` field as the authoritative check. **That field does not exist in
Ollama 0.32.15.** I queried all 33 models on this machine: the `:cloud` suffix
agrees exactly with the absence of a `modelfile`, and `gemini-3-flash-preview:latest`
— which looks like it should be cloud — is a genuine local copy with a
modelfile. So the suffix is the primary signal, the gate stays deterministic
without a daemon, and a `/api/show` corroboration was considered and left out.

**APPLE-1 interim: `reconcile_apple_intelligence()`.** Provisioning's
symmetric operation: at boot, if the Apple endpoint is registered and the
bridge does not answer, clear any slot pointing at it, at WARNING, naming the
slot. The endpoint stays registered (eligibility did not change, reachability
did) and provisioning re-fills an empty slot when the bridge is next seen. It
touches only slots whose `endpoint_id` is the Apple one — a local Ollama secure
model the user chose is not its business. Wired into the boot branch the old
code skipped. **The Swift sidecar / Rust-FFI investigation is not started**;
that is R&D and its own piece of work.

**Evidence, run against the real config rather than the fixtures:** the
fallback logs *"Secure turn: apple-foundation-3b unreachable and the guide
(deepseek-v4-flash:cloud @ http://localhost:11434) is not local — failing
closed rather than answering from a cloud endpoint"* and returns `None`.
Removing the tag clause turns 18 tests red; removing the provider clause, 4.

**Tests**: `test_model_locality.py` (new, 35 cases incl. the live triples
verbatim) and extensions to `test_agent_model_override`, `test_secure_model`,
`test_capabilities`, `test_auto_provision` — 25 more. All written red first;
the truth table caught the unnamed-model gap in my own first implementation.

---

## 3. The consequence you will experience

**After the daemon restarts, secure turns on this machine fail closed** with
*"This turn contains sensitive content … no local model is configured."*
Reconcile clears the dead Apple slot; every remaining slot is `:cloud`; there
is no local model. That is correct — today those turns silently leave — but it
is a visible change. The remedy is a genuinely local model in any slot (the
secure slot, or a local guide), and the picker will now refuse to save a
`:cloud` tag as the secure model.

---

## 4. Bookkeeping that was wrong or unclear

- **The issue was filed as SEC-15, which was already taken** (prompt-injection
  containment in `SECURITY-IMPLEMENTATION-PLAN-2026-09-06.md`; highest assigned
  was SEC-20). Canonical id is **SEC-21** in code, tests, commits and
  `DECISIONS.md`. The filename is kept because `ROADMAP.md` already references
  it; the doc carries a header note.
- **The one failing test is not this work's.** `test_spa_routes::test_every_frontend_route_is_served_by_the_spa_table`
  fails identically on untouched `main`: `/compute` and `/mcp` are routed in
  `App.tsx` but absent from `dashboard.app.SPA_ROUTES`, so they 404 as deep
  links under the systemd deployment. `/mcp` came in with B5 (`9411b03c`);
  `/compute` with the node-list rail (`27998aa0`). Two-line fix; not made here
  because it is another workstream's defect and the founder's call to bundle.

---

## 5. A process failure of mine, on the record

The first merge chain **aborted** — git refused to overwrite the two untracked
issue docs in the main checkout — but a `| tail` on the merge step defeated
`set -e`, so the chain continued: it pushed `main` *without* my merge, and
removed the worktree. My work was safe on the branch and I merged cleanly on a
second pass with every exit code checked and no pipes on the git steps.

But **that first push carried 25 of another session's app-ui-access commits**
(`564aa51e` … `a429145b`) that were on local `main` and not yet on origin. They
are legitimate `main` history and I altered nothing — but their owner may not
have intended them pushed yet, and it cannot be undone without a force-push,
which I will not do. Whoever owns app-ui-access should know their branch is on
origin as of `a429145b`.

Two rules I am carrying forward: check `$?` explicitly on merge and push, never
through a pipe; and never remove a worktree before verifying the merge landed.

---

## 6. Where Phase B stands (assessed, not touched)

Asked "is Phase B complete?" I found the answer depends on which document
defines it, and verified rather than recalled — my own memory note ("B5 stopped
mid-work") was stale.

**By the PLAN (`PLAN-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md`, Phase B = B1–B5): complete, with one wiring gap.**
All five are on `main` (`c7e6712e` … `9411b03c`, merged as `a429145b`). The
`feat/app-ui-access` worktree is clean, nothing is stashed. I ran B5's
acceptance rather than trusting its presence: **28 backend tests pass, all 470
MCP-tagged tests pass, the 5 frontend tests pass**, and `CAP_MCP_CLIENT` gates
both the API (a config edit while off is a 409, not a silent no-op) and the
page. The gap is the `SPA_ROUTES` omission in §4 — the page works by
navigation, not by URL.

**By the HANDOFF (`HANDOFF-VOICE-ASSISTANT-APP-UI-ACCESS-2026-09-07.md`, which added B6): not complete.**
B6 — *expose Halbert's tools as an MCP server, wrapping the same `execute` the
agent uses* — has no commit. The merge title's "MCP client+**server**" refers
to the pre-existing August server: `mcp/server.py` still exposes only the
seven read-only `_tool_get_*` handlers and nothing wraps the agent's
`ToolExecutor` registry. The two `B6` hits in git history are the old
terminal-pool numbering, not this.

**The "B6 audit → final review" step has not happened.** There is no results
or review document for app-ui-access; `REVIEW-PACKET-02-MCP-SERVER-AND-BOUNDARY.md`
is from the August MCP series.

**Recommended order:** (1) the two-line `SPA_ROUTES` fix — closes a real B5
defect and returns `main` to green; (2) a founder decision on B6 — it was
added as "NEW, not in original plan", it is a real new surface (Halbert's
tools reachable by other agents over MCP, so the MCP trust-boundary rulings
apply in full), and it should not be started unasked; (3) the final review.

---

## 7. How to check any of this

```bash
arch -arm64 .venv/bin/python -m pytest halbert_core/tests/test_model_locality.py -q
arch -arm64 .venv/bin/python -m pytest halbert_core/tests/ -q -k "secure or capabilit or provision or model_override"
git show --stat 9b593ebc
# the live-config verdict (read-only):
arch -arm64 .venv/bin/python -c "from halbert_core.model import llm_config as c; from halbert_core.model.llm_config import is_local_model as L; [print(s, m.model, L(m.model,m.url,m.provider)) for s in ('secure_model','chat_model','specialist_model') for m in [c.resolve(s)] if m]"
# the remote_host claim, on this Ollama:
curl -s localhost:11434/api/show -d '{"name":"deepseek-v4-flash:cloud"}' | python3 -c "import sys,json; print(sorted(json.load(sys.stdin)))"
```

Three things worth checking by hand rather than by test, because the tests
were written by the same person who wrote the code:

1. **Is there a sixth site?** `grep -rn "_is_local_url\|is_local_model" halbert_core/` —
   I converted every locality *verdict* I found; a new caller that reaches for
   `_is_local_url` directly would reopen the hole. `_is_local_url` is still the
   right tool for its remaining callers (`normalise`'s peer:// rejection, the
   `_probe_local_llm` docstring); the question is whether any of them is
   secretly a verdict.
2. **The reconcile write.** It calls `set_slot(slot, "", ep_id)` on your live
   `models.yml`. Confirm you are comfortable with boot writing config; the
   symmetry argument (provisioning already does) is mine.
3. **The consequence in §3, on the actual dashboard**, not in a test.

---

## 8. What I would want a reviewer to push on

- The decision to make **unknown provider / unnamed model read as not local**
  is a fail-closed posture that could block a legitimate setup I have not
  imagined (a provider string I did not list). `LOCAL_RUNTIME_PROVIDERS` is the
  allowlist; if something local is missing from it, that is where.
- **Reconcile clears `chat_model` too** when a 16–24 GB Mac had it provisioned
  to Apple. Right by the same logic, but it is a bigger user-visible change
  than the secure slot.
- **Nothing here has run against a working FoundationModels bridge**, because
  none exists. The `apple-foundation` on-device pass-through in
  `is_local_model` is asserted by the rule, not by a live sidecar.
