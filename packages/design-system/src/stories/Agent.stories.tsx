// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { Meta, StoryObj } from '@storybook/react'

import { WhyChip, type ProvenanceRef } from '../primitives/WhyChip'
import { StatusLight, type StatusLightState } from '../primitives/StatusLight'
import { EmptyState } from '../primitives/EmptyState'
import { ModuleLoadError } from '../primitives/ModuleLoadError'
import { Collapsible, CollapsibleGroup } from '../primitives/Collapsible'
import { ThinkingPanel } from '../surfaces/ThinkingPanel'
import { DiffBlock, DiffSummary } from '../surfaces/DiffBlock'
import { Button } from '../primitives/Button'

/* ================================================================ WhyChip */

const whyChipMeta: Meta<typeof WhyChip> = {
  title: 'Agent/WhyChip',
  component: WhyChip,
}
export default whyChipMeta

const SAMPLE_REFS: ProvenanceRef[] = [
  { type: 'path_lines', ref: 'src/lib/engine.ts:42-67', label: 'Engine initialization' },
  { type: 'log_cursor', ref: 'log:run-12:34', label: 'Build log at 14:02' },
  { type: 'metric_window', ref: 'cpu:2m', label: 'CPU over 2 min window' },
  { type: 'snapshot_id', ref: 'snap:abc123', label: 'Config snapshot abc123' },
  { type: 'memory_id', ref: 'mem:user-prefs', label: 'User preferences (memory)' },
]

export const Default: StoryObj<typeof WhyChip> = {
  args: {
    provenance: SAMPLE_REFS,
    onExpand: (ref) => console.log('expand', ref),
  },
}

export const SingleRef: StoryObj<typeof WhyChip> = {
  args: {
    provenance: [SAMPLE_REFS[0]],
  },
}

export const WithUrl: StoryObj<typeof WhyChip> = {
  args: {
    provenance: [
      { ...SAMPLE_REFS[0], url: 'https://example.com' },
      SAMPLE_REFS[1],
    ],
  },
}

/* ============================================================ StatusLight */

export const StatusLightStates: StoryObj = {
  name: 'StatusLight / States',
  render: () => {
    const states: StatusLightState[] = ['running', 'needs_attention', 'done_unseen', 'error', 'blocked']
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        {states.map((s) => (
          <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
            <StatusLight state={s} elapsedSeconds={42} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-secondary)' }}>{s}</span>
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
          <StatusLight state="running" size="md" elapsedSeconds={127} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-secondary)' }}>running (md)</span>
        </div>
      </div>
    )
  },
}

/* ============================================================ EmptyState */

export const EmptyStateDefault: StoryObj = {
  name: 'EmptyState / Default',
  render: () => (
    <EmptyState
      title="No Backups Discovered"
      description="Click Scan to discover backup configurations on connected drives."
      action={<Button variant="primary" size="sm">Scan Now</Button>}
    />
  ),
}

export const EmptyStateMinimal: StoryObj = {
  name: 'EmptyState / Minimal',
  render: () => <EmptyState title="No results" />,
}

/* ======================================================= ModuleLoadError */

export const ModuleLoadErrorDefault: StoryObj = {
  name: 'ModuleLoadError / Default',
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', maxWidth: 400 }}>
      <ModuleLoadError module="config diff" status={500} message="Internal server error" />
      <ModuleLoadError module="secret viewer" status={403} />
      <ModuleLoadError module="log tail" />
    </div>
  ),
}

/* =========================================================== Collapsible */

export const CollapsibleDefault: StoryObj = {
  name: 'Collapsible / Group',
  render: () => (
    <CollapsibleGroup>
      <Collapsible title="System Information" summary="macOS 15.2 • 64 GB • M4 Max">
        <p style={{ margin: 0, color: 'var(--color-ink-secondary)', fontSize: 13 }}>
          macOS 15.2, Apple M4 Max, 64 GB unified memory, 4 TB SSD.
        </p>
      </Collapsible>
      <Collapsible title="Network Configuration" defaultOpen>
        <p style={{ margin: 0, color: 'var(--color-ink-secondary)', fontSize: 13 }}>
          en0: 192.168.1.42/24 • en1: disconnected
        </p>
      </Collapsible>
      <Collapsible title="GPU Details" summary="2× GPUs detected" actions={<Button size="sm" variant="ghost">Refresh</Button>}>
        <p style={{ margin: 0, color: 'var(--color-ink-secondary)', fontSize: 13 }}>
          Apple M4 Max (built-in) + AMD Radeon (eGPU)
        </p>
      </Collapsible>
    </CollapsibleGroup>
  ),
}

/* ========================================================= ThinkingPanel */

const THINKING_TEXT = `## Analysis
Looking at the error trace, the failure occurs in the database migration step.
The migration is trying to add a column that already exists.

## Plan
1. Check the migration history table
2. Compare with the current schema
3. Generate a corrective migration

## Conclusion
The fix is to add an IF NOT EXISTS guard to the ALTER TABLE statement.`

export const ThinkingPanelDefault: StoryObj = {
  name: 'ThinkingPanel / Sections',
  render: () => <ThinkingPanel thinking={THINKING_TEXT} />,
}

export const ThinkingPanelStreaming: StoryObj = {
  name: 'ThinkingPanel / Streaming',
  render: () => <ThinkingPanel thinking="Analyzing the codebase structure..." isStreaming />,
}

/* ============================================================= DiffBlock */

export const DiffBlockPending: StoryObj = {
  name: 'DiffBlock / Pending',
  render: () => (
    <DiffBlock
      filePath="src/lib/engine.ts"
      oldContent={`function init() {\n  console.log('starting');\n  loadConfig();\n}`}
      newContent={`function init() {\n  console.log('starting engine v2');\n  loadConfig();\n  validateConfig();\n}`}
      additions={2}
      deletions={1}
      onApply={() => console.log('apply')}
      onReject={() => console.log('reject')}
    />
  ),
}

export const DiffBlockApplied: StoryObj = {
  name: 'DiffBlock / Applied',
  render: () => (
    <DiffBlock
      filePath="package.json"
      newContent={`{\n  "name": "halbert",\n  "version": "2.1.0"\n}`}
      additions={3}
      deletions={0}
      status="applied"
      onApply={() => {}}
      onReject={() => {}}
    />
  ),
}

export const DiffSummaryBar: StoryObj = {
  name: 'DiffBlock / Summary',
  render: () => (
    <DiffSummary
      diffs={[
        { filePath: 'src/lib/engine.ts', additions: 12, deletions: 3 },
        { filePath: 'src/config.ts', additions: 4, deletions: 1 },
        { filePath: 'tests/engine.test.ts', additions: 28, deletions: 0 },
      ]}
      onApplyAll={() => console.log('apply all')}
      onRejectAll={() => console.log('reject all')}
    />
  ),
}
