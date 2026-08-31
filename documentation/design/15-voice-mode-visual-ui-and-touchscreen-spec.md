# Voice Mode Visual UI & Touchscreen Architecture Specification

> **Document:** `documentation/design/15-voice-mode-visual-ui-and-touchscreen-spec.md`  
> **Status:** Architecture, Visual UI & SVG Animation Specification  
> **Date:** 2026-08-31  
> **Target Framework:** React 18.2 / 19, SVG Path Deformation / Web Audio API, Tailwind CSS, Tauri v2 / Kiosk Mode, Linux (`halbert_core`)  
> **Reads With:** `documentation/design/11-response-modality-handoff.md`, `documentation/design/14-system-prompts-and-modality-gap-analysis.md`, `documentation/design/the-being.md`, `documentation/design/DESIGN-SYSTEM-SPEC.md`, `audio-research/01-CORRECTED-ARCHITECTURE.md`, `audio-research/03-UX-SURFACES.md`
> **Consumes:** Modality-voice engine SSE events (`modality_resolved`, `speech_segment`) from Phase 2.5 work in `integrations/modality_wiring.py` and `hooks/useAgentStream.ts`

---

## 1. Executive Vision: The Embodied Voice Presence

Halbert is fundamentally structured as a multi-modal sovereign mind. While the **Engaged Surface** (`HostShell.tsx` — conversation spine + context stage) serves the desktop workstation user and the **Browsing Surface** (`Layout.tsx` nav rail) serves the sysadmin, **Voice Mode** represents Halbert's **embodied physical presence in the room**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            THE THREE HALBERT SURFACES                       │
├──────────────────────────┬──────────────────────────┬───────────────────────┤
│ 1. Engaged Surface       │ 2. Browsing Surface      │ 3. Voice Mode Surface │
│    (Workstation Canvas)  │    (Sysadmin Hub)        │    (Living Presence)  │
├──────────────────────────┼──────────────────────────┼───────────────────────┤
│ • Conversation Spine     │ • Full Navigation Rail   │ • Central Resonator   │
│ • Terminal Dock & Stage  │ • Storage, ZFS, Services │ • Spectral SVG Motion │
│ • Diffs & Telemetry      │ • Network, GPU, Backups  │ • Touchscreen Kiosk   │
│ • Keyboard / Mouse-first │ • Configuration Forms    │ • Ambient Ear & Voice │
└──────────────────────────┴──────────────────────────┴───────────────────────┘
```

In a dedicated appliance setup — such as an **Intel N150 Home Assistant server** with an attached 7"–15" capacitive touchscreen or wall-mounted iPad/kiosk — Voice Mode is the primary **"Listening & Resonating" interface**. It transforms the abstract AI into a physical, acoustic being with clear visual feedback, tactile touch controls, and power-conscious ambient display management.

---

## 2. Core Visual Aesthetic: The Audio-Reactive Halbert Mark

### 2.1 The Geometry of the Mark
The official Halbert brand mark (`/Volumes/4TB-BAD/Halbert/assets/brand/halbert-mark-medium.svg` and `packages/design-system/src/primitives/HalbertMark.tsx`) is inherently acoustic. It is constructed from concentric, nested U-shaped resonator paths radiating outward from a central vertical stem.

**Voice Mode uses `density='display'`** (10 concentric paths), which is what `HalbertMark` renders at sizes > 64px via `density='auto'`. A 512px central resonator therefore renders all 10 tines. The `medium` variant (6 paths, used at 32–64px) is a subset suitable for the 48px header emblem when Voice Mode scales the mark down during keyboard overlay. The frequency table below covers the full 10-ring `display` density.

```
                          X = 512 (Center Line)
                               │
               Outer Tines     │     Outer Tines
              Ring 5  Ring 3   │   Ring 3  Ring 5
                │       │      │     │       │
                ▼       ▼      ▼     ▼       ▼
             ╭─────────────────┬─────────────────╮   Y = 80px (Apex)
             │  ╭──────────────┼──────────────╮  │
             │  │  ╭───────────┼───────────╮  │  │
             │  │  │  ╭────────┼────────╮  │  │  │
             │  │  │  │  ╭─────┼─────╮  │  │  │  │
             │  │  │  │  │  │  │  │  │  │  │  │  │
             │  │  │  │  │  │  │  │  │  │  │  │  │
             │  │  │  │  │  │  │  │  │  │  │  │  │   Y = 512px (Equator)
             │  │  │  │  │  ╰──┴──╯  │  │  │  │  │   (Concentric U-Arcs)
             │  │  │  │  ╰───────────╯  │  │  │  │
             │  │  │  ╰─────────────────╯  │  │  │
             │  │  ╰───────────────────────╯  │  │
             │  ╰─────────────────────────────╯  │
             ╰───────────────────────────────────╯   Y = 944px (Base)
```

### 2.2 Harmonic Frequency-to-Geometry Mapping
Rather than applying generic uniform scaling or CSS pulses, the mark acts as a **physical harmonic resonator**, where each concentric tine corresponds to a specific acoustic register of the human voice and synthesized speech:

| Tine Identifier | Geometric Coordinates / Radius | Acoustic Frequency Register | Vocal Characteristic Mapped |
|---|---|---|---|
| **Center Stem (Ring 0)** | `M 512 80 V 512` (Vertical line) | **Brilliance / Air** (4,000 Hz – 8,000 Hz) | Sibilance airiness (`s`, `t`, `sh`), upper overtones, fricative energy |
| **Ring 1** | Radius $R = 48.0\text{px}$ (`X: 464.0` to `560.0`) | **Sibilance** (2,500 Hz – 4,000 Hz) | Consonant attacks, sharp sibilants, articulation clarity |
| **Ring 2** | Radius $R = 96.0\text{px}$ (`X: 416.0` to `608.0`) | **Upper Mids** (1,500 Hz – 2,500 Hz) | Nasal clarity, vowel formant $F_2$, presence band |
| **Ring 3** | Radius $R = 144.0\text{px}$ (`X: 368.0` to `656.0`) | **Vowel Clarity** (1,000 Hz – 1,500 Hz) | Articulation, consonant definition, intelligibility |
| **Ring 4** | Radius $R = 192.0\text{px}$ (`X: 320.0` to `704.0`) | **Vocal Core / Formant** (700 Hz – 1,000 Hz) | Vowel formant $F_1$ upper, melodic speech cadence |
| **Ring 5** | Radius $R = 240.0\text{px}$ (`X: 272.0` to `752.0`) | **Vowel Body** (500 Hz – 700 Hz) | Core vowel formant $F_1$, fullness of vowels |
| **Ring 6** | Radius $R = 288.0\text{px}$ (`X: 224.0` to `800.0`) | **Warmth** (350 Hz – 500 Hz) | Body of the voice, tonal warmth, chest resonance upper |
| **Ring 7** | Radius $R = 336.0\text{px}$ (`X: 176.0` to `848.0`) | **Chest Formant** (200 Hz – 350 Hz) | Vocal warmth, male chest resonance, tonal density |
| **Ring 8** | Radius $R = 384.0\text{px}$ (`X: 128.0` to `896.0`) | **Vocal Fundamental** (100 Hz – 200 Hz) | Speaker pitch fundamental ($F_0$ for male/female voices) |
| **Outermost Arc (Ring 9)** | Radius $R = 432.0\text{px}$ (`X: 80.0` to `944.0`) | **Sub-Bass / Room Acoustic** (40 Hz – 100 Hz) | Chest rumble, low room acoustics, ambient energy |

---

## 3. Mathematical Animation & Path Deformation Engine

To achieve an organic, physical vibration without tearing SVG geometry, each path is modulated in real time using parametric Bézier deformation and Fourier energy weighting.

```
┌───────────────────────┐       ┌───────────────────────┐       ┌────────────────────────┐
│  Audio Ingress / TTS  │ ----> │ Web Audio Analyser    │ ----> │ 2nd-Order Spring       │
│  (16kHz PCM Stream)   │       │ (FFT 64 Frequency Bins)│       │ Physics Smoothing      │
└───────────────────────┘       └───────────────────────┘       └───────────┬────────────┘
                                                                            │
                                                                            ▼
┌───────────────────────┐       ┌───────────────────────┐       ┌────────────────────────┐
│ Rendered Screen       │ <---- │ Dynamic SVG Path      │ <---- │ Standing Wave &        │
│ (60 FPS SVG)          │       │ String Interpolation  │       │ Radial Flex Equations  │
└───────────────────────┘       └───────────────────────┘       └────────────────────────┘
```

### 3.1 Standing Wave Equation on Vertical Legs
For the vertical segments of each tine $k \in \{0 \dots 4\}$, the lateral displacement $\Delta x_k(y, t)$ at vertical position $y$ and timestamp $t$ is calculated by:

$$\Delta x_k(y, t) = A_k \cdot E_k(t) \cdot \sin\left(\frac{n_k \pi (y - y_{\text{top}})}{y_{\text{bottom}} - y_{\text{top}}} + \phi_k(t)\right) \cdot W(y)$$

Where:
- $E_k(t) \in [0, 1]$ is the normalized spectral energy in frequency bin $k$.
- $A_k$ is the maximum lateral excursion amplitude (typically $6\text{px}$ to $18\text{px}$).
- $n_k$ is the spatial harmonic mode (1 for fundamental flex, 2 or 3 for higher ripples on inner stems).
- $\phi_k(t)$ is continuous phase drift: $\phi_k(t) = \int \omega_k \, dt$.
- $W(y)$ is a Tukey/Hann window envelope ensuring boundary pinning ($\Delta x = 0$ at apex endpoints and base junctions) to prevent path disconnection:
  $$W(y) = \sin^2\left(\frac{\pi (y - y_{\text{top}})}{y_{\text{bottom}} - y_{\text{top}}}\right)$$

### 3.2 Radial Flexure on Base U-Arcs
For the curved bottom arc of tine $k$, displacement is applied along the normal radial vector:

$$\Delta r_k(\theta, t) = B_k \cdot E_k(t) \cdot \cos\left(m_k \theta + \psi_k(t)\right)$$

Where $\theta \in [0, \pi]$ sweeps the semi-circular base from left leg to right leg.

### 3.3 Physics-Based Damping & Smoothing
To prevent harsh strobe-like jitter when processing noisy mic inputs, raw FFT bin amplitudes pass through a 2nd-order damped spring oscillator:

$$m \frac{d^2 x}{dt^2} + c \frac{dx}{dt} + k_s (x - x_{\text{target}}) = 0$$

- **Stiffness ($k_s$):** `140.0` (rapid attack on transient phonemes)
- **Damping ($c$):** `18.5` (smooth, organic decay without robotic square-wave transitions)
- **Mass ($m$):** `1.0`

**Integrator:** Semi-implicit (symplectic) Euler with a **fixed 8 ms internal timestep** ($\Delta t_{\text{fixed}} = 0.008\text{s}$), sub-stepped from the variable requestAnimationFrame delta. At 60fps the natural $\omega\sqrt{k_s/m} \approx 11.8\text{ rad/s}$, giving $\omega \cdot \Delta t \approx 0.094$ — well within the stability region. The fixed substep ensures stability when the display frame rate dips to 30fps on N150-class hardware ($\omega \cdot \Delta t_{\text{fixed}} \approx 0.094$ regardless of render rate). The render loop interpolates between the two most recent physics states for smooth visual output.

**Render path:** SVG `d`-attribute string interpolation at 60fps. On N150-class hardware, 10 deforming paths with string rebuild per frame is performant at 60fps. If profiling reveals frame drops, a Canvas2D fallback (redraw bezier curves as Canvas `bezierCurveTo` calls instead of SVG string rebuilds) can be implemented as a future optimization without changing the physics layer.

### 3.4 FFT Bin → Tine Mapping
The Web Audio `AnalyserNode` produces 64 frequency bins linearly spaced from 0 Hz to Nyquist ($f_s / 2$). At 16 kHz sample rate, Nyquist = 8,000 Hz, so each bin spans $8000 / 64 = 125\text{ Hz}$. Voice frequency registers are approximately logarithmic, so bins must be grouped into per-tine energy bands using logarithmic band edges:

$$k_{\text{tine}} = \text{argmin}_j \left| f_{\text{center},j} - f_{\text{edge}} \right| \quad \text{where} \quad f_{\text{center},j} = j \cdot \frac{f_s}{2 \cdot N_{\text{fft}}}$$

The mapping function groups bins into 10 bands using the frequency register boundaries from §2.2:

```typescript
// Bin edges (inclusive lower, exclusive upper) for 10 tines at 16kHz / 64-bin FFT
const TINE_BIN_RANGES: Array<[number, number]> = [
  [32, 64],   // Ring 0: 4000-8000 Hz (brilliance/air)
  [20, 32],   // Ring 1: 2500-4000 Hz (sibilance)
  [12, 20],   // Ring 2: 1500-2500 Hz (upper mids)
  [8, 12],    // Ring 3: 1000-1500 Hz (vowel clarity)
  [6, 8],     // Ring 4: 700-1000 Hz (vocal core)
  [4, 6],     // Ring 5: 500-700 Hz (vowel body)
  [3, 4],     // Ring 6: 350-500 Hz (warmth)
  [2, 3],     // Ring 7: 200-350 Hz (chest formant)
  [1, 2],     // Ring 8: 100-200 Hz (fundamental)
  [0, 1],     // Ring 9: 0-100 Hz (sub-bass)
];

// Per-tine normalized energy: E_k = mean(bin_amplitude[j]) for j in TINE_BIN_RANGES[k]
function tineEnergy(freqData: Uint8Array, k: number): number {
  const [lo, hi] = TINE_BIN_RANGES[k];
  let sum = 0;
  for (let j = lo; j < hi; j++) sum += freqData[j];
  return (sum / (hi - lo)) / 255;  // normalize to [0, 1]
}
```

Note: bins 0–1 capture DC and near-DC energy which is mostly ambient room noise. Ring 9's energy should be low-passed more aggressively (additional 0.3× attenuation) to prevent sub-bass rumble from dominating the outer arc.

---

## 4. Voice Mode State Machine & Interaction Lifecycle

Voice Mode transitions through seven distinct operational states, aligned with the existing `AcousticAuraIndicator` state vocabulary (`idle | listening | recognized | thinking | speaking | error`):

```mermaid
stateDiagram-v2
    [*] --> Standby: Idle (Screen Blanked / Low Luma)

    Standby --> Listening: Wake Word ("Halbert") / Screen Tap
    Listening --> Recognized: Speaker Biometric Match (CAM++)
    Listening --> Thinking: Voice Activity Ceases (VAD End of Speech)
    Recognized --> Thinking: Confirmed Identity, Continue Turn
    Thinking --> Speaking: LLM Response / Tool Result Ready
    Speaking --> Listening: Continuous Multi-turn / Barge-in Detected
    Speaking --> Standby: Turn Complete + Inactivity Timeout (30s)
    Listening --> Error: Mic Failure / Ingress Disconnect
    Thinking --> Error: LLM Timeout / Tool Exception
    Error --> Standby: Auto-retry Exhausted or User Dismissal

    Listening --> ChatTransition: Tap Keyboard / Swipe Up
    Thinking --> ChatTransition: Tap Screen / Complex Output
    Speaking --> ChatTransition: "Show me details"
    ChatTransition --> HostCanvas: Full Dual-Column Engaged Mode
    HostCanvas --> Listening: Voice Resume / /voice Route Re-entry
```

### 4.1 State Breakdown

| State | Visual Behavior of Halbert Mark | Audio & Acoustic Subsystem | Display Power / Screen State |
|---|---|---|---|
| **1. Standby / Dormant** | Ultra-dim (10% opacity) slow sinusoidal breathing (3.5s cycle) or pure `#000000` blackout. | Low-power wake word listener active (Sherpa-onnx / openWakeWord). | Screen backlight at 0%–10% or software blanked. |
| **2. Listening** | Mark elevates to full luminosity (`#D34E24` Olivetti Vermilion). Reactive wave vibration tracks user's voice in real time. | Mic ingress active (16kHz PCM stream). VAD segmenting speech frames. | Full brightness (100%), 60fps path deformation. |
| **3. Recognized** | Biometric badge fades in at top-left (`Eric • Admin 98%`). Mark holds listening vibration but gains a subtle green confirmatory pulse ring. | Speaker ID match confirmed (CAM++ 256-dim). Role gate applies permissions for upcoming turn. | Full brightness, brief confirmatory pulse. |
| **4. Thinking** | Concentric tines rhythmically contract inward, emitting a soft radial chromatic aura. | LLM inference, CRAG graph evaluation, or tool execution. | Full brightness, subtle pulsing glow. |
| **5. Speaking** | Full harmonic path resonance synchronized to Piper neural TTS output. Subtitle stream renders live words. | Neural TTS audio output playing through speakers. Barge-in VAD active. | Full brightness, frequency-mapped tine vibration. |
| **6. Interrupted (Barge-in)** | Sharp radial ripple / instant dampening back to Listening posture. | Immediate playback audio cutoff. New user utterance captured. | Instant zero-latency visual reset. |
| **7. Error** | Mark flashes vermilion-to-red gradient, then dims to a muted state with a small alert glyph. | Audio ingress/egress halted. Error logged. Auto-retry with backoff (3 attempts). | Full brightness during flash, then dims to standby-level. |

---

## 5. Touchscreen Appliance Logistics: N150 Server & Display Management

### 5.1 The Hardware Architecture
In a homelab/smart home deployment, the user often runs Halbert on an **Intel N150 / N100 mini PC** connected to a dedicated HDMI/USB capacitive touchscreen (7" to 15.6" IPS or OLED panel).

```
┌────────────────────────────────────────────────────────────────────────┐
│                        INTEL N150 APPLIANCE                            │
│                                                                        │
│  ┌───────────────────────┐             ┌────────────────────────────┐  │
│  │ halbert_core (Python) │             │ Tauri v2 / Kiosk Chromium  │  │
│  │ • Local Mic Ingress   │ <─WebSocket─│ • VoiceMode.tsx View       │  │
│  │ • Sherpa STT / VAD    │  & SSE Loop │ • Audio-Reactive SVG Mark  │  │
│  │ • Piper Neural TTS    │             │ • Virtual Touch Keyboard   │  │
│  │ • Power / DPMS Daemon │             │ • Modality Switcher        │  │
│  └───────────────────────┘             └────────────────────────────┘  │
└───────────────────┬───────────────────────────────────┬────────────────┘
                    │ HDMI Video Output                 │ USB HID Touch
                    ▼                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  TOUCHSCREEN MONITOR (7" - 15.6")                      │
│                                                                        │
│   [ Speaker Badge ]                             [ Settings / Mute ]    │
│                                                                        │
│                               ( ( ( ) ) )                              │
│                           HALBERT RESONATOR MARK                       │
│                               ( ( ( ) ) )                              │
│                                                                        │
│   "Turned off 3 lights in the kitchen and set thermostat to 71°F"     │
│                                                                        │
│   [ <Mic> Tap to Speak ]    [ <Keyboard> Type / Expand ] [ <X> Cancel ]│
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Screen Power Saving vs. Instant Wake Latency
A major design challenge for dedicated voice displays is power management:

| Method | Power Saved | Wake Latency | Suitability for Voice Mode |
|---|---|---|---|
| **Hardware DPMS (`xset dpms force off`)** | 100% display backlight powered off (~5–15W). | **1.5s – 3.5s** (HDMI signal re-sync & handshake). | **Unacceptable for wake word.** A 2-second blank delay feels broken when speaking to an assistant. |
| **DDC/CI or PWM Backlight Dimming (`/sys/class/backlight`)** | 80%–90% power saved (LED backlight dialed to 0%). | **50ms – 100ms** (Instant PWM ramp). | **Ideal for LCD panels.** Immediate visual feedback on "Hey Halbert". |
| **Software Pure Black (`#000000` Canvas + `cursor: none`)** | 95%+ power saved on OLED screens; GPU idle. | **0ms** (Instant frame render). | **Ideal for OLED / Modern Kiosk displays.** Zero wake latency. |

#### Recommended Multi-Tier Standby Policy:
1. **Tier 1 (0 – 30 seconds idle):** Ambient resting mark (subtle 10% breathing aura + current room temperature/clock).
2. **Tier 2 (30 seconds – 10 minutes idle):** Software blackout / ultra-dim ambient clock. Instant wake on wake-word or screen touch.
3. **Tier 3 (Quiet Hours / Night 22:00 – 07:00 or >15m idle):** Backlight dimmed to 0% via DDC/CI or hardware DPMS sleep. Wake-word daemon signals hardware wake before TTS completes.

---

## 6. Touchscreen UI Layout & Transition Mechanics

### 6.1 Voice Mode Screen Anatomy
When active, the Voice Mode layout maximizes physical visibility and touch accessibility:

```
┌────────────────────────────────────────────────────────────────────────┐
│ [● Eric (Admin) 98%]     Living Room Satellite   [<Settings>] [<VolumeX> Mute]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│                                                                        │
│                                   M                                    │
│                               ╭───┼───╮                                │
│                              ╭┤ ╭─┼─╮ ├╮                               │
│                             ╭┤│╭┤ ╵ ├╮│├╮                              │
│                             │││││   │││││                              │
│                             ╰┴┴┴┴───┴┴┴┴╯                              │
│                         (Audio-Reactive Mark)                          │
│                                                                        │
│                                                                        │
│  "I've verified the nightly ZFS snapshot completed with zero errors."  │
│  [ whisper prosody: calm ]                                             │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  [<Mic> Tap to Speak]    [<Keyboard> Open Keyboard] [<ArrowUpRight> Host Canvas]│
└────────────────────────────────────────────────────────────────────────┘
```

### 6.2 The Touch Controls
1. **Direct Mark Tap:** Tapping the center mark acts as a universal action:
   - If Speaking $\rightarrow$ **Interrupts / Silences TTS**.
   - If Idle $\rightarrow$ **Initiates Push-to-Talk**.
   - If Listening $\rightarrow$ **Forces immediate turn submission (manual VAD end-of-speech)**.
2. **On-Screen Touch Keyboard Overlay:**
   - Tapping `[ <Keyboard> Open Keyboard ]` or swiping up smoothly glides a touch-friendly virtual keyboard into view from the bottom edge.
   - The Halbert Mark scales down to a 48px header emblem.
   - Includes quick-intent suggestion chips: `"System Vitals"`, `"Check Storage"`, `"Lock Doors"`, `"Run Health Scan"`.
3. **Seamless Transition to Host Canvas (`HostShell.tsx`):**
   - Tapping `[ <ArrowUpRight> Host Canvas ]` or swiping right seamlessly transitions the screen from Voice Mode to the full two-column Host Canvas.
   - The voice conversation history is preserved intact in the `AgentChat.tsx` conversation spine.

---

## 7. Comparison: Voice Mode vs. Existing Audio Tooling

Halbert's audio capabilities have evolved rapidly across recent engineering batches. Voice Mode serves as the unifying presentation canvas — it is a full-screen kiosk realization of **UX Surface 1** (Ambient Acoustic Aura & Waveform) from `audio-research/03-UX-SURFACES.md`, expanding the 16px header indicator into a 512px central resonator. The modality-voice engine (Phase 2.5, merged to main) already provides the SSE event contract that Voice Mode consumes:

| Feature / Subsystem | Existing Component | Role in Voice Mode Screen |
|---|---|---|
| **Header Status Aura** | `AcousticAuraIndicator.tsx` | Provides minimal 16px pulse in desktop mode; in Voice Mode, expanded to full 512px central resonator. Polls `/api/audio/status` every 2s for coarse state. |
| **Speech Delivery Pill** | `VoiceCompanionPill.tsx` | Compact pill below chat bubbles; in Voice Mode, transformed into the live floating subtitle ribbon. Already consumes `SpeechSegmentEvent[]` from `useAgentStream`. |
| **Modality Resolution** | `useAgentStream.ts` SSE handler | Emits `modality_resolved` event with `ResponseModality` ('voice' / 'text' / 'mixed' / 'deferred'). Voice Mode uses this to drive state transitions (Listening $\rightarrow$ Thinking $\rightarrow$ Speaking). |
| **Speech Segments** | `useAgentStream.ts` SSE handler | Emits `speech_segment` events with typed `SpeechSegmentEvent` (text, prosody, role). Voice Mode subtitle ribbon consumes this stream directly — same interface as `VoiceCompanionPill`. |
| **Quiet Hours & Life-Safety** | `modality_wiring.py` | Already implements quiet hours (22:00–07:00) and life-safety bypass (B2 smoke/gas/CO detection). Voice Mode standby policy (§5.2 Tier 3) defers to this engine rather than reimplementing. |
| **Biometric Recognition** | `SpeakerProfilesCard.tsx` (CAM++ 256-dim) | Identifies speaker identity in background $\rightarrow$ displays top-left biometric badge with confidence score. Triggers the `recognized` state (§4.1). |
| **Acoustic Anomalies** | `AcousticAnomalyModule.tsx` (CED-tiny) | Proactive event card $\rightarrow$ triggers Voice Mode screen wake with urgent amber pulse when glass break / smoke alarm is heard. |
| **Audio Configuration** | `AudioSettings.tsx` | Manages Wyoming satellites, Piper voices, and quiet hours $\rightarrow$ directly governs Voice Mode audio engines. |
| **Pronunciation Lexicon** | `PronunciationLexicon` in `modality_wiring.py` | 40+ Halbert domain terms (systemd, MQTT, NVMe, etc.) with phonetic mappings. Affects TTS phoneme timing and spectral content, which feeds back into the frequency-to-tine resonance mapping (§2.2). |

**Transport clarification:** `/api/audio/status` is a **polling** endpoint (GET, 2s interval in `AcousticAuraIndicator`). The real-time event stream is **`/api/being/events`** (SSE), which carries `modality_resolved`, `speech_segment`, `response_chunk`, and proactive event types. Voice Mode should use SSE for all real-time state transitions and reserve polling for initial state hydration on mount.

---

## 8. Implementation Roadmap

### Phase 1: SVG Path Deformation Prototype
- Build `AudioReactiveHalbertMark.tsx` component in `@halbert/design-system`.
- Implement Web Audio API `AnalyserNode` frequency extraction (64 FFT bins, 16kHz sample rate).
- Implement FFT bin → tine energy mapping per §3.4 (`TINE_BIN_RANGES`).
- Create parametric Bézier curve generator with Hann window boundary pinning.
- Implement semi-implicit Euler integrator with fixed 8ms substep (§3.3).
- **SSR/Storybook guards:** `AudioContext` and `AnalyserNode` are browser-only. The component must lazy-init the audio context on first user interaction (not on mount), guard with `typeof window !== 'undefined''`, and render a static (non-animated) fallback in Storybook/SSR contexts. The `@halbert/design-system` package has dual React 18/19 peer-deps and is consumed by Storybook — no Web Audio types should leak into the public props interface.
- Add Storybook stories with synthetic `OscillatorNode` test tones for visual testing (no microphone required).

### Phase 2: Voice Mode Screen (`VoiceMode.tsx`)
- Implement full-screen view in `halbert_core/dashboard/frontend/src/pages/VoiceMode.tsx`.
- **Consume existing SSE stream** from `/api/being/events` — do not create a new event source. The modality-voice engine (Phase 2.5, merged to main) already emits:
  - `modality_resolved` events with `ResponseModality` type — use for state machine transitions (§4).
  - `speech_segment` events with `SpeechSegmentEvent` type — feed directly to the subtitle ribbon (same interface as `VoiceCompanionPill`).
  - `response_chunk` events — use for live STT transcription display.
- **Initial state hydration:** Poll `/api/audio/status` once on mount to get current pipeline state, then switch to SSE for all subsequent updates.
- Integrate live streaming STT transcription subtitle ribbon using `SpeechSegmentEvent[]` from `useAgentStream`.
- Add touch gestures (tap to interrupt, swipe up for virtual keyboard).
- Reference `PronunciationLexicon` from `modality_wiring.py` for domain term display in subtitle ribbon (e.g., show "NVMe" not "N-V-M-E").

### Phase 3: Shell & Appliance Integration
- Add Voice Mode route (`/voice`) and integrate with `ShellModeContext.tsx`.
- Implement software blanking / auto-sleep timer with instant touch/wake-word wakeup.
- Defer quiet-hours standby policy to `modality_wiring.py`'s `should_speak_proactively()` — do not reimplement quiet-hours logic.
- Wire seamless bidirectional transition between Voice Mode and `HostShell` canvas (state diagram return edge: `HostCanvas → Listening`).
- Validate on touch hardware (N150 mini PC + 10" HDMI capacitive touchscreen).

---

> **Design Law:**  
> *The mark does not merely display sound; it embodies the voice.*
