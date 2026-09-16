# 17 — Voice mark: plucked-string motion model

*Revises design doc 15 §3.3 and the 2026-08-31 "v2 tuning" note in doc 16. Written 2026-09-15.*

## Why this revision

The 2026-08-31 engine gave every tine the **same** spring (`k=120, c=3.5` when
speaking; `k=140, c=18.5` otherwise). Measured impulse response of that spring:
1.74 Hz ring, 0.57 s amplitude decay, identical on all six tines; the
listening/idle spring is near-critically damped (ζ≈0.78) and never rings at
all. Read as motion: one slow wobble everywhere. Nothing about it says "string".

The founder's brief (2026-09-15): the tines must move like plucked strings —
the centre faster and shorter, the outer lines slower and longer; no bounce
easing; higher pitches at the centre, lower at the edges; one implementation
shared by Storybook, the marketing site and the app.

## What a plucked string does (the physics we borrow)

A string fixed at both ends and released from a pluck moves as a sum of modes:

    y(x, t) = Σ_n A_n · sin(nπx/L) · cos(ω_n t) · e^(−t/τ_n)

- Each mode is a **damped cosine in time** on a **fixed shape in space**.
  The nodes do not move. (The old engine drifted the standing-wave phase; a
  string never does.)
- The mode amplitudes fall off as `A_n ∝ sin(nπd/L) / n²` for a pluck at
  distance `d` from the end (Russell, PSU). The fundamental dominates.
- **Higher frequencies decay faster** (`τ_n ∝ 1/n`, and across an instrument
  the thin, high-pitched strings die sooner than the thick bass strings).
- A pluck is a **velocity/displacement impulse**, after which the string is
  free: motion crosses the rest line many times with an exponential envelope.
  This is the property no `cubic-bezier` easing can produce — a cubic can
  overshoot its endpoint once, never oscillate. (If a pure-CSS surface ever
  needs this curve, CSS `linear()` easing can carry a sampled damped cosine
  exactly; the per-frame integrator below draws the same curve.)

Sources: Russell, *The Plucked Fixed-Fixed String* (PSU acoustics demos);
Smith, *Damped Plucked String* (CCRMA, Stanford); Liebman, *Waves part 2:
plucky underline* (`y(t) = 1 − e^(−5t)·cos(2π·8t)`, the "8 Hz, dies in
0.2 s" reference feel); Physics Forums, *Why do harmonics decay faster than
the fundamental?*

## The model

### One string per tine, one mode each

Tine `k` is a damped harmonic oscillator on its own mode shape
(`TINE_MODES`: mode 2 on the spine and first lane, fundamental elsewhere):

    x_k'' = −ω_k² x_k − (2/τ_k) x_k'        ω_k = 2π f_k

Spring form (mass 1): `stiffness = ω_k²`, `damping = 2/τ_k`. Integrated with
the existing fixed 8 ms semi-implicit Euler step (frame-rate independent,
stable at the kiosk's 30 fps dips). No phase drift; nodes are stationary.

### The ladder — pitch falls and sustain grows outward

Both endpoints are constants; intermediate tines are geometric interpolations
so the same rule serves 6 or 10 tines.

| tine (medium) | band the tine listens to | f (Hz) | τ (s) | ζ | cycles to 1/e |
|---|---|---|---|---|---|
| 0 spine | 4–8 kHz air | 8.00 | 0.20 | 0.10 | 1.6 |
| 1 | 1.5–4 kHz | 6.06 | 0.28 | 0.09 | 1.7 |
| 2 | 700–1500 Hz | 4.59 | 0.40 | 0.09 | 1.8 |
| 3 | 350–700 Hz | 3.48 | 0.56 | 0.08 | 2.0 |
| 4 | 100–350 Hz | 2.64 | 0.78 | 0.08 | 2.1 |
| 5 outer arc | 40–100 Hz sub-bass | 2.00 | 1.10 | 0.07 | 2.2 |

Two octaves inner→outer (8 Hz → 2 Hz), the span of a guitar's six strings.
8 Hz at 60 fps is 7.5 frames per cycle — a visible quiver, not a blur. The
outer arc swings ~30 frames per cycle and is still moving a second later.

### Two components per tine: ring + swell

    displacement_k = A_k · ( ring_k + swellWeight · swell_k )

- **ring** — the string above, at rest target 0, excited only by plucks.
  A pluck of amplitude `a` injects velocity `a·ω_k`, so a given strike
  displaces every tine by about the same fraction of its `A_k` regardless
  of pitch (measured: 0.81 at the spine to 0.89 at the outer arc for a unit
  strike — the 8 ms step's residual pitch dependence, within 10%). An
  energy limiter caps `√(x² + (v/ω)²)` at 1.0 at injection time (only `v`
  is clamped, never `x`, so nothing snaps).
- **swell** — the old well-damped follower (`k=140, c=18.5`) of the band
  level, so a sustained vowel still shows as a gentle lean. Weighted per
  state; never above 0.3 in the voiced states. The weight itself glides to
  each state's target with a 120 ms time constant, so speaking → idle
  (0.3 → 1.0) never pops the lean.
- **sensitivity** (the prop) scales the incoming level *before* both
  components — strikes land harder and the lean goes further — so a loud
  strike saturates the string's limiter instead of clipping the drawn path.

`|ring| ≤ 1` and `swell ≤ 0.3` bound the multiplier at 1.3, so the geometry
invariant becomes `1.3·(A_k + A_{k+1}) < inter-lane gap` (test-enforced) and
the amplitude tables are retuned to it.

### Excitation per state

| state | pluck source | gain (displacement per unit level rise) | swell weight | retract | extra |
|---|---|---|---|---|---|
| idle | none from the breathing source | — | 1.0 | 0 | sparse soft plucks: one random tine every 2.5–6 s, amplitude 0.25–0.45, weighted toward the outer (long-sustain) tines |
| listening | — | — | 0 | 1 | the ends withdraw (see *Listening* below); no warp at all |
| recognized | — | — | 0.3 | 1 | on entry (including mounting in it), a **strum**: every tine plucked at 0.7, spine first, 35 ms stagger outward, on the still-withdrawn lines |
| thinking | — | — | 0 | 0 | traveling bulges and the 0.94 contraction, unchanged |
| speaking | band-level onsets | 2.5 | 0.3 | 0 | — |
| error | — | — | 0 | 0 | tint only, unchanged |

**Onset** = a per-frame rise of a tine's band level above 0.02 (mic noise
stays below it). Each rising frame plucks by `gain × rise`; a sharp consonant
lands in two or three frames and sums to one strike, a slow ramp becomes a
slow push that returns when the ramp ends. No edge detector, no latency.

## Listening — retraction, not warping (added 2026-09-16)

Listening had been plucking exactly like speaking. The founder's brief: while
listening the lines do not warp; each line **withdraws its ends** along its
own path in response to sound. Fully withdrawn, a U-line is a dot at its
apex, the outer arc a dot at its lowest point, the spine a dot at the
mark's centre (it withdraws from the top only; its base *is* the centre).
Retraction is a trim of the sampled path (`TinePathOptions.trim`), so it
composes with every warp — recognized strums the withdrawn lines.

Two inputs drive it, and neither is a level meter (`listening.ts`):

| input | what it responds to | how far | timing |
|---|---|---|---|
| **presence** | any sustained sound (loudest band above 0.04) | 10–15 % per end at full attention, each end drifting on its own slow curve (~0.35 Hz, golden-angle phases, outer lines slightly slower) | attention rises with a 150 ms time constant and releases over 1.8 s — the mark keeps listening for a moment after you stop |
| **impact** | a broadband transient: all bands but one rising by more than 0.15 against their level 50 ms earlier (a fixed window, so 30 fps and 60 fps agree). A syllable is a gaussian over the register and lifts at most five of seven bands, however sharp its attack; a clap lifts them all. Strength comes from the mean rise: 0.15 → nothing, 0.65 → full | up to 0.24 per end on the outer line, 0.7 of that on the spine; hard-capped at 0.4 per end, so even the hardest clap at full attention leaves a fifth of every line and about a quarter of the outer arc (test-enforced) — a clap startles, it never closes a line | rises in 30 ms, holds 120 ms (so it actually reaches its target), releases over 0.45 s; critically damped, no ring; all timing on elapsed frame time, never the absolute clock |

Speech therefore reads as "it is listening" rather than as syllables; a clap
reads as a startle that relaxes. The per-state weight (`retract` in
`STATE_EXCITATION`) is 1 for listening and recognized, 0 elsewhere, and it
ramps with a 250 ms time constant so leaving listening slides the ends back
out instead of snapping.

### Geometry: the voice mark is the ratified 7-line mark

The voice mark now renders the `brand` density by default (spine + 6 lanes,
pitch 72, stroke 48, gap 24 — `PATHS_7` in `HalbertMark.tsx`, reproduced
exactly). The tighter gap caps the pluck amplitudes at `[6, 7, 8, 9, 9, 9, 8]`
(the 1.3-ceiling invariant against a 24-unit gap); the spectrum gains a
7-band octave ladder (8 kHz → 40 Hz) and the string ladder a 7-entry
interpolation of the same endpoints. `medium` (6) and `display` (10) remain
available.

## Demo source (Storybook and marketing share it)

`createSpeechBurstSource()` — seeded syllable bursts at roughly four a second,
sharp attack and exponential decay, each with its own spectral centre — so the
demo plucks the way speech does. It replaces the smooth formant sweep that was
copied into `marketing/web-v10/src/content/ui.jsx`; the marketing plate now
imports it from the design system. The app needs no change: it feeds live
analyser energy through the same onset path.

## What this deliberately does not do

- No second mode per tine (the 1/n² law would put mode 2 at a quarter
  amplitude — invisible at a 48-unit stroke). Add it as a knob if the review
  wants the "traveling kink" look.
- No bezier/CSS variant. The three surfaces all render the shared component.
