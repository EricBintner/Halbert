# VALIDATION: Integrity Phase 0 and the model-licensing mitigation — six days on

**Date:** 2026-09-08
**Validates:** the 2026-09-02 session — `REVIEW-CRYPTOGRAPHIC-IDENTITY-AND-MERKLE-MEMORY` → Phase 0 of `haloysius.integrity`; the XTTS-v2 withdrawal and `MODEL-LICENSING-POLICY`
**Against:** `main` @ `60708dc` (62 commits since the session's last push, `bcf7b58`)
**Suite:** 64,197 passed (was 63,419 at ship)

---

## 0. Verdict

| Question | Answer |
| :--- | :--- |
| Is the code complete against the goals designed on 2026-09-02? | **Yes for every Phase 0 item.** One goal was met by a different mechanism than designed (§1, "standalone value"). |
| Is it being used correctly beyond Halbert? | **Halbert: yes, faithfully. Halley: yes, and they corrected us. BrightestMinds: unaffected, and under the corrected policy nothing is required of them.** |
| Does recent / in-flight work need to interface with it? | **Yes — five points (§3).** None is a conflict today; two become live at Phase 1; one (soft delete) contradicts decision D3 now. |
| Did the session leave errors behind? | **Yes, three, all fixed this pass (§5):** the policy's missing first question, a factually wrong escalation to Halley, and a wrong licence cell in the legal-review doc. |

---

## 1. Phase 0 goals vs. delivered (from the review, §5)

| Goal | Status | Evidence |
| :--- | :--- | :--- |
| 0.1 `canonical.py` — JCS + NFC + integer millis | ✅ | 27 tests; NFD/NFC divergence and float rejection covered |
| 0.2 `eventlog.py` — append-only, chain continuous across shards, persisted head, atomic append | ✅ **and hardened since** | `7b1ddc0` per-directory lock + `flock` (Halbert's `INTEG-06`: 24 concurrent appends produced 46 false problems); `4766b5e` / `c7a1353` an interrupted append is recovered, not reported as tampering; `b3cce58` `seqs_where` + `erase_many`. 694 lines, 3 new test files |
| 0.3 `SigningBackend` seam | ✅ | `seam.py:785`, in `__all__`; Halbert implements it (`crypto/storage.py:397`) |
| 0.4 `identity.py` — `did:key`, pluggable curve, software signer | ✅ | `z6Mk…` / `zDn…` prefixes match the W3C spec; P-256 varint prefix `0x8024` |
| 0.5 `[crypto]` extra, lazy imports | ✅ **re-verified today** | clean py3.11 venv, `cryptography` and `base58` blocked: import OK, unsigned log verifies, zero third-party modules loaded |
| "Standalone value: an atomic append-only log replaces the non-atomic `memories.json` rewrite" | ⚠️ **goal met, mechanism differs** | EN-2 (`c003f15`) made `PersonaMemoryStore._save_to_disk` atomic (temp + fsync + rename) — its docstring credits "the hazard the engine's own `integrity/eventlog.py` docstring names". `EventLog` itself is **not wired into the store**; nothing inside the engine consumes it. Consumers do (Halbert's audit log). The primitive's documentation carried the fix, which is a legitimate outcome, but the review's framing implied the log itself would land in the store. It did not, and does not need to. |

Deferred by design and still deferred: Phase 1 (signed peer writes), Phase 3 (Merkle with peer co-signed roots).

---

## 2. XTTS / licensing goals vs. delivered

| Goal | Status | Evidence |
| :--- | :--- | :--- |
| No Haloysius doc *instructs* XTTS-v2 | ✅ (one residue fixed today) | `RESEARCH-VOICE-MODALITY-CITATIONS.md:162` still listed XTTS-v2 as an example `VoiceBackend` engine — corrected in place |
| `TTSConfig.xtts_*` → `voice_clone_*`, legacy env honoured | ✅ | 10 tests; **Halley mirrored it with their own tests** (`tests/test_tts_config.py:105-113`) |
| Policy gate exists and is adopted | ✅ adopted — ❌ **structurally wrong**, fixed | Halley and Halbert adopted it; Halley's reply showed it never asked whether the product ships weights. Corrected `60708dc` |
| Escalation to Halley (§5 of the handoff) | ❌ **wrong on two counts**, withdrawn | See §5 |
| CHANGELOG / handoff index | ❌ **never written**, fixed | Neither the integrity package nor the rename had a changelog line; none of the four docs was indexed. `60708dc` |

---

## 3. Recent and in-flight work that interfaces with this session

**3.1 EN-1 write-time provenance ↔ `author_did` (interface at Phase 1).**
`a6f827f` gives every memory a closed-vocabulary provenance coerced from `source`; the store refuses unclassifiable writes. That provenance is **self-asserted by the writer**. `author_did` is its verifiable counterpart across bodies: once peer writes are signed (Phase 1 §2.1), a receiving body can check that a record claiming `user` provenance was authored by the body the user was actually talking to. Not a conflict today (one trust domain); it is the natural place Phase 1 should plug in, and the OpenClaw second-guess doc's "provenance guard" (`Gap 3`) is the same concern from the promotion side.

**3.2 EN-2 `recall_events` is a second event store, unchained and unsalted.**
`memory_v2/recall_events.py` (`c003f15`) is an append-only SQLite table keyed by `sha256(content.strip().lower())[:16]` — a truncated, unsalted content hash. Its docstring cites `integrity/eventlog.py` as a house pattern but takes no dependency on it. That is fine: it is local-only (`peer_backend.py` does not sync it), fail-soft, and tamper-evidence was never its purpose. **One note against decision D3:** those hashes are brute-forceable for low-entropy content; if recall events are ever synced or exported, salt them or exclude them.

**3.3 Erasure now has three shapes, and one contradicts D3.**

| Path | What "forget" does | D3-consistent? |
| :--- | :--- | :--- |
| `EventLog.erase()` | drops payload + salt; commitment and chain intact | ✅ |
| `ObservationStore.delete()` (`2648e72`) | hard delete, `PRAGMA secure_delete`, tombstone refuses re-save | ✅ |
| `PersonaMemoryStore.delete(soft=True)` | sets `metadata["deleted"]=True`; **content stays in `memories.json`** | ❌ |

The default (`soft=True`) leaves the forgotten text on disk. Recommend the memory-program owner have soft delete blank `content` (keeping id + tombstone, matching the observation-store precedent) or route "forget" to hard delete.

**3.4 Hermes write-approval staging ↔ `EventLog` (forward note).**
`HERMES-INPUTS…` §47 proposes staged writes (`pending/…`) with fail-closed commit detection as the governance shape for Option C. `EventLog`'s `kind` + `author_did` + chain is a ready substrate — append `write.proposed`, later `write.approved` — with the audit trail for free. Nobody has proposed it; recording the fit.

**3.5 `REPLY-OSS-RESEARCH-PROGRAM`** cites the eventlog docstring as evidence of the durability bug (§86) and lists `integrity/` in the subtractive-contract set (§59). Consistent with §1 above.

**No interface:** the warrant work (`a8fb6ef`) — "authority" there is consent-role authority; the warrant handoff already separates three senses of the word, and cryptographic attribution would be a fourth to keep apart. `attunement/ledger.py` borrows the eventlog's lock discipline and nothing else.

---

## 4. Consumer uptake beyond the handoff's target

**Halbert — faithful and complete for Phase 2.** `obs/audit.py` rebuilt on `EventLog` with the chain continuous across day and tool boundaries and a persisted head ("the failure mode an audit log exists to catch"); `crypto/storage.py` custody ladder exactly as specified — hardware seam → Keychain → Secret Service → `0600` file with OpenSSH-style permission refusal, WARNING on downgrade; `audit-verify`; signing **opt-in** (`INTEG-03`: resolving a signer creates a key on the machine, which a tool call must not do unannounced — a better call than the handoff made); no "verified" badge (`INTEG-05`). They found the append race (`INTEG-06`) and it was fixed upstream. `continuity/provenance.py` joins audit and state on `request_id`, explicitly *not* on event seq. **Blocked on Haloysius Phase 1 §2.1** for per-body identity (their ROADMAP, TRUST-1). Distribution posture (does the Tauri app bundle weights?) is unverified — the one gap.

**Halley — adopted, then corrected us.** Rename mirrored with tests; XTTS stub deleted; default voice moved from `en_US-amy-medium` (licence unknowable) to `en_US-libritts_r-medium` (MIT); Chatterbox + Kokoro spike queued. Their reply (`HANDOFF-TO-HALOYSIUS-LICENSING-CORRECTIONS-2026-09-02.md`) is right and was unanswered for six days — see §5. Their one remaining engine-side ask is real: **`ProsodyTTSRequest` carries only `noise_scale`**, so `expression_tokens` / `cadence_style` / `whisper` never reach *any* engine through the reference adapter — including the Chatterbox spike we recommended. Small fix; unblocks expressive engines.

**BrightestMinds — no engagement, nothing required.** Same BYOM posture (0 tracked weights, no installer, runtime `hf_hub_download` of SDXL and FLUX.1-schnell); `TTSConfig.from_env()` unaffected by the rename; `list_voices()` enumeration is fine under the corrected policy. Recommend a one-line posture record in the policy table; nothing more.

---

## 5. Corrections made this pass — `60708dc`

1. **Policy asked the wrong first question.** Added "does the product ship the weights?" as gate step 0; added ⚪ *unknowable*; corrected the §4 table (no wired `FLUX.1-dev`; `FLUX.2-dev` user-supplied; `FLUX.1-pro` 0 in live code; Piper voices user-supplied); added a per-app posture table.
2. **Escalation to Halley withdrawn in place.** Two errors, either fatal: they ship no weights, and the variant claim did not survive contact with their code. Reference counts are not evidence of what ships; `git ls-files` and the installer manifest are.
3. **`LICENSING-REVIEW.md` §1** called the heavyweight consumer GPL-3.0. It was never; the file was unfilled boilerplate from a tooling import, since deleted. Dated corrections block added (also notes Haloysius's completed Apache-2.0 relicense).
4. CHANGELOG entries and handoff-index sections 1f / 1g.
5. `RESEARCH-VOICE-MODALITY-CITATIONS.md` example-engine list.

---

## 6. Open, ranked

1. **Phase 1 — signed peer writes (Haloysius).** Blocks Halbert's per-body identity; the highest-value item in the programme. Timestamp + nonce, host rejects stale/replayed. Two-sided with Halbert's canonical host.
2. **`ProsodyTTSRequest` fields** — optional `expression_tokens`, `cadence_style`, `whisper`; Piper ignores via `getattr`. Unblocks Halley's spike.
3. **`PersonaMemoryStore.delete(soft=True)` leaves content on disk** — D3.
4. **Halbert distribution posture** — verify before a release ships an installer or add-on image.
5. **`recall_events` hashes unsalted** — only if ever synced.
6. Phase 3 Merkle — after 1.

---

## 7. Evidence

- Full suite: `64,197 passed` (`pytest src/haloysius -q`).
- Integrity + TTS + recall-events + observation-store + compression: `192 passed`.
- Subtractive contract: clean py3.11 venv, `sys.modules['cryptography']=None`, `['base58']=None` → import OK, unsigned verify OK, no third-party modules loaded.
- Halley's claims verified in their tree: tracked weight files 0; `installers/` weight files 0; every `hf_hub_download` call takes a user-configured id; hardcoded ids: `FLUX.1-schnell` ×4, `FLUX.2-klein-4B`/`-9B`, `diffusers/FLUX.2-dev-bnb-4bit` ×1; the only `FLUX.1-dev` in live `.py` is a log line advising against it; root `LICENSE` absent.
- BrightestMinds: tracked weight files 0; no installer dir; `stabilityai/stable-diffusion-xl-base-1.0` ×2, `black-forest-labs/FLUX.1-schnell`.
