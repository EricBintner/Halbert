# pytest triage — main @ 4a7bf71f, 71 failures (2026-09-01)

Totals: REAL 38 (F2 33, F1 2, licence gate 2, peerApi 1) | ENV 13 (cv2; CI lacks `vision` extra too) | TEST ROT 10 | ORDER 10 | UNKNOWN 0

Per file:
- test_cognition_tick_once (10), test_agent_memory (10), test_state_machine (2), turn_lock 6/7, turn_persistence 3/4, meta_tools 2/5 → REV-06 F2: `response_modality` UnboundLocalError, state_machine.py:2743 assigned only inside `if self.prompts:` but read at :2761 in else. Fix: hoist `response_modality = "text"`. Commit 2f595bc0 (08-30). Deterministic — NOT order-sensitive. Production get_agent() always wraps AgentPromptBuilder so dashboard unaffected; CI signal for agent core destroyed.
- test_thread_e2e (2) → REV-06 F1: stale instance-level `_defanged_query` (state_machine.py:1519 read, :2701 reset too late, :2724 set). Turn-2 planning uses turn-1's question. LIVE when modality engine importable (it is). Commit 0a2c3dfd.
- turn_lock TestTerminalSessionIds, turn_persistence test_end_turn_receives_text_blocks_terminals_status, test_terminal_e2e (1) → TEST ROT: fake_execute() lacks new `speaker_role` kwarg (state_machine.py:2364; commit 58adce12).
- meta_tools 3 → TEST ROT: tests pin CRAG kwargs {model_override, tier_override}; code also passes `secure=` (state_machine.py:1739, :2578; 4db888a9).
- test_cv_extensions (11), test_vision_tools (2) → ENV: `import cv2` missing; opencv only in `vision` extra (pyproject:95-97); CI installs [dashboard,dev] (ci.yml:214) → red in CI since 067855c0 (08-29).
- test_corpus_license_gate (2) → REAL: config/dependency-licenses.yml missing 8 deps (mss, opencv-python, sherpa-onnx, openwakeword, pyacoustid, cpal, webrtc-audio-processing, @halbert/design-system, @halbert/model-picker) + scripts/check_appstore_deps.py:74-86 parses self-referential extras `halbert-core[dashboard]` as deps. Blocks App Store gate. Founder sign-off needed on licence classes (opencv bundles FFmpeg; pyacoustid needs chromaprint).
- test_frontend_no_relative_urls (1) → REAL: frontend/src/lib/peerApi.ts:122 `API_BASE=''` → 9 bare fetch('/api/peers|fleet…') :151-229 bypass apiBase → 404 inside Tauri webview (Settings→Devices pairing, peer list, fleet telemetry). Commit 928c9166. Second hit StandbyController.tsx:76 is a false positive.
- test_llm_routes (4), test_llm_config_layers (2) → ORDER: polluter test_agent_model_override.py (`slots` fixture) → has_capability(CAP_SECURE_MODEL) probes real CapabilityRegistry singleton (capabilities.py:348-367, never reset) which reads developer's REAL models.yml (apple-foundation secure endpoint 127.0.0.1:11435). Fix: autouse reset_registry() fixture. Commits 330f641b/09ec6eb7.
- test_peer_tool_proxy (4) → ORDER: sync tests use asyncio.get_event_loop().run_until_complete (test:264-301) with asyncio_mode=auto → no current loop after any async test. Test bug. ffe74bdd.
- test_llm_config_parse_cache (2) → TEST ROT: extra parses are being.yml (routes/agent.py:487 per-turn load_being_config; capabilities.py:266/:276/:119) not models.yml.
- test_llm_discover (1) → TEST ROT: discover_local_engines now returns apple_foundation too (routes/llm.py:939-966); 944422d7.
- test_multi_instance (1) → TEST ROT: role derives from _get_variant() not HALBERT_PERSONA_ID (instance.py:31-38, REV-03 F8); 7d01720e.

HIDDEN (not in the 71): Apple Intelligence auto-provisioning can never fire on a fresh install — auto_provision.py:72-83 and routes/llm.py:219 gate on has_capability(CAP_SECURE_MODEL) whose probe (capabilities.py:192-204) = "secure_model slot already configured" → chicken-and-egg. test_auto_provision.py fails 4/11 SOLO, passes in full run only via registry pollution. CI red set differs from local.

REV-06 coverage: F2, F1, O4 documented; 34 tests + 1 hidden are new/undocumented.

Shipped-but-broken: F1 prompt leak; Tauri peer/fleet API bare URLs; Apple Intelligence auto-provision self-gated; App Store licence gate red; CapabilityRegistry singleton never reset; CI never installs vision extra (13 red since 08-29).
