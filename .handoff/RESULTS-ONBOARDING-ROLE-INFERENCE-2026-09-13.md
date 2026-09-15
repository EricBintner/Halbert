# Results: Onboarding Role Inference — implemented

**Date:** 2026-09-13
**Implements:** `HANDOFF-ONBOARDING-ROLE-INFERENCE-2026-09-07.md` (the
scan-first, suggest-and-confirm redesign of the "user type" question)
**Status:** Core flow landed. Consumption side partially landed — see
"Deferred" below.

---

## What landed

| Handoff step | Where |
|---|---|
| Q3 scanner additions | `discovery/scanners/system_profile.py` — HA/MQTT/Z2M names in both notable-services lists (`homeassistant`, `mosquitto`, `zigbee2mqtt`, `zwave`, `deconz`, `openhab`, `node-red`, `frigate`, `scrypted`, `iobroker`, `homebridge`; `hass` deliberately excluded — it substring-matches `chassis`); macOS now populates `usb_devices` from `ioreg -p IOUSB` (was never filled) |
| Q2 inference in the backend | `discovery/role_inference.py` — `collect_probe_signals()` (read-only fast subset: os/hardware/desktop/services/containers/development/boot + psutil uptime), `extract_signals()`, `infer_roles()` (the §5.2 scoring + §5.4 ±2-point tie margin) |
| Q1 probe endpoint | `GET /api/settings/onboarding/probe` → `{signals, suggestion}`; runs in a worker thread, ~2.8 s on this machine |
| Storage | `preferences.yml` `roles`; `system_profile.json` `user_settings.roles`; marker file is now two lines (name lines only — Q4) |
| Frontend wizard | `Onboarding.tsx` — probe fires while the welcome screen is up; configure step shows "What is this computer for?" as three multi-select chips (Workstation / Server / Home Hub), pre-checked from the suggestion until the user touches them; first-person reasoning line under the chips; optional "anything else?" note |
| Q6 free-text | `notes` → `being.yml` `purpose` — the existing field the prompt already renders, set only when empty so a re-run can't clobber a Being-tab edit |
| Q7 editable roles | Settings > Being > **Machine Role** card → `GET/POST /api/settings/machine-roles` |
| §6.6 prompt context | `_machine_role_line()` in `prompts/agent_prompts.py` — "This machine's role: workstation and home automation hub." in the identity block |
| §6.1 landing | `landingRoute(roles)` in `routeCapabilities.ts` — post-onboarding entry lands on `/services` for a server-only machine, `/home` for a hub-only machine, `/` otherwise |
| §6.2 nav visibility | `/api/instance/info` gains `machine_roles` + a `containers` feature split from `development`: a declared hub gets the Home panel; a machine declared server-or-hub-only loses Development and GPU but keeps Containers |
| Profile summary | `get_summary()` now says "I serve as a workstation / a server / a home automation hub." |

## Deviations from the handoff (deliberate)

- **No `user_type` migration.** The handoff's Q5 recommendation was silent
  migration; the standing directive "no users yet — do not build
  migrations or back-compat shims unasked; leave superseded data on disk,
  unread" wins. `prefs["user_type"]` stays on disk where it exists,
  unread; `roles` defaults to `["workstation"]` when absent.
- **The probe calls `_scan_*` methods directly**, not `scan_category()`,
  which mutates and saves `profiler.profile` — the probe is read-only by
  construction.
- **An empty-evidence probe suggests workstation, not server.** Headless
  (+3 server) only scores when the probe actually returned evidence;
  otherwise a failed probe would call every broken-scan machine a server.
- **Landing applies at post-onboarding entry only.** Redirecting `/` on
  every load would make the overview unreachable on a declared server; a
  real "fleet view" doesn't exist yet.

## Deferred (still designed, not built)

- §6.3 interactive-feature gating (voice/chat off on servers) — needs a
  decision on whether declared intent may *remove* capability the hardware
  has; nav visibility does it, feature gating is a bigger lever.
- §6.4 scan emphasis per role.
- §6.5 proactivity mode per role.
- Landing page beyond the first entry (see deviation note).
- SEC-6 (two-phase boot + consent review) still absorbs this whole flow
  when it lands — roles survive it; `user_type` and the marker were
  already removed by this change, which is exactly what SEC-6 prescribes.

## Tests

- `tests/test_role_inference.py` — the §5.3 ambiguous cases as fixtures
  (headless mini + HA → server+hub; desk mini + HA → workstation+hub;
  NAS → server; Pi + Zigbee → hub; strong workstation + HA container →
  workstation only, hub noted).
- `tests/test_onboarding_roles.py` — complete/probe/machine-roles routes,
  marker format, notes→purpose, resolver filtering.
- `Onboarding.test.tsx` — asks "what is this computer for", pre-checks the
  suggestion, POSTs `roles` and never `user_type`, survives a dead probe.
- `routeCapabilities.test.ts` — containers/development split +
  `landingRoute`.
- Verified: 26 new Python tests, 5 new frontend tests, full frontend
  suite 1091/1091, `tsc --noEmit` clean. One unrelated failure exists on
  main regardless: `test_multi_instance.py::TestPersonaIdFromEnv::
  test_custom_persona_id` (this host's real `being.yml`
  `persona_id_override` wins over the env var — environmental).
