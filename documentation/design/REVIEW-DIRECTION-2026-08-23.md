# Review: Overall Direction and Planning

**Status:** Stub — to be filled in by external reviewer.
**Reviewer:** [name]
**Date:** [date]
**Reads with:** `.handoff/HANDOFF-REVIEW-2026-08-23.md` (the handoff brief)

---

## How to use this document

This is your working document. Fill in each section with your notes,
suggestions, and critique. Delete the scaffolding prompts when you've
addressed them. Add new sections as needed.

The handoff brief asked for notes, suggestions, and critique on the
overall direction and planning — the "are we building the right thing"
question. Be direct. Point out what's missing. Propose alternatives.

---

## 1. First impression

[After reading the vision, the explorations catalog, the roadmap, and the
implementation plan — what's your immediate reaction? What feels right?
What feels wrong? What's the thing that made you go "hmm"?]

---

## 2. Scope assessment

### 2.1 Is the two-slice MVP the right cut?

[The plan defines two proof slices: (1) proactive config worry — the being
detects a config problem and tells you with its why; (2) reactive "how are
you?" — the being answers as itself with evidence and a summoned vitals
module. Is this the right MVP? Should it be one slice done deeper? A
different slice entirely?]

### 2.2 Are we trying to do too much?

[The implementation plan has 62 tasks across 8 phases. The critical path
is Phase 0 → 2 → 3 → 4 → 4.5 → 5/6 → 7 → 8. Is this too ambitious? Where
would you cut?]

### 2.3 Are we trying to do too little?

[Is there a category of work that's obviously missing from the plan? The
handoff brief lists: error handling, observability, accessibility, i18n,
mobile/remote, multi-user, security model, testing strategy, deployment.
Are any of these blocking? Which ones can truly wait?]

---

## 3. Sequencing and dependencies

### 3.1 The critical path

[The dependency chain is long. Where could we parallelize more? Where could
we cut scope to land a slice sooner? Is the boot-test gate (Phase 4.5) in
the right place?]

### 3.2 Phase 0 and Phase 1 parallelism

[The plan says Phase 0 (RAG corpus) and Phase 1 (intake pipeline) run in
parallel. Is this right? Are there hidden dependencies?]

### 3.3 The being layers (Phases 5-8)

[Phases 5-8 depend on the infrastructure spine (0-4.5) being complete. Is
there any being-layer work that could start earlier? Could the config
detectors (Phase 5c) be prototyped before the boot-test gate?]

---

## 4. Architectural blind spots

### 4.1 Three stores (SourcePrep, memory_v2, SQLite)

[The plan defines three stores with clear ownership: SourcePrep (system
knowledge + docs + rationale + ops memory), memory_v2 (episodic
conversation history), SQLite (findings + proposals + approvals). Is this
the right split? Are there ownership ambiguities? Is SQLite the right
choice for findings?]

### 4.2 Two SourcePrep projects (halbert-knowledge, halbert-host)

[The plan defines two SourcePrep projects: halbert-knowledge (the RAG
corpus — man pages, Arch Wiki, etc.) and halbert-host (the live config
tree). Is this the right boundary? Should they be one project with scopes?
Should there be a third (halbert-self for self-knowledge/observations)?]

### 4.3 ChromaDB retirement strategy

[ChromaDB is being retired from the chat path but kept for eval + telemetry
+ discovery. Is this the right migration strategy? Is keeping ChromaDB
around a maintenance burden? Should we migrate everything off it?]

### 4.4 The dual chat path retirement

[chat.py (3,914 lines) is being retired in favor of agent.py (736 lines).
Features are ported before endpoints are cut. Is this the right approach?
Is there a risk of feature loss? Should we cut chat.py sooner and accept
temporary feature loss?]

---

## 5. Missing categories of work

### 5.1 Error handling and degraded states

[The plan mentions graceful degradation in passing (SourcePrep down →
empty results, macOS → no journald). But there's no systematic error
handling strategy. What should it be? What are the failure modes? How does
the being explain its own limitations?]

### 5.2 Observability

[The intake pipeline has a `get_stats()` endpoint. The complexity router
tracks cache hits/misses. But there's no unified observability strategy
for the being itself. How do we know if retrieval quality is degrading?
How do we know if the being is being too noisy? Too quiet? What metrics
matter?]

### 5.3 Security model for the proactive channel

[The proactive channel pushes findings to the user. A finding might
contain sensitive config details (e.g., "sshd_config has
PermitRootLogin yes"). If the push goes through a tray notification, does
the OS notification leak sensitive content? How should findings be
sanitized for different surfaces (notification vs in-app vs CLI)?]

### 5.4 Testing strategy

[The plan has unit tests for each module. But there's no integration test
strategy, no end-to-end test strategy, no retrieval quality eval beyond
"20 test queries." What should the testing pyramid look like?]

### 5.5 Deployment and packaging

[The plan doesn't mention how Halbert gets installed on the target host.
Is it a pip install? A Tauri bundle? A systemd service? How does the
SourcePrep daemon get installed and managed? How does Haloysius get
installed?]

### 5.6 Other missing categories

[Add any other missing categories here: accessibility, i18n, mobile/remote
access, multi-user, etc.]

---

## 6. The RAG corpus plan

### 6.1 Corpus quality vs quantity

[The RAG plan cleans 30K docs down to ~15K unique. Is this the right
balance? Should we be more aggressive in cutting? Less aggressive? Are
there sources we should add that aren't in the plan?]

### 6.2 Cross-platform docs

[The plan suggests a `data/common/` directory for cross-platform tools
(git, ssh, bash). Is this the right approach? Or should platform-specific
docs stay separate and let retrieval figure it out?]

### 6.3 Retrieval quality measurement

[The plan proposes 20 test queries. Is this enough? Should there be a
larger eval set? A continuous eval pipeline? How do we measure retrieval
quality over time as the corpus changes?]

---

## 7. The being concept

### 7.1 Is the "being" framing right?

[The vision says "an LLM that identifies as the computer itself." The voice
setting defaults to first person ("I'm worried about /dev/sda1"). Is this
the right framing? Does it help or hurt adoption? Does it create
unrealistic expectations?]

### 7.2 Proactive agency

[The proactivity dial (off/quiet/balanced/assertive) is the main control.
Is this the right abstraction? Should there be more granularity? Should
the being learn from user behavior (the attention-learning loop mentioned
as post-MVP)? Is "balanced" the right default?]

### 7.3 The morning report

[Is a morning report the right ritual? Is daily the right cadence? Should
it be configurable? Should the being also do a "Sunday backup review" or
"monthly storage audit" as mentioned in the deeper veins?]

---

## 8. Things we may have obviously missed

[The "senior engineer who has built a similar product" check. What would
someone with experience building a system monitoring + conversational AI
product immediately flag?]

---

## 9. Suggestions for the implementation plan

[Concrete changes to the plan: tasks to add, tasks to remove, tasks to
reorder, tasks to merge. Reference task IDs (T1a.1, T2a.1, etc.) where
relevant.]

---

## 10. Summary assessment

[Your overall assessment: are we building the right thing? Are we building
it the right way? What's the one thing you'd change first?]
