// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Bodies — every machine this Halbert has, at once.
 *
 * The Presence Pill switches between bodies and Settings › Linked Devices
 * manages them. Neither shows them together, so "is the home body still up?"
 * had no answer short of switching to it. NodeFleetCockpit was written and
 * tested for exactly this and imported by nothing.
 *
 * The noun is **Body**. CORE-CONCEPTS-AND-ALIGNMENT §terminology lists node,
 * instance, host-as-noun and satellite under avoid, and C1-02 puts it plainly:
 * "I is the entity, bodies are 'my desk body'". A body of this entity shares
 * its memory and conversations; an independent one keeps its own.
 */

import { NodeFleetCockpit } from '@/components/fleet/NodeFleetCockpit'

export function Bodies() {
  return (
    <div className="p-4 space-y-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Bodies</h1>
        <p className="text-xs text-muted-foreground pt-0.5">
          One mind, many bodies. Health and services for every machine linked
          to this Halbert.
        </p>
      </div>
      <NodeFleetCockpit />
    </div>
  )
}

export default Bodies
