# Review Packet 03: Sentient Home Architecture (Home Assistant, Wyoming Voice, Frigate Vision & Multi-Instance)

**Review Level:** **Fable Level Review**  
**Domain:** Ambient Home Cognition, Home Assistant HACS Bridge, Wyoming Voice Protocol, Frigate NVR Computer Vision, and Multi-Instance Isolation  
**Target Date:** 2026-08-29  
**Status:** Ready for Deep Subsystem Scrutiny & Phase 7→8 Transition Review  

---

## 1. Executive Summary & Review Scope

The past week saw the transformation of Halbert from a purely host-level sysadmin tool into an **ambient Sentient Home Intelligence**. This subsystem operates as the cognitive orchestration layer above Home Assistant and Frigate NVR, deliberately avoiding UI dashboard duplication by leveraging existing HA entity registries, Bermuda BLE presence, and Frigate camera feeds.

Key architectural systems implemented:
1. **Multi-Instance Isolation (Phase 7):** Clean separation between `HALBERT_VARIANT=host` (Sysadmin engine) and `HALBERT_VARIANT=home` (Sentient home companion), complete with dynamic port mapping, isolated data homes, and UI instance switching.
2. **Wyoming Voice Agent (Phase 4):** Full-duplex TCP voice server implementing the Wyoming protocol for zero-latency Home Assistant Voice Assistant integration.
3. **Temporal Cognition & Behavior Modeling (Phase 2):** `TimelineStore`, `OccupancyModel`, `BehaviorStore`, and `PatternInferrer` for continuous episodic awareness.
4. **Frigate NVR & Local Computer Vision:** Asynchronous camera snapshot ingestion, local CV inference (`VisualWatcher`), proactive visual event bus, and 7-day disk-cached episodic visual memory.
5. **Home Assistant Bridge & HACS Custom Integration (Phase 3 & 6):** Bidirectional WebSocket bridge, Assist API tools, and SourcePrep HA configuration graph indexing.

The reviewing model (**Fable**) must scrutinize the Phase 7→8 transition, audit the model routing logic, verify the Wyoming async event loop, and review the spatial reasoning architecture.

---

## 2. Planning & Design Documents (Past 2 Weeks)

| Document | Purpose | Key Themes |
|---|---|---|
| [`.handoff/HOME-AUTOMATION-DESIGN-2026-08-27.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-DESIGN-2026-08-27.md) | Comprehensive Sentient Home Architecture | Cognitive loop, area awareness, behavioral modeling, Wyoming audio, safety gates |
| [`.handoff/HOME-AUTOMATION-IMPLEMENTATION-STRATEGY.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HOME-AUTOMATION-IMPLEMENTATION-STRATEGY.md) | 8-phase execution roadmap | Phased milestone plan, dependency ordering, verification criteria |
| [`.handoff/SENTIENT-HOME-GAP-ANALYSIS.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/SENTIENT-HOME-GAP-ANALYSIS.md) | Architectural gap audit | Identity isolation, spatial entity-camera fusion, semantic visual memory, physical safety |
| [`.handoff/PHASE7-8-TRANSITION-REVIEW-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/PHASE7-8-TRANSITION-REVIEW-2026-08-29.md) | Phase 7 audit & Phase 8 plan | Model routing corrections, light variant blueprint, founder questions |
| [`.handoff/HALBERT-VISION-INTEGRATION-PLAN-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/HALBERT-VISION-INTEGRATION-PLAN-2026-08-29.md) | Vision subsystem architecture | Standalone VisualWatcher, proactive bus, episodic disk cache, consent gates |
| [`documentation/playbooks/SENTIENT-HOME-INTEGRATIONS-GUIDE.md`](file:///Volumes/4TB-BAD/Halbert/documentation/playbooks/SENTIENT-HOME-INTEGRATIONS-GUIDE.md) | Operational setup guide | HAOS add-on setup, Frigate MQTT config, Wyoming pipeline linking |

---

## 3. Git History & Code Commits (Past Week: Aug 22 – Aug 29)

| Commit | Date | Summary | Key Files Changed |
|---|---|---|---|
| `2a02280b` | 2026-08-29 | Phase 0: BeingConfig variant/autonomy fields, AutonomyGate, HomeCognitiveLoop | `config/being_config.py`, `home/autonomy.py`, `home/loop.py` |
| `2e54bf0b` | 2026-08-29 | Prefer BeingConfig overrides over env vars | `integrations/cognition_wiring.py` |
| `62b76f1b` | 2026-08-29 | Fix platform.py missing os import + Python 3.9 type hint compat | `platform.py` |
| `430e65ce` | 2026-08-29 | Phase 2: TimelineStore, OccupancyModel, BehaviorStore, PatternInferrer | `home/timeline.py`, `home/occupancy.py`, `home/behavior.py` |
| `358db8d4` | 2026-08-29 | Phase 3: SourcePrep HA config bridge, awareness tools, API routes | `home/bridge.py`, `home/tools.py`, `dashboard/routes/home.py` |
| `ad028ac3` | 2026-08-29 | Phase 4: Wyoming voice agent TCP server for HA voice pipelines | `voice/wyoming_agent.py`, `tests/test_wyoming_agent.py` |
| `6a64779d` | 2026-08-29 | Phase 6: HACS custom integration + Assist API tools | `custom_components/halbert/`, `home/assist_tools.py` |
| `137f8468` | 2026-08-29 | Phase 7: Multi-instance isolation + UI instance switching | `platform.py`, `app.py`, `InstanceSwitch.tsx`, `Layout.tsx` |
| `ad65ed58` | 2026-08-29 | Multi-instance scrutiny pass: HALBERT_VARIANT gating + os import fix | `app.py`, `routes/instance.py` |
| `067855c0` | 2026-08-29 | Add Frigate NVR integration, local CV pipeline, MCP camera gate | `vision/frigate_client.py`, `vision/inference.py` |
| `9c761a02` | 2026-08-29 | Fix critical bugs found in scrutiny audit of Frigate, CV, and MCP | `vision/watcher.py`, `vision/frigate_client.py` |
| `69a23215` / `73482a27` | 2026-08-29 | Event-driven vision integration: proactive monitoring, intent capture | `vision/watcher.py`, `agents/state_machine.py` |
| `16c1b914` | 2026-08-29 | Docs: update Phase 7→8 handoff — code audit, model recommendations | `.handoff/PHASE7-8-TRANSITION-REVIEW-2026-08-29.md` |
| `b398d5a8` | 2026-08-29 | Fix: update tests for credentials_admin role + home-ops/frigate-ops skills | `skills/builtin/home-ops/`, `skills/builtin/frigate-ops/` |

---

## 4. Key Files & Architectural Components

- **Home Cognition & State Models:**
  - [`halbert_core/halbert_core/home/loop.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/home/loop.py)
  - [`halbert_core/halbert_core/home/timeline.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/home/timeline.py)
  - [`halbert_core/halbert_core/home/occupancy.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/home/occupancy.py)
  - [`halbert_core/halbert_core/home/behavior.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/home/behavior.py)
  - [`halbert_core/halbert_core/home/autonomy.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/home/autonomy.py)
- **Voice, Vision & Integrations:**
  - [`halbert_core/halbert_core/voice/wyoming_agent.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/voice/wyoming_agent.py)
  - [`halbert_core/halbert_core/vision/frigate_client.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/vision/frigate_client.py)
  - [`halbert_core/halbert_core/vision/watcher.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/vision/watcher.py)
  - [`halbert_core/halbert_core/home/bridge.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/home/bridge.py)
- **Instance Isolation & Frontend:**
  - [`halbert_core/halbert_core/dashboard/routes/instance.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/instance.py)
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/InstanceSwitch.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/InstanceSwitch.tsx)

---

## 5. Incomplete Work & Open Items

1. **Bug Identified in Phase 7 Audit (`PHASE7-8-TRANSITION-REVIEW-2026-08-29.md` §1.3):** `HALBERT_MODEL` env var is not currently threaded into `cognition_wiring.py` and `model/client.py`, causing model overrides to fall back to defaults under specific CLI launches.
2. **Missing `BeingConfig` YAML Fields:** `scene_context`, `variant`, and `ha_url` currently rely on environment variables rather than being serializable in `being.yml`.
3. **Phase 8 Implementation (Light Variant & Menu Bar Companion):** Build the lightweight packaging mode for macOS App Store compliance (`ai.halbert.home`), removing heavy local indexing engines in favor of connecting to an existing backend daemon.
4. **Spatial Entity-Camera Fusion:** Finalize auto-mapping of Home Assistant Area entities with Frigate camera detection zones into a unified spatial graph.

---

## 6. Review Directives for Fable

- **Wyoming Concurrency Audit:** Inspect `wyoming_agent.py` for audio buffer overflows, socket closure leaks, and pipeline cancellation during concurrent speech events.
- **Autonomy Enforcement:** Scrutinize `home/autonomy.py` and `AutonomyGate`. Verify that physical actuators (locks, garage doors, high-draw appliances) strictly enforce human confirmation tiers.
- **Multi-Instance Isolation Integrity:** Ensure `HALBERT_DATA_DIR` and `HALOYSIUS_DATA_HOME` never collide across simultaneous host and home daemon processes running on the same machine.
- **Verification Command:** Run `pytest halbert_core/tests/test_home_*.py halbert_core/tests/test_wyoming_agent.py halbert_core/tests/test_multi_instance.py -v`.
