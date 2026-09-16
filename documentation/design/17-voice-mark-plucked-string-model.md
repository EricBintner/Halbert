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

| state | pluck source | gain (displacement per unit level rise) | swell weight | extra |
|---|---|---|---|---|
| idle | none from the breathing source | — | 1.0 | sparse soft plucks: one random tine every 2.5–6 s, amplitude 0.25–0.45, weighted toward the outer (long-sustain) tines |
| listening | band-level onsets | 2.0 | 0.3 | — |
| recognized | — | — | 0.3 | on entry (including mounting in it), a **strum**: every tine plucked at 0.7, spine first, 35 ms stagger outward |
| thinking | — | — | 0 | traveling bulges and the 0.94 contraction, unchanged |
| speaking | band-level onsets | 2.5 | 0.3 | — |
| error | — | — | 0 | tint only, unchanged |

**Onset** = a per-frame rise of a tine's band level above 0.02 (mic noise
stays below it). Each rising frame plucks by `gain × rise`; a sharp consonant
lands in two or three frames and sums to one strike, a slow ramp becomes a
slow push that returns when the ramp ends. No edge detector, no latency.

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
