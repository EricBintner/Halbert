# Fable Handoff — Sovereign Host v2.0

**Created:** 2026-08-25
**Model tier:** fable (trivial, mechanical, no design decisions)
**Reads with:**
- [STRATEGY-V2-SCRUTINY.md](../documentation/sovereign-host-vision/STRATEGY-V2-SCRUTINY.md) — factual audit and corrected task list
- [IMPLEMENTATION-STRATEGY-2026-08-25.md](../documentation/sovereign-host-vision/IMPLEMENTATION-STRATEGY-2026-08-25.md) — v2.0 strategy

---

## What You're Doing

You have **3 tasks**. One can start immediately. Two are blocked until the opus track finishes prerequisites.

You are the **fast track**. Your work is mechanical — no design decisions, no architecture choices. Follow the instructions exactly.

---

## Task A0a: Install pytest-asyncio and activate skipped tests

**Status:** START NOW
**Effort:** med (10 minutes)
**Lines:** 0 (dependency install only)

### Why

The test suite has 413 tests. 395 pass, 18 are **skipped** because `pytest-asyncio` is not installed. These 18 tests cover the agent state machine and Phase D integration — exactly the code the opus track is about to change. We need them active before any changes land.

### Instructions

1. Install the package:
```bash
cd /Volumes/4TB-BAD/Halbert
pip install pytest-asyncio
```

2. Add it to the project's requirements/pyproject if one exists:
```bash
# Check what dependency file is used
ls pyproject.toml requirements*.txt setup.py setup.cfg 2>/dev/null
```
Add `pytest-asyncio` to whichever dev/test dependencies file exists.

3. Configure pytest-asynco mode. Check if `pytest.ini`, `pyproject.toml`, or `setup.cfg` has a `[tool.pytest.ini_options]` section. Add:
```ini
asyncio_mode = auto
```
This auto-detects `async def test_*` functions without requiring `@pytest.mark.asyncio` on each one.

4. Run the full test suite and verify the 18 skipped tests now run:
```bash
cd /Volumes/4TB-BAD/Halbert
python3 -m pytest halbert_core/tests/ -q --timeout=30 2>&1 | tail -5
```

**Expected result:** `413 passed, 0 skipped` (or close — a few may skip for other reasons like missing `haloysius`). The key metric: **0 skipped due to missing pytest-asyncio**.

5. If any of the newly-activated tests **fail**, do NOT fix them. Report the failures in a comment. The opus track needs to know what's broken before they change things.

### What not to touch

- Do not modify any source files in `halbert_core/`
- Do not modify any test files
- Do not change `pytest.ini` settings other than adding `asyncio_mode`

### When done

Commit with: `test: activate pytest-asyncio for 18 previously-skipped async tests`

---

## Task E1d: useIntersectionDock hook

**Status:** BLOCKED — wait for B1 (PTY backend) + C1 (Somatic Blocks) + E1a (useTerminalSessions) + E1b (TerminalTile) to be complete
**Effort:** med (~60 lines)
**Lines:** ~60

### Why

The frontend needs to know when a terminal tile scrolls out of view so it can "dock" it into the right-column accordion. This is a thin wrapper around the browser's `IntersectionObserver` API.

### Prerequisites (all must be done before you start)

- [ ] B1 complete (real PTY backend exists)
- [ ] C1 complete (Somatic Blocks exist, SSE events emit)
- [ ] E1a complete (`useTerminalSessions` hook exists)
- [ ] E1b complete (`TerminalTile` component exists)

Check status:
```bash
cd /Volumes/4TB-BAD/Halbert
test -f halbert_core/halbert_core/dashboard/frontend/src/hooks/useTerminalSessions.ts && echo "E1a done" || echo "E1a NOT done"
test -f halbert_core/halbert_core/dashboard/frontend/src/components/agent/TerminalTile.tsx && echo "E1b done" || echo "E1b NOT done"
```

### Instructions

Create `halbert_core/halbert_core/dashboard/frontend/src/hooks/useIntersectionDock.ts`:

```typescript
import { useRef, useEffect, useState, useCallback } from 'react';

interface UseIntersectionDockOptions {
  /** Visibility threshold below which docking triggers (0-1). Default 0.25. */
  threshold?: number;
  /** Called when element docks (visibility drops below threshold). */
  onDock?: () => void;
  /** Called when element undocks (visibility rises above threshold). */
  onUndock?: () => void;
}

interface UseIntersectionDockResult {
  ref: React.RefObject<HTMLElement>;
  isDocked: boolean;
  visibility: number;
}

/**
 * Watches an element's visibility via IntersectionObserver.
 * At <25% visibility, triggers docking. At >25% (scroll back), triggers undocking.
 */
export function useIntersectionDock(
  options: UseIntersectionDockOptions = {}
): UseIntersectionDockResult {
  const { threshold = 0.25, onDock, onUndock } = options;
  const ref = useRef<HTMLElement>(null);
  const [isDocked, setIsDocked] = useState(false);
  const [visibility, setVisibility] = useState(1);
  const onDockRef = useRef(onDock);
  const onUndockRef = useRef(onUndock);

  // Keep callbacks in refs to avoid re-creating the observer
  useEffect(() => {
    onDockRef.current = onDock;
    onUndockRef.current = onUndock;
  });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        const ratio = entry.intersectionRatio;
        setVisibility(ratio);

        if (ratio < threshold && !isDocked) {
          setIsDocked(true);
          onDockRef.current?.();
        } else if (ratio >= threshold && isDocked) {
          setIsDocked(false);
          onUndockRef.current?.();
        }
      },
      { threshold: [0, threshold, 0.5, 1.0] }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold, isDocked]);

  return { ref, isDocked, visibility };
}
```

### What not to touch

- Do not modify `TerminalTile.tsx` — the opus/sonnet track will wire this hook into it
- Do not modify `SidePanel.tsx`
- Do not add any styling or animation

### When done

Commit with: `feat(ui): add useIntersectionDock hook for terminal tile docking`

---

## Task E1e: TetherChip component

**Status:** BLOCKED — wait for E1d (useIntersectionDock) to be complete
**Effort:** med (~40 lines)
**Lines:** ~40

### Why

When a terminal tile is docked into the right column, a small inline chip appears in the conversation stream where the tile used to be. It says `[Terminal #1: zfs scrub → DOCKED]`. Hover highlights the docked card. Click scrolls back to the original position.

### Prerequisites

- [ ] E1d complete (useIntersectionDock hook exists)

Check status:
```bash
test -f halbert_core/halbert_core/dashboard/frontend/src/hooks/useIntersectionDock.ts && echo "E1d done" || echo "E1d NOT done"
```

### Instructions

Create `halbert_core/halbert_core/dashboard/frontend/src/components/agent/TetherChip.tsx`:

```typescript
interface TetherChipProps {
  sessionId: string;
  label: string;        // e.g. "zfs scrub"
  docked: boolean;
  onClick?: () => void;  // scroll back to original position
  onHover?: () => void;  // highlight docked card
}
```

Render a small inline pill/chip. Use existing CSS classes from the project — do not create new stylesheets. Look at how `StateBadge.tsx` or `ConfidenceIndicator.tsx` do their styling and follow the same pattern.

### What not to touch

- Do not modify `TerminalTile.tsx`
- Do not modify `TerminalAccordionDock.tsx`
- Do not add GSAP or any animation library

### When done

Commit with: `feat(ui): add TetherChip component for docked terminal tethers`

---

## Summary

| Task | Status | Effort | Lines | Can start |
|---|---|---|---|---|
| A0a | START NOW | med | 0 | Immediately |
| E1d | BLOCKED | med | ~60 | After B1 + C1 + E1a + E1b |
| E1e | BLOCKED | med | ~40 | After E1d |

**Your total work: ~100 lines + 1 dependency install.**

Do A0a now. Then wait for the opus track to signal that E1d/E1e prerequisites are met. Check the checkboxes above by running the `test -f` commands.
