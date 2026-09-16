# Inline Permission Surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Date:** 2026-09-16
**Branch:** `fix/sec-2-readonly-lane` (worktree `.claude/worktrees/sec-2-lane`), or a fresh branch off it.
**Goal:** Replace the modal permission popup with an inline, in-conversation pending-action surface, and give the ask the three affordances it lacks — a reason on denial, an "always allow" that drains the prompt, and a visible countdown — routing the terminal's ask (ruling B) through the same surface.
**Architecture:** One React component, `PendingActionEntry`, mirroring the existing inline `DiffBlock` (status `pending → approved/denied/expired`, read-only in past turns). It renders in the conversation flow above the composer — never as an overlay — and in the terminal tile. The agent path already emits `tool_confirmation_required` and resumes via `/api/agent/confirm`; the terminal path already answers `428` and carries `force`. This plan adds a `reason` to the confirm round-trip, an owner-only route that appends to the existing `command-allowlist.json`, and a client-side countdown.
**Tech stack:** FastAPI + Pydantic (backend), React 18 + TypeScript + Vitest + Testing Library (frontend), the shared design tokens in `shared-tokens/tokens.css`.

**Founder constraint (2026-09-16), binding on every task:** *No alert-style popups.* Permissions are communicated at the product level — in the conversation, at the tail of the current response, as a pending state the person acts on in place. `ConfirmationDialog.tsx` (a `fixed inset-0 bg-black/70 z-50` overlay) is the anti-pattern this plan retires.

**Prior art read for this plan (design only; AGPL/other — never lift code):** cdesktop's `PendingApprovalEntry.tsx` (an entry *in* the conversation timeline: countdown from `timeout_at`, Approve / Deny-with-reason, `aria-busy` while responding, resolved `approved|denied` state) and `SessionChatBoxContainer.tsx` (the composer stays usable, the approval is a separate entry keyed by `approval_id`); Warp's AI-block approval (`Run`/`Cancel` inline on the block, `Enter → Accept`, a one-shot "why am I asking" speedbump, an in-situ setting toggle). Full comparison: `.handoff/RESEARCH-PERMISSION-MODELS-2026-09-16.md`.

---

## 0. Scope

**In scope (this plan, ready now — research options 1–4):** the agent-conversation permission ask and the terminal (ruling B) permission ask, unified onto one inline surface with reason, always-allow, and countdown.

**Out of scope, and why:**
- **The permission Profile (research options 5–6).** Warp's per-capability dial with Halbert's classifier in the middle. It is blocked on five founder questions (see §Plan B, and `RESEARCH-PERMISSION-MODELS-2026-09-16.md` §8). It cannot be written as bite-sized TDD until those land; sketched at the end.
- **The settings-tab modals** (`ui/confirm-dialog.tsx`'s `ConfirmDialog`, used by `AboutYouCard`, `DeviceCard`, `DevicesTab`, `EntityIdentityCard`, `ReplicaStatus`; `ui/dialog.tsx` used by `Onboarding`). These are destructive-action confirms in Settings, not agent permission asks. Whether they also move off modals is a separate founder call, noted not assumed. **Do not touch them in this plan.**
- **A backend auto-deny timer.** The countdown in Task 5 is client-driven (as it visually is in cdesktop). If the browser is gone, the turn stays paused — no worse than today. A server-side watcher that resumes a paused turn as denied is real work touching the turn lock; deferred and named in §Plan B.

**A running note for every task:** frontend verification runs from the worktree with the main checkout's `node_modules` symlinked in, then removed before committing:
```bash
cd halbert_core/halbert_core/dashboard/frontend
ln -sfn /Volumes/4TB-BAD/Halbert/halbert_core/halbert_core/dashboard/frontend/node_modules node_modules
./node_modules/.bin/vitest run <path>
./node_modules/.bin/tsc --noEmit -p tsconfig.json   # baseline: one pre-existing Onboarding.test.tsx TS6133
rm -f node_modules
```
Python tests run from the worktree root: `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py <paths>`.

---

## File structure

**Backend (Python):**
- `halbert_core/halbert_core/dashboard/routes/agent.py` — `ConfirmActionRequest` gains `reason`; the confirm route threads it. *(Task 2)*
- `halbert_core/halbert_core/agents/state_machine.py` — `confirm_action` gains `reason`, woven into the rejection observation at `:1679`. *(Task 2)*
- `halbert_core/halbert_core/tools/safety.py` — a `save_user_command_override(binary, first_operand)` writer beside `load_user_command_overrides`. *(Task 4)*
- `halbert_core/halbert_core/dashboard/routes/terminal.py` — an owner-only `POST /api/terminal/allowlist` route. *(Task 4)*

**Frontend (TypeScript/React):**
- `.../src/components/agent/PendingActionEntry.tsx` — **new.** The inline surface. *(Task 1)*
- `.../src/components/agent/PendingActionEntry.test.tsx` — **new.** *(Tasks 1–5)*
- `.../src/hooks/useAgentStream.ts` — `ConfirmationRequest` gains `command?`, `alwaysAllowable?`, `arrivedAt`; `confirmAction` gains `reason`. *(Tasks 2, 3, 5)*
- `.../src/components/agent/AgentChat.tsx` — retire the modal mount (`:1513`); render `PendingActionEntry` in-flow. *(Tasks 1, 6)*
- `.../src/components/agent/ConfirmationDialog.tsx` — **deleted** at the end. *(Task 6)*
- `.../src/lib/api.ts` — `api.terminalAllowlist(binary, firstOperand)`. *(Task 4)*
- `.../src/components/agent/TerminalTile.tsx` + `.../src/hooks/useTerminalSessions.ts` — surface `SpawnNeedsConfirmation` as a `PendingActionEntry` in the tile. *(Task 5)*

---

## Task 1: The inline pending-action entry (replaces the modal)

**Files:**
- Create: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/PendingActionEntry.tsx`
- Create: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/PendingActionEntry.test.tsx`
- Modify: `halbert_core/halbert_core/dashboard/frontend/src/components/agent/AgentChat.tsx:1513-1518`

The component mirrors `DiffBlock.tsx` (same `statusColors`, same inline header, same read-only-in-past-turns rule) so the conversation reads as one system. It is **in-flow**, never `fixed`/`inset`/`z-50`.

- [ ] **Step 1: Write the failing test**

```tsx
// PendingActionEntry.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PendingActionEntry, type PendingAction } from './PendingActionEntry'

const base: PendingAction = {
  actionId: 'exec-1',
  tool: 'run_command',
  description: '**Execute command:**\n```\nhostname evil\n```',
  riskLevel: 'high',
  status: 'pending',
}

describe('PendingActionEntry', () => {
  it('renders in flow, not as a modal overlay', () => {
    const { container } = render(
      <PendingActionEntry action={base} onApprove={() => {}} onDeny={() => {}} />)
    // The whole point of ruling-B UI: no fixed overlay, no backdrop, no dialog role.
    expect(container.querySelector('.fixed')).toBeNull()
    expect(container.querySelector('[role="dialog"]')).toBeNull()
    expect(container.querySelector('[aria-modal]')).toBeNull()
  })

  it('approves and denies through its buttons', async () => {
    const onApprove = vi.fn(); const onDeny = vi.fn()
    render(<PendingActionEntry action={base} onApprove={onApprove} onDeny={onDeny} />)
    await userEvent.click(screen.getByRole('button', { name: /approve/i }))
    expect(onApprove).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole('button', { name: /deny/i }))
    expect(onDeny).toHaveBeenCalled()
  })

  it('is read-only in a past turn — shows the outcome, offers no buttons', () => {
    render(<PendingActionEntry action={{ ...base, status: 'denied' }} readOnly
      onApprove={() => {}} onDeny={() => {}} />)
    expect(screen.getByText(/denied/i)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /approve/i })).toBeNull()
  })
})
```

- [ ] **Step 2: Run it, watch it fail**

```bash
./node_modules/.bin/vitest run src/components/agent/PendingActionEntry.test.tsx
```
Expected: FAIL — `Cannot find module './PendingActionEntry'`.

- [ ] **Step 3: Write the component**

```tsx
// PendingActionEntry.tsx
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState } from 'react';
import { Check, X, ShieldQuestion } from 'lucide-react';
import { renderDescription } from './ConfirmationDialog';

export interface PendingAction {
  actionId: string;
  tool: string;
  /** Markdown-ish; the confirmation message the classifier produced. */
  description: string;
  riskLevel: string;
  status: 'pending' | 'approved' | 'denied' | 'expired';
  /** The raw command, when the tool is run_command — enables "always allow". */
  command?: string;
  /** Whether "always allow this" applies (a vouchable run_command). */
  alwaysAllowable?: boolean;
}

interface Props {
  action: PendingAction;
  readOnly?: boolean;
  onApprove: () => void;
  onDeny: (reason?: string) => void;
  onAlwaysAllow?: () => void;
}

// Mirror DiffBlock's palette so the ask reads as the same system.
const statusColors: Record<PendingAction['status'], string> = {
  pending: 'border-status-warning-line bg-status-warning-bg',
  approved: 'border-success/50 bg-success-muted dark:bg-success/5',
  denied: 'border-error/50 bg-error-muted dark:bg-error/5',
  expired: 'border-border bg-muted/40',
};

export function PendingActionEntry({ action, readOnly, onApprove, onDeny, onAlwaysAllow }: Props) {
  const [denying, setDenying] = useState(false);
  const [reason, setReason] = useState('');
  const live = action.status === 'pending' && !readOnly;

  return (
    <div
      className={`rounded-md border ${statusColors[action.status]} overflow-hidden`}
      // A live region, not a dialog: assistive tech hears it where it sits in
      // the conversation, and focus is never trapped away from the composer.
      role="group"
      aria-label={`Permission requested: ${action.tool}`}
    >
      <div className="flex items-center gap-1.5 px-2 py-1.5 bg-muted/50 border-b">
        <ShieldQuestion className="h-3 w-3 text-status-warning" />
        <span className="text-[10px] font-medium text-status-warning uppercase tracking-wide">
          {action.status === 'pending' ? 'Awaiting your approval' : action.status}
        </span>
      </div>
      <div
        className="px-3 py-2 text-[11px] text-foreground"
        dangerouslySetInnerHTML={{ __html: renderDescription(action.description) }}
      />
      {live && !denying && (
        <div className="flex items-center justify-end gap-1 px-2 py-1.5 border-t">
          {action.alwaysAllowable && onAlwaysAllow && (
            <button
              onClick={onAlwaysAllow}
              className="px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-text rounded"
            >
              Always allow this
            </button>
          )}
          <button
            onClick={() => setDenying(true)}
            className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] text-destructive hover:bg-destructive/10 rounded"
          >
            <X className="h-2.5 w-2.5" /> Deny
          </button>
          <button
            onClick={onApprove}
            className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] text-success bg-success-muted dark:bg-success/10 hover:bg-success/20 rounded"
          >
            <Check className="h-2.5 w-2.5" /> Approve
          </button>
        </div>
      )}
      {live && denying && (
        <form
          className="flex flex-col gap-1 px-2 py-1.5 border-t"
          onSubmit={(e) => { e.preventDefault(); onDeny(reason.trim() || undefined); }}
        >
          <textarea
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Optional: tell it why, so it doesn't try the same thing"
            className="text-[11px] bg-background border border-border rounded p-1 resize-none"
            rows={2}
          />
          <div className="flex justify-end gap-1">
            <button type="button" onClick={() => setDenying(false)}
              className="px-1.5 py-0.5 text-[10px] text-muted-foreground rounded">Cancel</button>
            <button type="submit"
              className="px-1.5 py-0.5 text-[10px] text-destructive bg-destructive/10 rounded">Deny</button>
          </div>
        </form>
      )}
      {action.status === 'approved' && (
        <div className="flex items-center gap-0.5 px-2 py-1.5 border-t text-[10px] text-success">
          <Check className="h-2.5 w-2.5" /> Approved
        </div>
      )}
      {action.status === 'denied' && (
        <div className="flex items-center gap-0.5 px-2 py-1.5 border-t text-[10px] text-destructive">
          <X className="h-2.5 w-2.5" /> Denied
        </div>
      )}
      {action.status === 'expired' && (
        <div className="px-2 py-1.5 border-t text-[10px] text-muted-foreground">Expired — not run</div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run it, watch it pass**

```bash
./node_modules/.bin/vitest run src/components/agent/PendingActionEntry.test.tsx
```
Expected: PASS (3 tests). If `renderDescription` import fails, confirm it is exported from `ConfirmationDialog.tsx:51` (it is) — the export survives until Task 6 moves it.

- [ ] **Step 5: Mount it in-flow, retire the overlay**

In `AgentChat.tsx`, replace the modal mount at `:1513-1518`:

```tsx
// BEFORE (delete):
{session?.pendingConfirmation && (
  <ConfirmationDialog
    confirmation={session.pendingConfirmation}
    onConfirm={() => confirmAction(session.pendingConfirmation!.actionId, true)}
    onReject={() => confirmAction(session.pendingConfirmation!.actionId, false)}
  />
)}
```

Move this render into the conversation column, immediately before the composer (the same column that holds `<Timeline>`), so it sits at the tail of the current response:

```tsx
{session?.pendingConfirmation && (
  <div className="px-3 pb-2">
    <PendingActionEntry
      action={{
        actionId: session.pendingConfirmation.actionId,
        tool: session.pendingConfirmation.tool,
        description: session.pendingConfirmation.description,
        riskLevel: session.pendingConfirmation.riskLevel,
        status: 'pending',
      }}
      onApprove={() => confirmAction(session.pendingConfirmation!.actionId, true)}
      onDeny={(reason) => confirmAction(session.pendingConfirmation!.actionId, false, reason)}
    />
  </div>
)}
```

Add `import { PendingActionEntry } from './PendingActionEntry';` and remove the `ConfirmationDialog` import (its file is deleted in Task 6). `confirmAction`'s third argument arrives in Task 2 — until then TypeScript accepts the 2-arg call and the `reason` is dropped; the plan wires it next.

- [ ] **Step 6: Verify and commit**

```bash
./node_modules/.bin/vitest run src/components/agent/PendingActionEntry.test.tsx
./node_modules/.bin/tsc --noEmit -p tsconfig.json   # only the Onboarding baseline
git add src/components/agent/PendingActionEntry.tsx src/components/agent/PendingActionEntry.test.tsx src/components/agent/AgentChat.tsx
git commit -m "feat(ui): an inline pending-action entry replaces the permission modal

The ask now sits in the conversation at the tail of the response, styled
like DiffBlock, never as a fixed overlay. Founder constraint, 2026-09-16:
permissions communicate at the product level, not through popups."
```

---

## Task 2: Deny with a reason

**Files:**
- Modify: `halbert_core/halbert_core/dashboard/routes/agent.py:104-107` (`ConfirmActionRequest`), `:2016-2023` (the call)
- Modify: `halbert_core/halbert_core/agents/state_machine.py:1572-1583` (signature), `:1671-1683` (the observation)
- Modify: `.../src/hooks/useAgentStream.ts:1353` (`confirmAction`), `:1377` (the body)
- Test: `halbert_core/tests/test_agent_confirm_reason.py` (new), `PendingActionEntry.test.tsx`

The rejection already writes a model-visible observation at `state_machine.py:1679`. The reason is woven into it.

- [ ] **Step 1: Write the failing backend test**

```python
# halbert_core/tests/test_agent_confirm_reason.py
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import StateContext, ToolCall


def _ctx_with_pending():
    ctx = StateContext(session_id="s1", request_id="r1")
    ctx.tool_calls = [ToolCall(id="exec-1", name="run_command", args={"command": "hostname evil"})]
    ctx.pending_confirmation = {"action_id": "exec-1", "tool": "run_command",
                                "description": "…", "risk_level": "high"}
    return ctx


def test_denial_reason_reaches_the_next_planning_pass():
    """The user's words are woven into the observation the model re-plans on."""
    sm = AgentStateMachine.__new__(AgentStateMachine)
    ctx = _ctx_with_pending()
    # Exercise only the rejection-observation logic, not the whole turn loop.
    sm._weave_rejection(ctx, "exec-1", reason="that would take the box offline")
    obs = " ".join(ctx.observations)
    assert "hostname evil" in obs
    assert "that would take the box offline" in obs
    assert "Do not propose it again" in obs
```

*(This assumes the rejection-observation logic is extracted into a small pure `_weave_rejection(ctx, action_id, reason)` helper. Step 3 extracts it from the inline block at `:1671-1683` so it is unit-testable without driving a turn.)*

- [ ] **Step 2: Run it, watch it fail**

```bash
arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_agent_confirm_reason.py -v
```
Expected: FAIL — `AttributeError: … '_weave_rejection'`.

- [ ] **Step 3: Extract the helper and weave the reason**

In `state_machine.py`, replace the inline rejection block (`:1671-1684`) with a call to a new method, and add the method (place it just above `confirm_action`, near `:1571`):

```python
def _weave_rejection(self, ctx, action_id: str, reason: Optional[str] = None) -> None:
    """Settle a rejected call and name it for the next PLANNING pass.

    Naming *what* was refused stops _already_called() proposing it again;
    the user's own reason, when given, tells the model why so it can offer
    a real alternative rather than a near-duplicate.
    """
    rejected = next((tc for tc in ctx.tool_calls if tc.id == action_id), None)
    if rejected is not None and rejected.id == action_id:
        rejected.status = "error"
        rejected.error = "rejected by user"
        note = (f"The user refused to run {rejected.name}({rejected.args}). "
                "Do not propose it again; answer without it or suggest a different approach.")
        if reason:
            note += f" They said: {reason!r}"
        ctx.add_observation(note)
    else:
        ctx.add_observation(
            f"User rejected the action. They said: {reason!r}" if reason
            else "User rejected the action")
```

Then in `confirm_action`, add `reason: Optional[str] = None` to the signature (after `confirmed`, `:1576`) and replace the `else:` branch body (`:1664-1684`) with:

```python
else:
    # User rejected - go back to planning
    self.ctx.pending_confirmation = None
    self._weave_rejection(self.ctx, action_id, reason)
    yield self._set_conversation_status(ConversationStatus.IN_PROGRESS)
    yield await self._transition(AgentState.PLANNING)
```

- [ ] **Step 4: Run it, watch it pass**

```bash
arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_agent_confirm_reason.py -v
```
Expected: PASS.

- [ ] **Step 5: Thread the reason through the route**

In `agent.py`, add to `ConfirmActionRequest` (`:104-107`):

```python
    reason: Optional[str] = Field(None, description="Optional denial reason, shown to the model so it does not re-propose the refused action")
```
and in the confirm route's call (`:2016-2023`), add the argument:

```python
                async with aclosing(agent.confirm_action(
                    session_id,
                    request.action_id,
                    request.confirmed,
                    reason=request.reason,
                    model_override=model_override,
                    tier_override=tier_override,
                    history_budget=history_budget,
                )) as stream:
```

- [ ] **Step 6: Run the route auth + confirm tests, commit the backend**

```bash
arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_agent_confirm_reason.py halbert_core/tests/test_route_auth_census.py -q
git add halbert_core/halbert_core/agents/state_machine.py halbert_core/halbert_core/dashboard/routes/agent.py halbert_core/tests/test_agent_confirm_reason.py
git commit -m "feat(agents): a denial can carry the user's reason to the model

confirm_action(reason=...) weaves the user's words into the rejection
observation the next PLANNING pass reads, so a refusal teaches the model
what to do instead of leaving it to re-propose a near-duplicate."
```

- [ ] **Step 7: Wire the reason on the frontend (failing test first)**

Add to `PendingActionEntry.test.tsx`:

```tsx
it('passes the typed reason to onDeny', async () => {
  const onDeny = vi.fn()
  render(<PendingActionEntry action={base} onApprove={() => {}} onDeny={onDeny} />)
  await userEvent.click(screen.getByRole('button', { name: /deny/i }))       // opens the form
  await userEvent.type(screen.getByRole('textbox'), 'takes the box offline')
  await userEvent.click(screen.getByRole('button', { name: /^deny$/i }))     // submits
  expect(onDeny).toHaveBeenCalledWith('takes the box offline')
})
```
Run: `./node_modules/.bin/vitest run src/components/agent/PendingActionEntry.test.tsx` — the reason form from Task 1 Step 3 already implements this, so this test should PASS on write. If it fails, the form's submit handler is the fix, not the test.

- [ ] **Step 8: Extend `confirmAction` to send the reason**

In `useAgentStream.ts`, change `confirmAction`'s signature (`:1353`) and body (`:1377`):

```ts
const confirmAction = useCallback((actionId: string, confirmed: boolean, reason?: string) => {
  // …unchanged setup…
  body: JSON.stringify({ action_id: actionId, confirmed, ...(reason ? { reason } : {}) }),
```
Update the `UseAgentStream` interface's `confirmAction` type (search the interface near `:328`) to `(actionId: string, confirmed: boolean, reason?: string) => void`.

- [ ] **Step 9: Verify and commit**

```bash
./node_modules/.bin/vitest run src/components/agent/PendingActionEntry.test.tsx src/hooks/useAgentStream.thread.test.ts
./node_modules/.bin/tsc --noEmit -p tsconfig.json
git add src/hooks/useAgentStream.ts src/components/agent/PendingActionEntry.test.tsx
git commit -m "feat(ui): the deny form carries a reason back to the agent"
```

---

## Task 3: The countdown, client-side

**Files:**
- Modify: `.../src/hooks/useAgentStream.ts` (`ConfirmationRequest` gains `arrivedAt`; set it at `:767`)
- Modify: `.../src/components/agent/PendingActionEntry.tsx` (a countdown, auto-deny at zero)
- Test: `PendingActionEntry.test.tsx`

The ask records when it arrived; the entry counts down from a default window and, at zero, calls `onDeny` with a fixed reason. No backend change — if the tab is gone the turn stays paused, exactly as today.

- [ ] **Step 1: Failing test (fake timers)**

```tsx
it('auto-denies when its window elapses', () => {
  vi.useFakeTimers()
  const onDeny = vi.fn()
  render(<PendingActionEntry action={{ ...base, timeoutMs: 5000 }} onApprove={() => {}} onDeny={onDeny} />)
  expect(onDeny).not.toHaveBeenCalled()
  vi.advanceTimersByTime(5001)
  expect(onDeny).toHaveBeenCalledWith('No response within the approval window.')
  vi.useRealTimers()
})

it('shows the seconds remaining while it waits', () => {
  vi.useFakeTimers()
  render(<PendingActionEntry action={{ ...base, timeoutMs: 30000 }} onApprove={() => {}} onDeny={() => {}} />)
  expect(screen.getByText(/30s|29s/)).toBeTruthy()
  vi.useRealTimers()
})
```
Add `timeoutMs?: number` to `PendingAction`.

- [ ] **Step 2: Run, watch fail** — `./node_modules/.bin/vitest run …PendingActionEntry.test.tsx` → FAIL (no countdown text; `onDeny` never fires).

- [ ] **Step 3: Add the countdown to `PendingActionEntry`**

```tsx
// inside the component, before the return:
const [remaining, setRemaining] = useState(action.timeoutMs ?? 0);
useEffect(() => {
  if (!live || !action.timeoutMs) return;
  const started = Date.now();
  const id = setInterval(() => {
    const left = action.timeoutMs! - (Date.now() - started);
    setRemaining(Math.max(0, left));
    if (left <= 0) { clearInterval(id); onDeny('No response within the approval window.'); }
  }, 500);
  return () => clearInterval(id);
}, [live, action.timeoutMs, onDeny]);
```
Render `{action.timeoutMs && live ? <span className="text-[10px] text-muted-foreground">{Math.ceil(remaining / 1000)}s</span> : null}` in the header row. Guard `onDeny` identity in the caller with `useCallback` so the effect does not re-arm each render.

- [ ] **Step 4: Run, watch pass.**

- [ ] **Step 5: Stamp arrival on the event**

In `useAgentStream.ts`, `ConfirmationRequest` gains `arrivedAt: number`, set at the `tool_confirmation_required` reducer (`:767`): `arrivedAt: Date.now()`. In `AgentChat.tsx`, pass `timeoutMs: 120000` (two minutes — the default; a later Profile setting can override) into the `PendingActionEntry` action object.

- [ ] **Step 6: Verify and commit**

```bash
./node_modules/.bin/vitest run src/components/agent/PendingActionEntry.test.tsx
./node_modules/.bin/tsc --noEmit -p tsconfig.json
git add src/components/agent/PendingActionEntry.tsx src/hooks/useAgentStream.ts src/components/agent/AgentChat.tsx
git commit -m "feat(ui): a permission ask shows its window and auto-denies at zero

Client-side: a browser that is gone leaves the turn paused as before; a
browser that is present stops a forgotten ask from waiting forever."
```

---

## Task 4: "Always allow this" — the owner allowlist gains a writer and a button

**Files:**
- Modify: `halbert_core/halbert_core/tools/safety.py` (add `save_user_command_override`, beside `load_user_command_overrides` at `:944`)
- Modify: `halbert_core/halbert_core/dashboard/routes/terminal.py` (owner-only `POST /allowlist`)
- Modify: `.../src/lib/api.ts` (`api.terminalAllowlist`)
- Modify: `.../src/components/agent/AgentChat.tsx` (wire `onAlwaysAllow`)
- Test: `halbert_core/tests/test_command_allowlist_writer.py` (new), `test_classifier_read_only.py`, `PendingActionEntry.test.tsx`

The store is read in one place and written nowhere (a property a Task-5-completion test in `test_classifier_read_only.py` already pins). This adds the *only* writer, owner-gated, keyed `(binary, first operand)` — the safe key shape, never a whole binary from a button.

- [ ] **Step 1: Failing test for the writer**

```python
# halbert_core/tests/test_command_allowlist_writer.py
# SPDX-License-Identifier: GPL-3.0-or-later
import json
from halbert_core.tools.safety import save_user_command_override, load_user_command_overrides


def test_it_appends_a_binary_verb_pair(tmp_path):
    p = tmp_path / "command-allowlist.json"
    save_user_command_override("systemctl", "restart", path=str(p))
    assert load_user_command_overrides(str(p)) == {"systemctl": frozenset({"restart"})}


def test_a_second_verb_joins_the_same_binary(tmp_path):
    p = tmp_path / "command-allowlist.json"
    save_user_command_override("systemctl", "restart", path=str(p))
    save_user_command_override("systemctl", "status", path=str(p))
    assert load_user_command_overrides(str(p)) == {"systemctl": frozenset({"restart", "status"})}


def test_it_never_writes_a_whole_binary_true(tmp_path):
    """A button must not be able to vouch an entire binary — only a pair."""
    p = tmp_path / "command-allowlist.json"
    save_user_command_override("systemctl", "", path=str(p))
    assert load_user_command_overrides(str(p)) == {}   # empty operand is refused
```

- [ ] **Step 2: Run, watch fail** — `arch -arm64 …/wt_pytest.py halbert_core/tests/test_command_allowlist_writer.py -v` → `ImportError: cannot import name 'save_user_command_override'`.

- [ ] **Step 3: Write the writer**

In `safety.py`, beside `load_user_command_overrides` (`:944`):

```python
def save_user_command_override(binary: str, first_operand: str,
                               path: Optional[str] = None) -> None:
    """Append one ``(binary, first_operand)`` pair to the owner allowlist.

    The only writer of ``command-allowlist.json`` (F: the store was read in
    one place and written nowhere). Keyed on the pair, never the whole
    binary: an "always allow" button retires *this* prompt, not every future
    use of the binary. A slash or ``=`` in the binary, or an empty operand,
    is refused — those are the shapes that would let the button vouch more
    than the one command a person saw.
    """
    binary = (binary or "").strip()
    first_operand = (first_operand or "").strip()
    if not binary or not first_operand or "/" in binary or "=" in binary:
        return
    if path is None:
        from ..utils.paths import config_dir
        path = os.path.join(config_dir(), "command-allowlist.json")
    try:
        with open(path) as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raw = {}
    except (OSError, ValueError):
        raw = {}
    verbs = raw.get(binary)
    verbs = list(verbs) if isinstance(verbs, list) else []
    if first_operand not in verbs:
        verbs.append(first_operand)
    raw[binary] = verbs
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(raw, f, indent=2)
    os.replace(tmp, path)   # atomic; a crash mid-write never truncates the store
```

- [ ] **Step 4: Run, watch pass.**

- [ ] **Step 5: The owner-only route (failing test first)**

Add to `test_command_allowlist_writer.py`:

```python
import asyncio
from halbert_core.dashboard.routes import terminal as term

def test_the_allowlist_route_parses_the_pair(monkeypatch, tmp_path):
    saved = {}
    monkeypatch.setattr(term, "save_user_command_override",
                        lambda b, o, **k: saved.update({"binary": b, "operand": o}))
    asyncio.run(term.add_to_allowlist(term.AllowlistRequest(command="systemctl restart nginx")))
    assert saved == {"binary": "systemctl", "operand": "restart"}
```
Run → FAIL (`add_to_allowlist` / `AllowlistRequest` missing).

- [ ] **Step 6: Write the route**

In `terminal.py`, near the other request models, and a route in the `if FASTAPI_AVAILABLE:` block. It reuses `split_shell_command` (already in `safety.py`) to take the first two tokens:

```python
class AllowlistRequest(BaseModel):
    command: str

# inside `if FASTAPI_AVAILABLE:` — every terminal route is already behind
# require_owner via the default-deny router (SEC-1); no extra dependency needed.
@router.post("/allowlist")
async def add_to_allowlist(request: AllowlistRequest):
    """Owner action: retire this prompt by vouching (binary, first operand)."""
    from ...tools.safety import save_user_command_override, split_shell_command
    tokens = split_shell_command(request.command.strip())
    if not tokens:
        raise HTTPException(400, "Unparseable command")
    binary = tokens[0]
    operand = tokens[1] if len(tokens) > 1 else ""
    save_user_command_override(binary, operand)
    return {"ok": True, "binary": binary, "operand": operand}
```
Add `from ...tools.safety import save_user_command_override` at module top so the monkeypatch in the test binds (`term.save_user_command_override`).

- [ ] **Step 7: Run backend, commit**

```bash
arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_command_allowlist_writer.py halbert_core/tests/test_route_auth_census.py -q
git add halbert_core/halbert_core/tools/safety.py halbert_core/halbert_core/dashboard/routes/terminal.py halbert_core/tests/test_command_allowlist_writer.py
git commit -m "feat(safety): an owner button can retire a prompt (binary, first operand)

The only writer of command-allowlist.json, keyed on the pair not the
binary, atomic. POST /api/terminal/allowlist is owner-gated by SEC-1's
default-deny router."
```

- [ ] **Step 8: The client call + wiring (failing test)**

Add to `PendingActionEntry.test.tsx`:

```tsx
it('offers Always allow only when the action is vouchable', () => {
  const onAlwaysAllow = vi.fn()
  const { rerender } = render(
    <PendingActionEntry action={base} onApprove={() => {}} onDeny={() => {}} onAlwaysAllow={onAlwaysAllow} />)
  expect(screen.queryByRole('button', { name: /always allow/i })).toBeNull()   // base has no alwaysAllowable
  rerender(<PendingActionEntry action={{ ...base, alwaysAllowable: true, command: 'systemctl restart nginx' }}
    onApprove={() => {}} onDeny={() => {}} onAlwaysAllow={onAlwaysAllow} />)
  screen.getByRole('button', { name: /always allow/i }).click()
  expect(onAlwaysAllow).toHaveBeenCalled()
})
```
The button-visibility logic is already in Task 1's component (`action.alwaysAllowable && onAlwaysAllow`), so this should PASS on write — it pins the contract.

- [ ] **Step 9: `api.terminalAllowlist` + AgentChat wiring**

In `lib/api.ts`, beside `executeCommand`:

```ts
terminalAllowlist(command: string) {
  return request('/api/terminal/allowlist', { method: 'POST', body: JSON.stringify({ command }) })
},
```
In `AgentChat.tsx`, pass `onAlwaysAllow` when the pending action is a vouchable `run_command` (the backend sets `alwaysAllowable`/`command` on the event — see Step 10):

```tsx
onAlwaysAllow={session.pendingConfirmation.command ? async () => {
  await api.terminalAllowlist(session.pendingConfirmation!.command!)
  confirmAction(session.pendingConfirmation!.actionId, true)   // allow once now; future asks are drained
} : undefined}
```

- [ ] **Step 10: Carry `command`/`alwaysAllowable` on the event**

The event builder (`events.py:263`) and its yield (`state_machine.py:4398`) currently pass `tool`, `description`, `risk_level`. Add `command` (the raw `args["command"]` when `tool == "run_command"`) and `always_allowable` (true when `tool == "run_command"`). In `useAgentStream.ts`, read them at the reducer (`:767`) into `ConfirmationRequest.command` / `.alwaysAllowable`. Full field-plumbing mirrors the existing `description`/`risk_level` path exactly.

- [ ] **Step 11: Verify and commit**

```bash
./node_modules/.bin/vitest run src/components/agent/PendingActionEntry.test.tsx
./node_modules/.bin/tsc --noEmit -p tsconfig.json
arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests/test_classifier_read_only.py -q   # the "no writer" pin now expects the one writer
git add -A
git commit -m "feat(ui): Always allow this — the button that drains a repeat prompt"
```

*Note for Step 11:* the `test_nothing_agent_side_writes_the_owner_allowlist` pin from the SEC-2 work will now see `save_user_command_override`. Update it to assert the writer is exactly one owner-gated route, not zero writers — the invariant is "nothing the *agent* can reach writes it", and a route behind `require_owner` is the owner, not the agent.

---

## Task 5: Route the terminal's ask (ruling B) through the same surface

**Files:**
- Modify: `.../src/hooks/useTerminalSessions.ts` (surface `SpawnNeedsConfirmation` as pending state)
- Modify: `.../src/components/agent/TerminalTile.tsx` (render `PendingActionEntry` in the tile)
- Test: `.../src/hooks/useTerminalSessions.test.ts`, `PendingActionEntry.test.tsx`

Ruling B's backend answers `428` with `{requires_confirmation, risk_level, reason, confirmation_message}`; the store already throws `SpawnNeedsConfirmation`. Today `ShellLauncher` catches it into an error string. This turns it into a `PendingActionEntry` in the tile, with Approve re-spawning `{force:true}` and "Always allow" hitting the same route as Task 4 — so the two doors share one surface, as the founder asked.

- [ ] **Step 1: Failing store test**

```ts
it('exposes a pending ask instead of only throwing', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: {
      requires_confirmation: true, risk_level: 'high',
      reason: 'not on the read-only list',
      confirmation_message: '```\nhostname evil\n```',
    } }), { status: 428 })))
  const pending = []
  const unsub = store.subscribePending?.((p) => pending.push(p))
  await store.spawn('hostname evil').catch(() => {})
  expect(pending.at(-1)).toMatchObject({ command: 'hostname evil', riskLevel: 'high' })
  unsub?.()
})
```

- [ ] **Step 2: Run, watch fail** — no `subscribePending`.

- [ ] **Step 3: Add a pending channel to the store**

`SpawnNeedsConfirmation` already carries `command` and `detail`. Add a small pending map to the store keyed by command, a `subscribePending` in the same `useSyncExternalStore` shape the sessions use, and on a 428 publish `{ command, riskLevel: detail.risk_level, description: detail.confirmation_message, alwaysAllowable: true }` before throwing. The throw stays (existing callers keep working); the pending channel is additive.

- [ ] **Step 4: Run, watch pass.**

- [ ] **Step 5: Render it in the tile (failing test)**

Add to `PendingActionEntry.test.tsx` a case that a tile-level pending action approves by re-spawn — assert the entry renders `hostname evil` and its Approve calls the provided `onApprove`. (The component is unchanged; this pins its reuse in the terminal surface.)

- [ ] **Step 6: Wire `TerminalTile`**

In `TerminalTile.tsx`, subscribe to the store's pending channel for this tile's context and, when present, render `<PendingActionEntry>` above the terminal body with:
- `onApprove` → `spawn(command, { force: true })` and clear the pending entry;
- `onDeny` → clear the pending entry (nothing ran, nothing to tell a model — the terminal has no model turn to resume);
- `onAlwaysAllow` → `api.terminalAllowlist(command)` then the approve path.

- [ ] **Step 7: Update `ShellLauncher`**

`ShellLauncher` already passes `force: true` (the click is the confirmation), so it never hits a 428 and needs no pending UI. Leave it. Confirm its test still passes.

- [ ] **Step 8: Verify and commit**

```bash
./node_modules/.bin/vitest run src/hooks/useTerminalSessions.test.ts src/components/agent/PendingActionEntry.test.tsx src/components/shell/ShellLauncher.test.tsx
./node_modules/.bin/tsc --noEmit -p tsconfig.json
git add -A
git commit -m "feat(ui): the terminal's ask uses the same inline entry as the agent's

Ruling B's 428 becomes a PendingActionEntry in the tile — Approve
re-spawns with force, Always allow hits the owner allowlist route. One
surface for both doors, as the founder asked."
```

---

## Task 6: Retire the modal; announce instead of alert

**Files:**
- Delete: `.../src/components/agent/ConfirmationDialog.tsx` (after moving `renderDescription`)
- Create: `.../src/lib/renderDescription.ts` (the escaping+markup helper, now shared)
- Modify: `PendingActionEntry.tsx` (import from the new location)
- Grep: confirm no remaining permission popup

`renderDescription` (with its security note about escaping model-supplied text before markup) currently lives in `ConfirmationDialog.tsx` and is imported by `PendingActionEntry`. Move it to its own module so deleting the modal is clean.

- [ ] **Step 1: Move `renderDescription` to `src/lib/renderDescription.ts`**

Copy `escapeHtml` + `renderDescription` (ConfirmationDialog.tsx `:27-59`) verbatim into the new file with the SPDX header and the full security comment. Export `renderDescription`.

- [ ] **Step 2: Repoint the import**

In `PendingActionEntry.tsx`, change `import { renderDescription } from './ConfirmationDialog'` to `import { renderDescription } from '../../lib/renderDescription'`.

- [ ] **Step 3: Delete the modal**

```bash
git rm src/components/agent/ConfirmationDialog.tsx
grep -rn "ConfirmationDialog" src/ | grep -v test   # expect: no results
```

- [ ] **Step 4: The blocked-on-approval announcement stays, and is enough**

`useAgentStream.ts:585` already announces `'Waiting for your approval'` assertively via `lib/announce` when the event arrives — the accessible, non-visual counterpart to the inline entry. No modal, no focus trap. Confirm it is unchanged.

- [ ] **Step 5: Assert no permission popup remains**

Add a guard test in `PendingActionEntry.test.tsx` (or a small `noModal.test.tsx`):

```tsx
it('the permission surface mounts nothing fixed or dialog-roled', () => {
  const { container } = render(
    <PendingActionEntry action={base} onApprove={() => {}} onDeny={() => {}} />)
  expect(container.querySelector('.fixed, [role="dialog"], [aria-modal="true"]')).toBeNull()
})
```

- [ ] **Step 6: Full frontend suite, typecheck, commit**

```bash
./node_modules/.bin/vitest run
./node_modules/.bin/tsc --noEmit -p tsconfig.json   # only the Onboarding baseline
git add -A
git commit -m "refactor(ui): delete the permission modal; renderDescription is shared

The inline entry is the only permission surface now. renderDescription
moves to lib/ with its escaping security note intact."
```

---

## Self-review (done while writing)

- **Spec coverage:** option 1 (render the ask) = Tasks 1 + 6; option 2 (always allow) = Task 4; option 3 (deny reason) = Task 2; option 4 (timeout) = Task 3; the founder's no-popup constraint = Tasks 1 + 6; the two-doors-one-surface ask = Task 5. Options 5–6 (the Profile) are §Plan B, gated.
- **Type consistency:** `PendingAction` (with `status`, `command?`, `alwaysAllowable?`, `timeoutMs?`) is defined once in Task 1 and extended by field in Tasks 3–4; `confirmAction(actionId, confirmed, reason?)` is the same 3-arg shape in Tasks 1 (2-arg call, reason dropped), 2 (reason added), and used in 4/5. `save_user_command_override(binary, first_operand, path=None)` is one signature across Task 4. `AllowlistRequest{command}` and `api.terminalAllowlist(command)` match.
- **No placeholders:** every code step carries the code; the one "should PASS on write" steps (2.7, 4.8) are pins on behavior a prior step built, and say so.
- **One assumption flagged for the founder, not blocking:** the terminal's ask renders *in the tile* (Task 5), matching Warp's block model, rather than in the conversation. If you would rather the terminal's ask also appear in the conversation spine, that is a one-component re-parent, not a re-architecture — say so and it moves.

---

## Plan B (sketch, blocked on founder rulings — NOT bite-sized yet)

Research options 5–6 — the permission **Profile** — cannot be written as executable tasks until the five questions in `RESEARCH-PERMISSION-MODELS-2026-09-16.md` §8 + §6a are answered, because each changes the data model:

1. **The dial's middle word** — *Ask / Judge / Allow*? "Judge" = Halbert's classifier decides (our distinguishing asset). Determines the enum's serialized names.
2. **One object or two** — is autonomy (`observe…orchestrate`) folded into the Profile or kept as its own step behind the phrase ceremony? Determines whether `being.yml` grows one section or two.
3. **Guest visibility** — may a guest *see* the owner's dial? `RoleGate` answers what a guest may *do*; this is new. Determines whether the settings card is owner-only.
4. **Options 1–4 now, or wait** — answered by this plan: now.
5. **The fork (§6a)** — raw PTY + gate the doors + watch the stream (today), or Warp's block model + gate the typed line. Only the block model lets an ask reach what a person *types* into a shell. This is a terminal-architecture decision and the largest of the five.

**When those land,** Plan B's shape (to be detailed then): a `PermissionProfile` dataclass in `config/` (Warp's per-capability three-way with Halbert's classifier as the middle position, `Unknown → Ask` fail-closed); the row list drawn from `capabilities.py` presence; `command-allowlist.json` + the `SENSITIVE_PATHS` additions as fields; a per-speaker column from `RoleGate`; one-shot speedbumps recorded in the consent ledger (SEC-6's first-run consent, per row); a settings card. It reuses this plan's `PendingActionEntry` as its ask surface — the Profile decides *whether* to ask; the entry is *how*.

---

## Execution handoff

Plan complete and saved to `.handoff/PLAN-INLINE-PERMISSION-SURFACE-2026-09-16.md`. Two execution options:

1. **Subagent-driven (recommended)** — a fresh subagent per task, two-stage review between tasks, fast iteration.
2. **Inline execution** — tasks run in this session with checkpoints for review.

Which approach — and do you want Task 4's "always allow" and Task 5's terminal unification in the first pass, or the inline entry (Tasks 1–3, 6) landed and reviewed first?
