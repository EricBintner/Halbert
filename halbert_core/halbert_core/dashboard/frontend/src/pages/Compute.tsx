// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Compute — shared compute view for all linked nodes.
 *
 * Shows a health grid of every machine linked to this Halbert: CPU, RAM,
 * temperature, uptime, and active services. The "Pair" button links a new
 * machine. This is the shared section's compute surface — the same data
 * regardless of which node is active, because the fleet is a property of
 * the network, not any single machine.
 *
 * The rail's EntityNodeBlock handles node switching; this page is for
 * monitoring and pairing.
 */

import { NodeFleetCockpit } from '@/components/fleet/NodeFleetCockpit'

export function Compute() {
  return (
    <div className="p-4 space-y-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Shared Compute</h1>
        <p className="text-xs text-muted-foreground pt-0.5">
          Health and services for every machine linked to this Halbert.
        </p>
      </div>
      <NodeFleetCockpit />
    </div>
  )
}

export default Compute
