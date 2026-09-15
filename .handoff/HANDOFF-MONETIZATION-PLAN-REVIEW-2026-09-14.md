# Handoff — Thorough Monetization Plan Review

**Date:** 2026-09-14
**From:** v10 marketing factual-review session
**To:** Review AI (next session)
**Status:** SUPERSEDED-BY `.handoff/RESULTS-MONETIZATION-PLAN-REVIEW-2026-09-14.md`
**ROADMAP linkage:** gates `DIST-1` §4 bullet "Halbert Pro" (blocked on `FDR-04`); this review is the input that unblocks it.

---

## 1. Why this handoff exists

The v10 marketing factual review (`.handoff/RESULTS-MARKETING-V10-FACTUAL-REVIEW-2026-09-14.md`, §F3) found
the website and durable legal docs stating Halbert Pro commercial terms as present fact
(Merchant of Record live, "up to 3 personal devices per license") while `DECISIONS.md` `FDR-04` is **open** — three
conflicting draft numbers existed and none was decided. The founder's response:

1. The **3-device limit is outdated** — any licence should allow **at least 5, maybe 10** devices.
2. "I honestly don't remember what we landed on" — so this session should not guess. Examine the whole monetization
   plan thoroughly and **get back to the founder with a recommendation**.

The site has been made truthful in the meantime (future tense, no device number); nothing in this handoff
depends on a website change. The task here is the **commercial plan itself**.

## 2. What to examine (the evidence base)

Read these before forming anything:

| Doc | What it holds |
|---|---|
| `DECISIONS.md` — `FDR-04` row | The open decision verbatim: price, update window, renewal, refund policy, device count; blocks Phase B (Ed25519 keys, Sparkle, Lemon Squeezy) |
| `DECISIONS.md` — `FDR-09` row | External infra still to enroll: Apple Developer Program, Developer ID + MAS certificates, Lemon Squeezy product/webhook, `halbert-ha-addon` repo |
| `DECISIONS.md` — 2026-09-04 macos-pro row | The channel/product distinction: the channel can build and pass gates "before its product has commercial terms — which is the state today" |
| `.handoff/TASK-PACKET-06-FOUNDER-DECISIONS-AND-APPSTORE-LEGAL.md` | The "$29 one-time perpetual ($24 launch promo) + 12-month update window" draft |
| `documentation/legal/OPEN-CORE-AND-DISTRIBUTION-STRATEGY.md` | Where the paid line can go: the signed/notarized/auto-updating binary + update stream (Ardour/Krita model); per-feature gating of GPL core is not durably enforceable |
| `documentation/legal/APP-STORE-DISTRIBUTION-STRATEGY.md` | §7 exception, App Store companion boundary (FDR-07: sandboxed remote companion) |
| `ROADMAP.md` §3 `DIST-1`, §4 | Channel buildability state and what blocks Pro (Ed25519 offline licence verification, Sparkle, real notarization run) |
| `documentation/legal/LEGAL-AND-LICENSING-TODO.md` | Any further commercial open items |

Also verify current state, don't take the docs' word: check `scripts/build-macos.sh`, `config/platforms.yml`,
and whether any licence-check code exists on any ref (`grep -ri "license" halbert_core/halbert_core/licensing/`
or wherever it would live) — the Ardour model means the free binary and Pro binary differ by signature/update
stream, and **feature gating of GPL core is off the table** (2026-09-04 paid-line mechanism constraint, binding).

## 3. The founder's stated direction (2026-09-14, this session)

- **Device count: minimum 5, preferred 10** — the 3-device draft is explicitly outdated.
  Justify the final number against comparable licences (Ardour's "one user, any machines you own",
  Krita, Sketch's device model, JetBrains's licensed-until model, etc.) and against the reality that
  Halbert is inherently multi-machine (federation/peers is a headline feature — a *host custodian* on
  5+ boxes is the normal case, not piracy; a punitive device count fights the product's own distributed story).
- **No decision on price** — re-derive from scratch; the $24–$29 drafts are inputs, not anchors.
  Note the drafts said "one-time perpetual with 12-month update window"; check whether that model
  still fits (Sparkle update-stream enforcement, renewals, refund policy all hang off it).
- **MoR assumption: LemonSqueezy** stands unless the review finds a reason it shouldn't (fees,
  longevity risk, VAT coverage, webhook maturity). If recommending a change, show the numbers.

## 4. What the review should produce (get back to the founder)

A written recommendation, in a `RESULTS-` or `DECISIONS-` ready form, covering:

1. **Device count** — final number with rationale (5 vs 10 vs "all machines you administer"),
   and the exact licence-grant wording that would implement it.
2. **Price model** — one-time perpetual + update window vs subscription vs hybrid; launch-promo
   stance; what each implies for Ed25519 licence keys and the Sparkle update stream.
3. **Update-window mechanics** — how a buyer keeps entitlement after the window lapses
   (Ardour model: last-paid-for version keeps working forever — confirm that's the intent).
4. **Refund policy** — concrete terms.
5. **Free/Pro boundary** — restated in one paragraph consistent with the binding 2026-09-04
   mechanism constraint (paid artifact = signed binary + update stream; no GPL-core feature gating).
6. **App Store companion** — price (free? paid?) and its relationship to Pro (FDR-07 boundary:
   the App Store build is a sandboxed remote companion, never a local admin).
7. **MoR confirmation** — LemonSqueezy yes/no, with fee/latency/exit-cost analysis.
8. **What FDR-04's ratification text should say**, verbatim, so the founder can paste it into
   `DECISIONS.md` and unblock Phase B (Ed25519 keys, Sparkle, Lemon Squeezy product).

Constraints to respect while writing it:

- Halbert is GPL-3.0-or-later with the App Store §7 exception (`LICENSE-EXCEPTION-APPSTORE`) —
  no pricing model may assume per-feature gating of GPL core code.
- The product's distributed story (many machines, one intelligence) argues *for* generous device
  counts; a restrictive count is both user-hostile and off-message with the v10 "Independent
  nodes. Shared intelligence." stop.
- No users yet, no migrations, no back-compat shims — greenfield terms.
- Never name or recommend AI models anywhere this plan surfaces publicly; unversioned
  client names are acceptable (sharpened 2026-09-14 — see the RESULTS doc §7).
- The v10 site currently says Pro is "planned; terms not yet final" — once this review lands and
  FDR-04 is ratified, the site, `documentation/legal/TERMS.md` §2.2 and `PRIVACY.md` §4 need one
  coordinated edit back to present tense (they were written future-tense on 2026-09-14 for exactly
  this reason).

## 5. Out of scope

- The email ecosystem (contact addresses, MX, unsubscribe tooling) — separate session.
- Website copy beyond what FDR-04's ratification triggers (see §4 last constraint).
- Linux/flatpak pricing — the drafts were macOS-Pro-shaped; if a Linux paid channel makes sense,
  that's a separate founder decision, but the review may note it as a question.

## 6. Status conventions

Per the handoff rules in `ROADMAP.md`: carry a status from DRAFT / ACTIVE / LANDED / SUPERSEDED-BY /
DEFERRED and the ROADMAP row id (`DIST-1` / `FDR-04`). When the review lands, write a
`RESULTS-MONETIZATION-PLAN-REVIEW-<date>.md` with the recommendation, and update this doc's status
to SUPERSEDED-BY pointing at it.