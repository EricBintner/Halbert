# Review: F5 — Variant-as-Hint Refactor (Capability Registry)

**Reviewed:** commits `8f1243eb` (initial rollout, bundled with P2b) and
`330f641b` (completion pass) on `feat/singular-entity`
**Reviewer:** Opus session (wrap-up pass), 2026-08-31
**Verdict:** Architecture is right and the conversion is complete where it
matters. Three probe-level defects found and fixed in this review; two
design notes recorded for follow-up.

---

## What F5 was supposed to be

Replace the hard variant gate (`being.yml: variant: home` ⇒ no terminal,
no ingestion, no SourcePrep, …) with **capability probing**: named,
testable predicates; the variant becomes a *preset* of defaults;
`being.yml: capabilities:` can override anything. Rationale: a Mac Studio
with HA configured should do both sysadmin AND home things; an N150 with
an A2000 should run a local LLM. Capabilities emerge from what is present,
not from a label.

## What landed (verified)

- `capabilities.py`: 9 capabilities, variant presets, probe registry,
  resolution order **override > probe > preset**, singleton probed once.
- Service startup matrix in `dashboard/app.py` fully converted
  (CAP_INGESTION/DISCOVERY/SCHEDULER/CONFIG_WATCHER/SOURCEPREP/TERMINAL/
  HA_CONNECTION).
- Chat path (`routes/agent.py`), context adapters, app-seam wiring,
  tier_router secure-model slot, config_wizard + auto_provision + llm.py
  Apple Intelligence provisioning — all converted.
- Old `is_home_variant` call sites that remain are: graceful fallbacks if
  the capabilities module cannot import (adapters.py, cognition_wiring),
  intentional variant-label uses (compute/peers directional feature,
  instance.py display, body_name default) — all justified.
- Backward-compat tests pin "no overrides = old behavior" for both
  variants. 36 tests passing before this review, 44 after.

## Findings (fixed in this review's commit)

**F5-1 — Variant gates re-introduced inside presence probes (the exact
thing F5 removed).** `_probe_config_watcher` and `_probe_sourceprep`
returned False on `variant == "home"` *before* checking presence. A
home-variant Mac Studio with `config-registry.yml` on disk or SourcePrep
installed got neither capability — the label beat the artifacts, one
level down from where F5 had just removed it. The preset already provides
default-off for home; the probe's only job is "is it present".
*Fixed: variant early-returns removed; probes are presence-only.*

**F5-2 — `_probe_local_llm` used ad-hoc substring matching instead of the
canonical local-URL check.** `"localhost" in url` (a) misses
`http://[::1]:11434`, which `llm_config._is_local_url` correctly accepts,
(b) false-positives on public tunnels like `https://api.localhost.gg`,
and (c) disagreed with `_is_local_url` — the same predicate that
enforces secure_model's local-only rule, so the two probes could answer
"local" differently for the same URL. Its docstring also claimed LAN
addresses count; they didn't, and shouldn't (another machine's Ollama is
the peer tier of the compute chain, not this node's local tier).
*Fixed: uses `_is_local_url`; docstring now states loopback-only and why.*

**F5-3 — `_probe_config_watcher` read `HALBERT_CONFIG_DIR` ad hoc.**
`Path(os.environ.get("HALBERT_CONFIG_DIR", ""))` collapses to a
**CWD-relative** path when the env var is unset — a stray
`config-registry.yml` in the process CWD would flip the capability — and
it bypassed `utils.platform.get_config_dir()`, which also handles the
legacy `Halbert_CONFIG_DIR` spelling and platform paths.
*Fixed: uses `get_config_dir()`.*

## Notes recorded (not fixed — deliberate or follow-up)

- **`CAP_LOCAL_LLM` currently has no consumers.** It is probed, logged,
  and overridable, but nothing gates on it. Keep it: the natural consumer
  is the ComputeRouter's local tier (P4b), whose hardware-profile check
  answers the *OOM-safety* question while this capability answers the
  *configured* question; wiring them together is future work.
- **`_probe_sourceprep` equates importable with index-available.** Coarse
  but honest for "this body can run SourcePrep"; a deeper probe should
  ask SourcePrep for its index state when it exposes an API for that.
- **The registry never re-probes in a running process.** Config changes
  (e.g. adding `ha_url`) require a restart to take capability effect.
  `reset_registry()` exists but nothing calls it in production; a
  re-probe hook after settings mutations is future work, as is the
  frontend capabilities endpoint the F5 commit message already flags.
- **`_load_config` fails open to the sysadmin preset** when `being.yml`
  cannot be read. Same failure class as the old variant gate; noted, not
  changed.
- **Dead private `_is_home_variant()` helpers** retained in tier_router /
  auto_provision / config_wizard / routes/agent with no callers. Harmless
  (private names, documented as retained); delete whenever those files
  are next touched.

## Post-review regression watch (not F5) — resolved

The F5 conversion initially left 18 full-suite failures relative to the
pre-session base (`ffe74bdd`): 16 tests across 7 files that still pinned
the old variant-gate behavior (patching `_get_variant` or the now-dead
`_is_home_variant` helpers, and passing only where the developer
machine's real being.yml/models.yml probe results happened to match),
plus an obsolete `test_conversations_route_module_is_gone` guard and a
Starlette-fragile route-prefix introspection. All repaired in the
follow-up commit: a shared `capability_registry` conftest fixture
(isolated registry, probes off, preset-driven — the F5-correct way to
control gating in tests), the variant-matrix suites rewired onto it with
syncing holders, sysadmin secure-model expectations pinned explicitly
rather than environmentally, the legacy-conversations guard refocused on
"the module is the peer API, not the legacy UI", and the prefix test
asserting endpoint behavior instead of route-object internals.

An earlier draft of this section also blamed 10
`test_cognition_tick_once` failures on the concurrent commits — wrong:
those fail identically on the pre-session base in the full suite (they
were truncated out of the first failure listing read). They are part of
the pre-existing environmental set, not a regression.