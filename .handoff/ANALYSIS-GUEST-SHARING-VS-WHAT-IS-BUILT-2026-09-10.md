# The guest persona: what "Halbert shares in normal mode" would take

**Date:** 2026-09-10
**Status:** analysis for a founder decision. **Nothing changed.** Every gap below is a
deliberate design decision with a stated reason, not an oversight.
**Trigger:** the founder's framing — *"Halbert is the only deviation, because there are home
automation tasks and important IT tasks, and the main Halbert might need to share with the
guest persona; only Private mode is the fully isolated memory. All the other apps have a 1:1
memory-to-persona ratio."*

The 1:1 half is settled and correct: Halley scopes on `persona_id`, BrightestMinds on the
figure's own id, and the shared-memory proposal made against that was retracted the same day.
This document is only about Halbert.

---

## 1. The stated model versus what is built

| The founder's model | What the code does | Verdict |
|---|---|---|
| Guest does **home automation** | `ha_get_entity_state`, `ha_call_service` are on the guest allowlist | ✅ **already works** |
| Guest does **important IT tasks** | every host tool is denied — `run_command`, `read_file`, `write_file`, `list_directory`, `terminal_blocks`, `get_cpu_info`, `get_disk_usage`, `get_memory_info`, `get_network_info`, `get_process_list`, `get_service_status`, screen capture, `web_search`, scripts | ❌ **deliberately refused** |
| Main Halbert **shares memory** with the guest | `recall_memory`, `recall_thread`, `resume_thread` denied; `recall_guest_memory` is documented *"The guest reads what it wrote (I6). **Never Halbert's memory.**"* | ❌ **not implemented, in either mode** |
| **Only private mode** is fully isolated | the guest tool profile has **no mode check at all** — normal mode is equally restricted | ❌ **normal mode is already isolated** |

The reason for row 2 is written down in `guest_tools.py`: *"A guest is for the home and for
company, **not for administering the host** (design §1)."* That is a decision against the
founder's stated need, not a gap someone forgot to fill.

---

## 2. The useful finding: I6, applied per-mode, *derives* the founder's model

`I6` (design §6.3 R1) is the invariant blocking row 3:

> The guest *reading* Halbert's memory while writing to a store Halbert cannot see or erase is
> a one-way valve out of the user's own machine. **The guest may not read what it may not write.**

It is currently applied at its most restrictive in **both** modes. But `route_write` already
routes writes differently by mode:

| Writer | Normal mode | Private mode |
|---|---|---|
| `conversation.message` | **HALBERT** | GUEST |
| `cognition.tick` | GUEST | GUEST |
| world kinds | HALBERT | HALBERT |

So in **normal mode the guest already writes into Halbert's conversation store.** By I6's own
logic — may not read what it may not write — the guest *may* read that store in normal mode,
because it writes there. The valve I6 exists to close is not open in that direction.

**I6 therefore does not forbid the founder's model; it produces it:**

- **Normal mode** — guest writes to Halbert's conversation store, so it may read it.
  Symmetric, no valve. `recall_thread` / `resume_thread` become I6-compliant.
- **Private mode** — `conversation.message` goes to the guest's home instead, so the guest
  stops writing to Halbert's store and must stop reading it. Symmetric, valve closed.

That is exactly *"only private mode is the fully isolated memory."* The current
implementation is **stricter than I6 requires**, not required by it.

**The one thing that should not move: `cognition.tick`.** It is GUEST in every mode by `R2`,
whose reason is *"Halbert's own psyche never learns a guest's evenings."* That is the same
character-protection principle that settled the BrightestMinds question, and it should
survive. Sharing the **conversation** is not the same as merging the **psyche**, and only the
first is being proposed here.

---

## 3. IT tools are a different question, and should not ride on I6

I6 is about *memory exfiltration*. A live-state read is not memory, which is why the guest can
already read HA entity state — world — without breaching it. So the IT question is a
capability-and-trust decision, and it decomposes:

| Class | Examples | Exfiltration risk | Note |
|---|---|---|---|
| **IT reads** | `get_service_status`, `get_cpu_info`, `get_disk_usage`, `get_network_info`, `get_process_list` | low — live state, not memory | the smallest change that makes a guest useful for IT |
| **Screen** | `capture_screenshot`, `capture_window`, `capture_and_ocr` | high — *"the screen is the workstation's, not the house's"* | reads whatever the user has open |
| **Host writes / execution** | `run_command`, `write_file`, `terminal_blocks`, the script pipeline | highest | denial is pinned in `tests/tools/test_execute_code.py` **at every layer** |

If the guest is to do IT work, the defensible increment is **IT reads in normal mode only**.
Execution is a different order of risk and the test suite was deliberately built to stop it.

---

## 4. What a decision here would need to say

1. **Does the guest do IT at all?** Design §1 says no on purpose. If yes, scope it: reads only,
   normal mode only, or more?
2. **Open `recall_thread` / `resume_thread` in normal mode?** I6 permits it (§2). This is the
   cheapest way to make "Halbert shares with the guest" true, and it needs a mode check in the
   allowlist, which does not exist yet.
3. **Confirm `cognition.tick` stays GUEST in both modes** (R2, psyche protection). Recommended
   unchanged.
4. Any of this makes the guest tool profile **mode-dependent for the first time.** That is a
   security-relevant structural change: `GUEST_ALLOWED_TOOLS` is currently a single frozenset
   and its docstring says *"The allowlist is the authoritative check… Adding a tool to the
   allowlist is a code change and a security review."* A mode-conditional allowlist needs the
   same review, plus tests pinning that private mode never widens.

**Still open regardless, from the 2026-09-08 facade finding:** a facade turn in normal mode
writes to Halbert's conversation store *and* the guest's remote home, and `SiblingClient` has
`memory_add` / `memory_search` and **no delete** — so "forget that" reaches two planes and
misses the third. `ERASURE_LIMITS` does not name the guest's home. Unchanged by anything here.
