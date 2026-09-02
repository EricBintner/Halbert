# 11. Response Modality & Conversational Style — Design Handoff

**Date:** 2026-08-30
**Status:** Findings documented. Awaiting external design & UX review.
**Purpose:** This document records the architectural gaps discovered in Halbert's response-generation path regarding modality (voice vs text), conversational vs technical style, and intent-driven format selection. It is a handoff for an external AI reviewer to research best practices, validate or challenge the findings, and write their recommendations as feedback directly in this document.

---

## How to Use This Document (For the External Reviewer)

1. Read **Part A — Findings** for the current state of the codebase, with file references and line numbers.
2. Read **Part B — The Design Questions** for the open questions the founder wants answered.
3. Conduct your own research into voice assistant design best practices, conversational AI UX, and multi-modal response formatting.
4. Write your research, findings, and recommendations in **Part C — External Review** (the section at the bottom, left blank for you).
5. Be specific. Cite sources. Reference the codebase findings where relevant. Disagree with the findings where warranted — the goal is the best design, not consensus.

---

## Part A — Findings (Current State of the Codebase)

### A1. No "modality" concept exists anywhere in the system

The system has zero awareness of whether a response will be read on screen (text chat) or spoken aloud (voice). A search for `modality`, `output_channel`, `will_be_spoken`, `response_channel`, or any equivalent concept across the entire `halbert_core` package returns no matches. Every response is generated identically regardless of destination.

**Implication:** The voice path (TTS) and the text path (chat UI) receive the same model output. There is no branching at the prompt level, the model level, or the post-processing level.

### A2. Markdown formatting is hardcoded into the response prompt

The response-generation prompt unconditionally instructs the model to use markdown:

- File: `halbert_core/halbert_core/prompts/agent_prompts.py`
- Method: `build_response_prompt()` (called on every RESPONDING turn)
- Lines 688-697:

```
## Instructions
- Provide a helpful, accurate response based on the available information
- Use **markdown formatting**: headers (##), bullet points (-), **bold**, `code`, code blocks (```bash)
- Cite sources when possible (e.g., "According to the systemd documentation...")
- Be concise but complete
- If you're uncertain, clearly state your confidence level
- Suggest follow-up actions if appropriate

Your response (use markdown formatting):
```

No condition checks for variant, intent, voice mode, or output modality. Every response — greeting, troubleshooting, status check, voice turn — gets the same "use markdown formatting" instruction.

### A3. TTS will literally speak markdown syntax

The Piper TTS engine passes text directly to the synthesizer with no cleaning:

- File: `halbert_core/halbert_core/audio/speech/tts_engine.py`
- Method: `synthesize()`, lines 113-119

```python
def _generate() -> tuple[list[float], int]:
    audio = self._tts.generate(
        text,
        sid=self._speaker_id,
        speed=self._speed,
    )
```

If the model follows its prompt and outputs `## ZFS Pool Status`, Piper will attempt to speak "hash hash Z F S Pool Status." There is no markdown-to-plaintext conversion layer between the model output and TTS input. This is a latent bug that will surface the moment voice is wired into the chat path.

### A4. The intent classifier exists but does not influence response style

Halbert has a working intent classifier:

- File: `halbert_core/halbert_core/intake/signals.py`
- Lines 387-403

It classifies intent in priority order: `greeting > farewell > troubleshooting > question > command > informational`. This classification flows into `MessageIntake` via `intake/pipeline.py` (line 205) and is used to:

- Route model tier (chat/guide/specialist) via complexity scoring
- Decide whether retrieval is needed (`needs_retrieval = not (is_greeting or is_farewell)`)
- Decide whether tools are needed (`needs_tools = signals.is_troubleshooting and complexity.score >= threshold`)

It is **not** used to influence response format, verbosity, conversational tone, or modality. A greeting and a troubleshooting request get the same markdown-heavy response template.

### A5. The variant system (Home vs Workstation) does not affect communication style

BeingConfig has a `variant` field:

- File: `halbert_core/halbert_core/config/being_config.py`
- Line 226: `variant: str = "sysadmin"  # sysadmin | home | home-light`

Valid values: `sysadmin`, `home`, `home-light`. The variant is resolved via `cognition_wiring.py` `_get_variant()` (line 81) with priority: `BeingConfig.variant > HALBERT_VARIANT env > 'sysadmin'`.

However, the variant only controls **which background services start**:

- File: `halbert_core/halbert_core/dashboard/app.py`
- Lines 423-477: Skips sysadmin-only services (ingestion, discovery scan, scheduler, config watcher) on home/home-light variants.

The variant does **not** change:
- The system prompt
- The response format instructions
- The personality section
- The voice mode
- The verbosity
- The conversational vs technical default style

A `home` variant Halbert gets the identical "use markdown formatting" response prompt as a `sysadmin` variant.

### A6. Voice mode (first_person / the_computer / hybrid) only changes pronouns

The voice setting in BeingConfig controls self-reference style:

- File: `halbert_core/halbert_core/prompts/agent_prompts.py`
- Lines 70-88: Three identity templates that differ only in pronoun usage ("I/my/me" vs "this system/the computer/it" vs hybrid)

It does not change format, verbosity, conversational register, or modality. It is purely a pronoun swap.

### A7. UserPreferences.verbosity is dead code

A verbosity field exists but is never consumed:

- File: `halbert_core/halbert_core/prompts/context.py`
- Line 225: `verbosity: str = "concise"  # minimal, concise, detailed, verbose`

The `UserPreferences` dataclass is defined and exported, but:
- It is never instantiated in any production code path
- `format_user_preferences()` (line 332) is only called from `ContextInjector` methods that are themselves never called in the agent's state machine path
- The state machine calls `build_planning_prompt()` and `build_response_prompt()` directly — neither accepts or uses verbosity

The concept exists in the code but is completely disconnected from the response generation pipeline.

### A8. The XML prompt system (output-format.xml) is loaded but never sent

A sophisticated output-format prompt component exists:

- File: `config/prompts/v2/base/output-format.xml`
- Contains length guidelines by context: `simple_question: 1-3 sentences`, `howto: Brief explanation + command`, `complex_problem: Structured with headers`, `debugging: Step-by-step with verification`, `explanation: As long as needed, but no fluff`
- Contains exclude rules: no unnecessary preamble, no obvious caveats, no emojis, no repetition of the question

The `PromptBuilder` assembles this component (along with identity, objectives, constraints, safety) via `build_base_prompt()`, which is called by `build_system_prompt()`. However, **`build_system_prompt()` is never called in production**. The state machine only calls:
- `build_planning_prompt()` — becomes the PLANNING turn's system message
- `build_response_prompt()` — becomes the RESPONDING turn's system message

Neither of these methods uses the PromptBuilder or loads the XML components. The entire `config/prompts/v2/` directory — identity, objectives, constraints, output-format, safety — is dead weight on the production path.

### A9. No mechanism for dynamic mode switching mid-conversation

The founder's vision includes the ability to switch between conversational and technical modes mid-conversation — e.g., the user asks "give me more detail" and the system switches from a brief conversational reply to a detailed technical response, or vice versa.

There is no mechanism for this. The response format is fixed in `build_response_prompt()`. The intent classifier runs on each incoming message but does not feed back into response style. There is no per-turn "response style" parameter, no conversation-level "current register" state, and no user-facing control to escalate or de-escalate verbosity.

### A10. The Home vs Workstation divide maps to variant but should be fluid

The founder noted that the Home vs Workstation distinction "sort of fits the same divide as Home vs Workstation" but wants it to "naturally be able to go back and forth." A sysadmin variant Halbert should still be conversational for a quick "how are you?" and a home variant should still give technical detail when asked "show me the HA config."

The current variant system is a static, startup-time switch. It does not adapt per-turn. The intent classifier has the raw signal (greeting vs troubleshooting) to drive this adaptively, but the signal is not wired to response style.

---

## Part B — The Design Questions

These are the open questions the founder wants the external reviewer to research and answer.

### B1. Voice assistant response design best practices

What are the established best practices for voice assistant response design? Specifically:
- How should a voice assistant handle responses that would naturally contain structured information (tables, lists, code) in a text context?
- What is the right approach for "conversational but accurate" — natural speech that doesn't sacrifice technical precision?
- How do leading voice assistants (Alexa, Google Assistant, Siri, ChatGPT Voice, Gemini Live) handle the transition between conversational and informational responses?
- What are the guidelines for response length in voice contexts vs text contexts?
- How should disambiguation and clarification work in voice vs text?

### B2. Dual-mode (voice + text) response generation

Should the system generate one response and adapt it for each modality, or generate different responses per modality? Specifically:
- Is it better to (a) generate a markdown response, then strip/transform it for TTS, or (b) tell the model upfront which modality it's responding in and let it shape the response accordingly?
- What are the trade-offs of each approach (quality, latency, complexity, consistency)?
- How do systems that support both voice and text (ChatGPT, Gemini) handle this internally?
- What is the right architecture for a system that may stream to both text UI and voice simultaneously?

### B3. Intent-driven response style

How should intent classification drive response style? Specifically:
- Should a greeting always be conversational, even on a sysadmin workstation?
- Should a troubleshooting request always be technical, even on a home variant?
- What is the right mapping between intent categories (greeting, farewell, troubleshooting, question, command, informational) and response styles (conversational, technical, hybrid)?
- Should the system detect "the user wants more detail" / "the user wants a summary" from phrasing, or should there be explicit controls?
- How should the system handle ambiguous intent (e.g., "how's the system?" could be a casual check-in or a serious diagnostic request)?

### B4. Conversational vs technical register

What defines "conversational" vs "technical" response style in practice? Specifically:
- Is it primarily about format (plain sentences vs markdown structure), verbosity (short vs detailed), or tone (casual vs formal)?
- Can a response be both conversational AND technically precise? What does that look like?
- How should the system handle the case where a conversational response needs to convey a command or code snippet?
- What is the right default for a sysadmin workstation — conversational or technical? What about for a home assistant?
- How do you avoid the "uncanny valley" where a voice assistant sounds too casual for serious system administration?

### B5. Mode switching UX

How should the user switch between conversational and technical modes? Specifically:
- Should it be implicit (detected from the user's phrasing), explicit (a UI control or voice command), or both?
- What phrasing should trigger escalation ("give me more detail", "show me the full output", "be more technical") vs de-escalation ("just give me the summary", "in plain English", "short version")?
- Should the mode persist across turns (once you ask for detail, stay detailed) or reset per turn?
- How should the UI indicate which mode the assistant is in, if at all?
- Is there a role for a persistent "verbosity" or "register" setting in addition to per-turn switching?

### B6. The variant-to-style mapping

Should the Home vs Workstation variant influence the default communication style, and if so, how? Specifically:
- Should a `home` variant default to conversational and a `sysadmin` variant default to technical?
- Or should both default to adaptive (intent-driven) with variant only influencing the baseline tone?
- How should `home-light` (the minimal variant) differ from `home` in communication style?
- Should the variant set a "floor" and "ceiling" on how conversational/technical the assistant can go, or should it be a soft default that intent can override?

### B7. Markdown-in-voice specifically

What is the right technical approach for handling markdown in voice output? Specifically:
- Should the model be told "do not use markdown" for voice turns, or should it always produce markdown and a post-processor strips it?
- If post-processing: what is the correct transformation? (Strip headers, convert bullet lists to spoken lists, convert code blocks to "here's the command: ...", convert bold to emphasis?)
- If model-level: does telling the model "respond in plain text, no markdown" degrade the quality of its reasoning or structure?
- How should code snippets be handled in voice? Spoken character-by-character? Summarized? Skipped with "I've put the command in the chat"?

### B8. Wiring the existing dead code

The codebase has two mechanisms that already encode the right concepts but are not connected:
- `UserPreferences.verbosity` (minimal/concise/detailed/verbose) — never instantiated
- `output-format.xml` with context-sensitive length guidelines — never sent to the model

Should these be wired in as part of this work, or should they be replaced with a new system? If wired in:
- How should `verbosity` interact with intent-driven style (does a greeting override verbosity=detailed)?
- How should the `output-format.xml` length guidelines interact with modality (the "1-3 sentences" guideline for simple questions is right for voice but may be too short for text)?
- Should `output-format.xml` gain modality-specific rules, or should there be separate prompt components for voice vs text?

---

## Part C — External Review

> **Instructions for the external reviewer:** Write your research, findings, and recommendations below. Structure your response however you see fit, but address the questions in Part B. Cite sources where possible. Reference Part A findings by number (e.g., "Regarding A3...") when relevant. Disagree with the findings where warranted.

### Reviewer Information
- **Reviewer:** _(name/model)_
- **Date:** _(date)_
- **Research conducted:** _(brief summary of sources consulted)_

### Research Findings

_(Write your research here)_

### Recommendations

_(Write your recommendations here)_

### Disagreements with Part A Findings

_(Note any findings you disagree with or think are mischaracterized)_

### Suggested Architecture

_(If you have a specific architectural recommendation for how to implement modality-aware, intent-driven response style, describe it here)_

### Open Questions for the Founder

_(List any questions you have that would refine your recommendations)_

---

## Appendix — File Reference Index

| Finding | File | Lines | What to look at |
|---------|------|-------|-----------------|
| A1 | (entire codebase) | — | No matches for modality/output_channel/will_be_spoken |
| A2 | `halbert_core/halbert_core/prompts/agent_prompts.py` | 688-697 | `build_response_prompt()` — hardcoded markdown instruction |
| A3 | `halbert_core/halbert_core/audio/speech/tts_engine.py` | 113-119 | `synthesize()` — no markdown stripping before TTS |
| A4 | `halbert_core/halbert_core/intake/signals.py` | 387-403 | Intent classifier — exists but doesn't drive response style |
| A4b | `halbert_core/halbert_core/intake/pipeline.py` | 190-231 | `MessageIntake` assembly — intent flows to tier routing, not format |
| A5 | `halbert_core/halbert_core/config/being_config.py` | 226 | `variant` field — sysadmin/home/home-light |
| A5b | `halbert_core/halbert_core/dashboard/app.py` | 423-477 | Variant only gates service startup |
| A5c | `halbert_core/halbert_core/integrations/cognition_wiring.py` | 81-93 | `_get_variant()` resolution |
| A6 | `halbert_core/halbert_core/prompts/agent_prompts.py` | 70-88 | Voice templates — pronoun swap only |
| A7 | `halbert_core/halbert_core/prompts/context.py` | 225 | `UserPreferences.verbosity` — dead code |
| A8 | `config/prompts/v2/base/output-format.xml` | 1-45 | Output format guidelines — loaded but never sent |
| A8b | `halbert_core/halbert_core/prompts/builder.py` | 26-32, 90-167 | `PromptBuilder` — assembles XML but `build_system_prompt()` is never called |
| A8c | `halbert_core/halbert_core/agents/state_machine.py` | 2680, 1653 | State machine only calls `build_response_prompt()` and `build_planning_prompt()` |
| A9 | (no file) | — | No per-turn response style parameter exists |
| A10 | `halbert_core/halbert_core/config/being_config.py` | 226 | Variant is static, startup-time only |
