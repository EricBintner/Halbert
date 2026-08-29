# Review Packet 01: Security Architecture, Trust Boundaries & Sensitivity Classification

**Review Level:** **Fable Level Review**  
**Domain:** Security Architecture, Secret Redaction, Sensitivity Classification, MCP Gateways, and Cryptographic/Policy Boundaries  
**Target Date:** 2026-08-29  
**Status:** Ready for Deep Security & Architectural Review  

---

## 1. Executive Summary & Review Scope

Over the past week (2026-08-22 to 2026-08-29), Halbert underwent a massive security hardening phase. This effort established a multi-tiered trust boundary preventing sensitive host credentials and private configuration secrets from leaking into untrusted LLM contexts, MCP tool egresses, or remote cloud providers.

A critical milestone during this period was the **Tier 2 Recalibration**: converting policy-based credential checks into strict **architectural guarantees** (secrets never leave the local tool sandbox during `describe_secret`). In parallel, a full visual redesign of the **Security Settings Tab** was executed per the Daylight Mid-Century Modern design system, complete with live telemetry, volatile TTL unlocking, and high-friction phrase confirmation.

The reviewing model (**Fable**) must evaluate the airtightness of these trust boundaries, verify that no leakage pathways exist across context assembly or tool calls, check the correctness of regex and entropy filters, and identify any remaining incomplete work.

---

## 2. Planning & Design Documents (Past 2 Weeks)

| Document | Purpose | Key Themes |
|---|---|---|
| [`.handoff/SECURITY-REVIEW-REQUEST-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/SECURITY-REVIEW-REQUEST-2026-08-29.md) | Initial security review request & threat model | Sensitive file enumeration, redaction backstop, multi-tier trust gates |
| [`.handoff/TIER2-RECALIBRATION-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/TIER2-RECALIBRATION-2026-08-29.md) | Architectural guarantee specification for Tier 2 secrets | Removal of network breach checks from `describe_secret`, metadata-only responses |
| [`.handoff/SECURITY-TAB-VISUAL-DESIGN-AND-HANDOFF-2026-08-29.md`](file:///Volumes/4TB-BAD/Halbert/.handoff/SECURITY-TAB-VISUAL-DESIGN-AND-HANDOFF-2026-08-29.md) | Component spec for Security UI | Daylight design tokens, mechanical rocker switches, live telemetry bar, volatile TTL unlock |
| [`documentation/legal/SECURITY.md`](file:///Volumes/4TB-BAD/Halbert/documentation/legal/SECURITY.md) | Public security policy & disclosure framework | Reporting vulnerabilities, trust boundaries, open-core guarantees |

---

## 3. Git History & Code Commits (Past Week: Aug 22 – Aug 29)

| Commit | Date | Summary | Key Files Changed |
|---|---|---|---|
| `61911756` | 2026-08-28 | Add `credentials_admin` scope — close trust boundary hole | `config/being_config.py`, `dashboard/routes/settings.py` |
| `e6ce6bad` / `483a5b52` | 2026-08-28 | Known-prefix and high-entropy backstop for bare secrets | `config/redactor.py`, `tests/test_redactor.py` |
| `fd098521` | 2026-08-28 | Secure content routing: two-part detector + cloud fallback | `agents/router.py`, `context/assembler.py` |
| `e807e449` | 2026-08-28 | Context-assembly secure content backstop | `context/assembler.py`, `tests/test_assembler.py` |
| `d8b5cdcd` | 2026-08-28 | Config query layer, sensitivity classifier, deterministic responder | `config/classifier.py`, `config/responder.py` |
| `57477399` | 2026-08-28 | Token format identification & format database | `config/format_db.py`, `tests/test_format_db.py` |
| `5a99e8af` | 2026-08-28 | Credential validation (opt-in API checks) | `config/credential_validation.py` |
| `3a0f890e` | 2026-08-28 | Compromise detection (HIBP password + GitHub secret scanning) | `config/compromise_detection.py` |
| `145390ba` | 2026-08-28 | Dynamic prefix database fetcher | `config/dynamic_prefix.py` |
| `b6333b63` | 2026-08-28 | Implementation gaps: scanner gating, escape hatch, base64/JSON | `discovery/engine.py`, `config/classifier.py` |
| `f58bd9a0` | 2026-08-28 | Cross-file secret correlation + HTTP transport hardening | `config/correlation.py`, `dashboard/app.py` |
| `784009b6` | 2026-08-28 | Tier 2 recalibration research & plan | `.handoff/TIER2-RECALIBRATION-2026-08-29.md` |
| `9fa8068e` | 2026-08-29 | Tier 2 recalibration: enforce architectural guarantee on `describe_secret` | `config/classifier.py`, `tests/test_tier2_guarantee.py` |
| `b10c0707` | 2026-08-29 | Update Tier 2 recalibration handoff with actual code state | `.handoff/TIER2-RECALIBRATION-2026-08-29.md` |
| `92ccf9e1` | 2026-08-29 | Per-key cloud escape hatch card in Security settings tab | `dashboard/frontend/src/components/SecurityComponents.tsx` |
| `082e8d3b` | 2026-08-29 | Redesign security tab per Daylight Mid-Century Modern design system | `pages/Settings.tsx`, `components/SecurityComponents.tsx` |
| `67b174e0` | 2026-08-29 | Fix scrutiny issues: wire TTL, guard null, validate lists, recurse telemetry | `dashboard/routes/settings.py`, `components/SecurityComponents.tsx` |
| `b3f39c5e` | 2026-08-29 | Security scrutiny round 2: runtime TTL, concurrency, ARIA, polling | `dashboard/routes/settings.py`, `components/SecurityComponents.tsx` |
| `b398d5a8` | 2026-08-29 | Update tests for `credentials_admin` role + home-ops/frigate-ops | `tests/test_security_roles.py` |

---

## 4. Key Files & Architectural Components

- **Core Sensitivity Classifier & Secret Redaction:**
  - [`halbert_core/halbert_core/config/classifier.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/classifier.py)
  - [`halbert_core/halbert_core/config/redactor.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/redactor.py)
  - [`halbert_core/halbert_core/config/format_db.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/format_db.py)
  - [`halbert_core/halbert_core/config/dynamic_prefix.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/config/dynamic_prefix.py)
- **Context Assembly & Routing Safeguards:**
  - [`halbert_core/halbert_core/context/assembler.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/context/assembler.py) (Backstop leak detector)
  - [`halbert_core/halbert_core/agents/router.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/agents/router.py) (Secure content routing & local model fallback)
- **Frontend Security UI & Controls:**
  - [`halbert_core/halbert_core/dashboard/frontend/src/components/SecurityComponents.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/components/SecurityComponents.tsx)
  - [`halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/src/pages/Settings.tsx)
  - [`halbert_core/halbert_core/dashboard/routes/settings.py`](file:///Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/routes/settings.py)

---

## 5. Incomplete Work & Open Items

1. **CLI Script Migration:** `config/credential_validation.py` and `config/compromise_detection.py` were decoupled from `describe_secret` (Tier 2 recalibration), but still sit in `config/`. They need to be packaged as standalone human-run CLI commands (`halbert-check-credential`, `halbert-check-breach`) in `pyproject.toml` console scripts.
2. **Unredacted SourcePrep Indexing (Operational Gate):** Run `register_host_project(redact=False)` to stage raw files, populate canon DB, and trigger an unredacted SourcePrep index rebuild while verifying that both egress gates (MCP tool boundary and secure model routing) protect raw keys.
3. **Live Scanner Egress Testing:** Run automated integration tests with mock API keys across all macOS discovery scanners (`system_profile.py`, `keychain_scanner.py`, etc.) to prove zero raw credential egress.

---

## 6. Review Directives for Fable

- **Architectural Guarantee Check:** Audit `describe_secret` in `classifier.py` and `mcp/server.py`. Ensure no code branch can trigger network requests or return plaintext secret values under any configuration state.
- **Shannon Entropy & Regex Backstop:** Review `redactor.py` calculations for false positive/negative trade-offs on high-entropy strings (e.g. UUIDs, base64 hashes, SSH keys).
- **TTL Expiry & Volatile State:** Audit `dashboard/routes/settings.py` and `SecurityComponents.tsx` to ensure volatile unlock tokens automatically expire and relock without lingering in browser localStorage.
- **Verification Command:** Run `pytest halbert_core/tests/test_tier2_guarantee.py halbert_core/tests/test_redactor.py halbert_core/tests/test_security_roles.py -v`.
