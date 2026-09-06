# DESIGN: Vision source registry — naming what Halbert can look through

**Date:** 2026-09-06
**Status:** design, ready to implement. Two decisions (§5) want a founder
answer first; neither blocks starting §4 phase A.
**Parent:** `.handoff/DESIGN-GUEST-PERSONA-2026-09-06.md` §5 and §11 phase 6.
That document scoped this as "standalone, worth building whether or not
guest personas ship" — this is that spec.
**Proposed roadmap row:** `VIS-1` (§8)
**Branch:** none yet. Independent of `feat/guest-persona`; touches
`vision/`, `tools/vision_tools.py`, `config/being_config.py`, the Vision
settings tab.

---

## 1. Why this exists on its own

Two things are true today and neither involves a persona:

1. **There is no way to say "the patio camera only."** Vision consent is a
   single global on/off plus one webcam index.
2. **Frigate cameras are invisible to every CV tool.**
   `tools/vision_tools.py:461 _capture_frame_for_cv(source)` accepts exactly
   `"webcam"` or `"screen"`. A house with six cameras can be *told about*
   them through Frigate events, but `detect_objects` cannot look at one.

Fixing (2) is a feature. Fixing (1) is the prerequisite for any per-persona,
per-room or per-time-of-day camera policy — including the guest persona's
narrowed view, which is what surfaced it.

---

## 2. What the code is now

Four independent notions of "a camera", none aware of the others.

| Where | What it calls a source | Named? |
|---|---|---|
| `vision/config.py` | `webcam.camera_index: int = 0`, `screen_capture.monitor_index: int = 1` | no |
| `tools/vision_tools.py:461` | the literal strings `"webcam"` / `"screen"` | no |
| `integrations/frigate/frigate_config.py:39` | `enabled_cameras: list[str]`, filtered at `frigate_mqtt_subscriber.py:224` and `:248`; `frigate_client.py:135 get_cameras()` returns name + zones + objects | **yes** |
| `vision/zone_watcher.py:117` | an anonymous `frame_source: Callable[[], bytes]` | no — a zone knows its own name, not which camera it watches |

Per-persona vision consent already exists and has nowhere to put a source:
`config/being_config.py:164 SensesVisionConfig` carries
`enabled`, `proactive_monitoring`, `capture_on_intent`, `capture_on_error`,
`interval_seconds`, `error_patterns`. No source selection.

The settings UI makes the user type the integer
(`VisionTab.tsx:257` "Camera index", `:205` "Monitor index").

---

## 3. The finding that makes this more than plumbing

**The configured source is a default, not a bound.**

```
vision_tools.py:137   camera_index = args.get("camera",  cfg.webcam.camera_index)
vision_tools.py:60    monitor      = args.get("monitor", cfg.screen_capture.monitor_index)
```

The *model* picks. A persona scoped to the patio can pass `camera: 1` and
get the bedroom; the config value only applies when the model says nothing.

So the registry must become the authority the tool consults, not the
fallback it uses when the argument is absent. Any per-persona scoping built
on top of the current shape is decorative — a privacy control that is not
one, which is worse than none, because the user will believe it.

This mirrors §15.1 item 2 of the guest-persona build: schema-level masking
was necessary but not sufficient, so the mask lives at `get_schemas()` *and*
`execute()` default-denies. Same lesson, different surface.

---

## 4. The design

### 4.1 A source identity

```
halbert_core/vision/sources.py

    @dataclass(frozen=True)
    class VisionSource:
        id: str          # "screen:1" | "webcam:0" | "frigate:patio"
        label: str       # "Studio monitor", "Desk webcam", "Patio"
        kind: str        # screen | webcam | frigate
        native: str      # the index or camera name the driver needs

    list_sources() -> List[VisionSource]      # registry, config-backed
    probe_sources() -> List[VisionSource]     # what the machine can see now
    resolve_source(id) -> bytes               # one frame, JPEG
```

`id` is stable and persisted; `native` is the volatile part. That
separation is the point of D1 (§5).

### 4.2 One resolver

`resolve_source(id)` replaces the two-value enum in
`_capture_frame_for_cv`. `detect_objects` / `detect_faces` /
`detect_motion` take a source **id**, not `"webcam" | "screen"`, and a
Frigate camera becomes a first-class CV source (subject to D2).

### 4.3 The argument becomes a request

Every capture tool resolves its source through one gate:

```
    permit_source(requested_id, *, caller_scope) -> VisionSource
        raises VisionSourceDenied
```

- Absent argument → the caller's default source, not a global one.
- Out-of-scope id → **refused and audited**, never silently downgraded to
  an allowed source. A silent downgrade is a lie about what was looked at.
- Unknown id → refused with the list of ids the caller may use.

### 4.4 Per-persona narrowing

`SensesVisionConfig` gains:

```
    sources: List[str] = field(default_factory=list)
```

- Empty = every source `vision_config.yml` has enabled. Backwards
  compatible: existing persona files mean what they meant.
- Non-empty = intersected with the system-enabled set. **Narrowing only.**
  A persona can never name a source the system has switched off (I1).

### 4.5 Migration

`webcam.camera_index` and `screen_capture.monitor_index` become the
`native` of two auto-registered sources (`webcam:<n>`, `screen:<n>`) with
default labels, so an existing install keeps working with no user action
and the values are not lost.

### 4.6 UI

Vision tab: a list of named sources with enable toggles and editable
labels, replacing the two index boxes. Persona editor: a subset picker
over the system-enabled list, with "all enabled sources" as the default
rendering of an empty list — not an empty multi-select, which reads as
"none".

---

## 5. Decisions wanted

**D1 — probe or declare?**
Probing OpenCV indices and monitors gives a good first run and unstable
ids: plugging in a webcam can renumber the bedroom to `1`. A persona
scoped to `webcam:0` would then be looking somewhere else with no error and
no notice.
*Recommendation:* probe to **offer**, persist a declared id and label. A
source keeps its name across a reboot; a `native` that stops resolving is
reported as unavailable rather than silently re-pointed.

**D2 — is a Frigate camera a real CV source?**
"Halbert can look at the patio" versus "Halbert hears what Frigate says
about the patio". Frames-on-demand changes bandwidth, latency and the
privacy story; event-only keeps Halbert downstream of Frigate's own
detection.
*Recommendation:* yes, on demand only — no continuous pull — because
`detect_objects` against a named camera is the feature, and `ZoneWatcher`
already polls Frigate latest-frames for exactly this
(`zone_watcher.py:10`).
*If yes:* `mcp/camera_gate.py` implements a "metadata in, nothing out"
boundary for camera data and its own header says it is **not wired into
`server.py` dispatch** (R2-OBS-1, 2026-09). The moment a camera-touching
tool is reachable over MCP, that gate must be connected — its header says
so, in those words. Do it in the same pass.

---

## 6. Invariants

- **V1 — narrowing only.** A persona's `sources` is intersected with the
  system-enabled set, never unioned.
- **V2 — no silent substitution.** A denied or unresolvable source is an
  error the caller sees, never a different picture.
- **V3 — the id is the contract.** Labels are for humans and may change;
  `id` is what a persona file and an audit record hold.
- **V4 — the registry is the authority.** No capture path reads a raw
  index out of tool arguments.

---

## 7. Phases

| # | Contents | Effort |
|---|---|---|
| A | `vision/sources.py` — the dataclass, registry, probe, `resolve_source`; migration from the two integers; tests | ~1 d |
| B | `permit_source` and rewiring the capture tools; the audited refusal | ~1 d |
| C | `SensesVisionConfig.sources` + intersection with system-enabled | ~0.5 d |
| D | Vision tab source list; persona subset picker | ~1 d |
| E | *(D2 yes)* Frigate as a CV source + wire `mcp/camera_gate.py` | ~1 d |

Phases A–B are the ones with the safety content. C–D are surface. E is
gated on D2.

---

## 8. Proposed roadmap row

| Row | Statement | Notes |
|---|---|---|
| `VIS-1` | Vision sources are named, enumerable and individually consentable; a capture names a source id, an out-of-scope request is refused rather than substituted, and a persona may narrow the set it can see but never widen it | Prerequisite for the guest persona's narrowed view (`GP-1` §5) and for any per-room or per-time-of-day camera policy. Independent of `GP-1` — ship in either order. |

---

## 9. Key files

| File | Role |
|---|---|
| `vision/config.py` | the two unnamed integers being replaced |
| `tools/vision_tools.py:60,137,461` | where the model currently picks the source |
| `integrations/frigate/frigate_config.py:39` | the naming + allowlist pattern to generalise |
| `integrations/frigate/frigate_client.py:135` | `get_cameras()` — names, zones, objects |
| `vision/zone_watcher.py:117` | anonymous `frame_source`; gains a source id |
| `config/being_config.py:164` | `SensesVisionConfig` — where `sources` lands |
| `mcp/camera_gate.py` | written, tested, unwired (R2-OBS-1) — connect it under D2 |
| `dashboard/frontend/.../VisionTab.tsx:205,257` | the index boxes to replace |
