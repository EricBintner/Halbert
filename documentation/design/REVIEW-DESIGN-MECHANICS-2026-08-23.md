# Review: Design Mechanics and User Flows

**Status:** Stub — to be filled in by external reviewer.
**Reviewer:** [name]
**Date:** [date]
**Reads with:** `.handoff/HANDOFF-REVIEW-2026-08-23.md` (the handoff brief)

---

## How to use this document

This is your working document. Fill in each section with user flows,
interaction patterns, and design markup. Delete the scaffolding prompts
when you've addressed them. Add new sections as needed.

The handoff brief asked for a design doc focused on user-flow and myopic
interactions — the "how does a human actually use this" question. Sketch
the flows. Propose interaction patterns. Mark up the micro-interactions.
Use ASCII diagrams or mermaid where they help.

Remember: no emojis. Use icon fonts or clever graphic design.

---

## 1. Design principles

[Before diving into flows, state the design principles that guide your
recommendations. What makes this product different from a monitoring
dashboard with a chatbot? What's the interaction philosophy?]

---

## 2. The first conversation (onboarding / birth)

### 2.1 First-run experience

[The user installs Halbert and opens it for the first time. What happens?
Walk through the first 60 seconds. Does the being introduce itself? Does
it ask about purpose? Does it start scanning immediately or wait? What's
the tone? What does the screen look like?]

### 2.2 Purpose discovery

[The being.yml config has a `purpose` field (free text v1). How does the
being learn its purpose? Is it asked directly? Inferred from the system
(NAS vs dev box vs laptop)? Is it a conversation or a form?]

### 2.3 The first scan

[When does the being do its first config scan? Immediately on first run?
After onboarding? On a schedule? What does the user see while it's
scanning? Does the being narrate what it's doing?]

### 2.4 First findings

[The being finds something during the first scan. How does it present it?
Is this the first proactive interrupt? Or does it wait until the user
asks? What's the tone — "I just met you and already found a problem" vs
"I've been looking around and noticed something"?]

---

## 3. The conversation surface

### 3.1 Message types and rendering

[The conversation supports multiple message types: plain text, module
invocations, proposals, evidence refs, morning reports. How does each
type render? Sketch the layout for each.]

### 3.2 The context region

[The being.md describes a two-column layout: conversation spine (left) +
context region (right, summoned modules). How does this work in practice?
When is the context region empty? When does a module appear? How does the
user dismiss a module? Can multiple modules be summoned at once?]

### 3.3 Scrolling and history

[How does scrolling work when modules are inline in the conversation? Do
old modules collapse to a summary chip? Does the conversation have
infinite scroll? How does the user find something from "last Tuesday"?]

### 3.4 The input area

[What does the input area look like? Is it a single text field? Does it
support attachments (images, files)? Does it have a module palette
trigger? What's the keyboard shortcut to focus it?]

---

## 4. The proactive interrupt

### 4.1 The interrupt itself

[The being detects a config problem and wants to tell the user. What
exactly appears on screen? Walk through the visual states:
- App is open, user is in a conversation
- App is open, user is in browsing mode (dashboard)
- App is minimized to tray
- App is closed

For each: what does the interrupt look like? Toast? Slide-in? Badge?
What does the message say? How long does it stay?]

### 4.2 The finding card

[The interrupt leads to a finding card. What does it contain? Sketch the
layout. Where do the four whys appear? How does the user expand/collapse
them? What actions are available (approve/dismiss/snooze/why/ignore
category)?]

### 4.3 Approve / dismiss / snooze as gestures

[How does the user interact with a finding?
- Approve: what does it trigger? Does it go straight to the proposal, or
  is there an intermediate step?
- Dismiss: what does it mean? Does the user provide a reason? Does the
  being learn from it?
- Snooze: for how long? Is it a preset (1 day, 1 week) or custom? What
  happens when the snooze expires?
- "Why?": how does the user drill into the four whys? Is it a click, a
  hover, a keyboard shortcut?]

### 4.4 The proposal flow

[The being proposes a config change. What does the proposal look like?
Sketch the diff view. Where is the blast-radius shown? How does
approve/reject work? What happens after approval — does the being apply
immediately or queue? What does the "I applied it, here's what changed"
follow-up look like? What does rollback look like?]

---

## 5. The "how are you?" flow

### 5.1 The question

[The user asks "how are you?" What does the response look like? Is it a
single message? A message + a summoned vitals module? How does the vitals
module render alongside the text?]

### 5.2 Provenance and the WhyChip

[Every claim in the response has a provenance ref. How does the WhyChip
work as a UI element? Sketch it. Is it inline with the text? A sidebar?
A hover affordance? What happens when the user clicks it? What does the
evidence view look like?]

### 5.3 The vitals module

[What does the summoned vitals module show? CPU, memory, disk, network —
in what layout? Is it real-time or a snapshot? How does the user dismiss
it? Can they expand it to the full dashboard?]

### 5.4 Voice in practice

[How does the voice setting affect the "how are you?" response? Show the
same response in first_person, the_computer, and hybrid. Does the voice
affect the UI at all, or just the text?]

---

## 6. The morning report

### 6.1 Delivery

[The user opens Halbert in the morning. What do they see? Is the morning
report the first thing? Is it a single message? A special view? How does
it differ from a normal conversation message?]

### 6.2 Content and structure

[What's in the morning report? Findings, proposals, config changes,
telemetry anomalies, approvals awaiting. How are they grouped? How does
the user drill into each item? Is it scrollable? Collapsible?]

### 6.3 Interaction

[Can the user act on items in the morning report directly (approve,
dismiss, snooze)? Or do they need to open each item separately? Can the
user ask follow-up questions about the report? ("Tell me more about the
sshd thing.")]

---

## 7. The module palette

### 7.1 Summoning modules manually

[The user wants to summon a module without the being suggesting it. How
do they do it? A keyboard shortcut (Cmd+K)? A button in the input area?
A command palette? What does the palette look like? How are modules
listed — by name, by category, by icon?]

### 7.2 Module interactions

[Once a module is summoned, how does the user interact with it? Can they
resize it? Move it? Pin it? Dismiss it? Can they have multiple modules
open? How does the layout adapt?]

---

## 8. The tray indicator

### 8.1 Visual states

[What are the tray indicator states? Calm / needs-attention / urgent —
what do they look like? Is it a color change? An icon change? A badge
count? How does the user distinguish between "one info finding" and
"three critical findings"?]

### 8.2 Interactions

[What happens on click? Double-click? Right-click? Is there a context
menu? What's in it? Can the user dismiss findings from the tray? Can
they change the proactivity dial from the tray?]

### 8.3 The web fallback

[The being.md mentions a "persistent header chip in the dashboard" as a
web fallback for the tray. What does this look like? How does it behave
differently from the tray indicator?]

---

## 9. Settings: the "Being" tab

### 9.1 Layout

[The Settings page gains a "Being" tab. What does it look like? Sketch
the layout. How are the voice picker, proactivity dial, quiet hours,
morning report, and purpose field arranged?]

### 9.2 The voice picker

[How does the user choose between first_person / the_computer / hybrid?
Radio buttons? A segmented control? Does each option show a preview?
("I'm worried about /dev/sda1" vs "Your computer's primary drive...")]

### 9.3 The proactivity dial

[How does the user set the proactivity level? A literal dial? A slider?
A segmented control? Does each level show a description of what it
means? Can they set per-category overrides from the same view?]

### 9.4 Quiet hours and morning report

[How does the user set quiet hours? Two time pickers? A visual timeline?
How do they configure the morning report — toggle + time picker? What
if they want it off entirely?]

### 9.5 Purpose

[The purpose field is free text v1. How does it render? A textarea? A
single-line input? Does the being acknowledge when the user sets a
purpose? ("Got it — I'll keep an eye on storage since this is a NAS.")]

---

## 10. Error and degraded states

### 10.1 SourcePrep is down

[The being can't search its docs. What does the user see when they ask a
question? How does the being explain it? Does the UI show a degraded
state indicator?]

### 10.2 The LLM is down

[The being can't generate a response. What happens? Does the UI show an
error? Does the being "go quiet"? Is there a retry mechanism?]

### 10.3 A config detector throws

[A detector crashes during a sweep. What happens? Does the being report
the error? Does it silently skip? Does it create a finding about itself?]

### 10.4 macOS degraded sensors

[The being is running on macOS. No journald, no systemd. How does the
being explain this? "I can't see journald on this body" — is this the
right tone? How does the UI reflect degraded capabilities?]

### 10.5 The proactive channel is broken

[The SSE stream drops. What happens? Does the user miss findings? Does
the being queue them? Does the tray indicator show a disconnected state?]

---

## 11. The "living with it" rhythm

### 11.1 A week with Halbert

[Walk through a typical week of using Halbert. How many proactive
interrupts? When does the morning report land? When does the user
initiate vs the being initiating? What's the cadence? What gets
annoying? What feels missing?]

### 11.2 The attention budget

[The being should not be exhausting to live with. How do we manage the
user's attention? Is there a maximum number of interrupts per day? Does
the being batch findings? Does it escalate (quiet for a day, then
assertive if something is still unresolved)?]

### 11.3 The relationship over time

[How does the relationship between user and being evolve over weeks and
months? Does the being learn what's noise? Does it become more or less
proactive? Does the user's trust increase? How is that measured?]

---

## 12. Accessibility and keyboard navigation

### 12.1 Keyboard-first interaction

[The user is a power user. Can they do everything with the keyboard?
What are the key bindings? Can they approve/dismiss/snooze with a
keystroke? Can they summon modules with a shortcut? Can they navigate
the conversation with arrows?]

### 12.2 Screen reader and assistive tech

[The being's messages carry provenance, modules, and proposals. How do
these render for screen readers? Is the WhyChip accessible? Are the
module containers labeled?]

---

## 13. Visual design language

### 13.1 Tone and density

[The user is technical. The UI can be dense. But the being is also
conversational. How do we balance information density with conversational
warmth? What's the visual tone — terminal-like? Dashboard-like? Something
new?]

### 13.2 Color and severity

[How do we communicate severity (info / warning / critical) without
relying on color alone? Icons? Borders? Backgrounds? How does severity
render in the tray, in the finding card, in the morning report?]

### 13.3 The being's "face"

[Does the being have a visual identity? An avatar? A color? A shape that
represents its state (calm / worried / working)? Or is it purely
textual? What are the trade-offs?]

---

## 14. Open design questions

[List the design questions that need further exploration. These are
things you noticed but don't have a recommendation for yet — they need
more thought or user testing.]

---

## 15. Summary of design recommendations

[Your top 5-10 design recommendations, prioritized. What should we
design first? What's the highest-risk interaction? What's the thing
that will make or break the product?]
