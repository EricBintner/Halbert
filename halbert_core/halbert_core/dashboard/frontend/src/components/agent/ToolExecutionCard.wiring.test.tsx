// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The card finds its block without being handed one.
 *
 * ToolExecutionCard.test.tsx passes `blockId="blk-1"` as a literal in every
 * block test, so the whole Plan B surface was green in CI while no caller in
 * the application passed the prop and every branch was unreachable. These
 * tests use the shape the app actually produces -- a ToolExecution the
 * stream has stamped with its block -- so they fail if the wiring goes away.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ToolExecutionCard } from './ToolExecutionCard';
import type { ToolExecution } from '../../hooks/useAgentStream';

/** What useAgentStream produces once a block event names this tool call. */
const streamed: ToolExecution = {
  executionId: 'exec-1',
  tool: 'run_command',
  args: { command: 'smbstatus' },
  status: 'success',
  result: 'two shares',
  blockId: 'blk-1',
  terminalSessionId: 'term-1',
};

describe('ToolExecutionCard wiring', () => {
  it('renders the command, not the internal tool name, from a streamed execution', () => {
    render(<ToolExecutionCard execution={streamed} blockExitCode={0} blockDuration={0.3} />);

    expect(screen.getByText('smbstatus')).toBeTruthy();
    expect(screen.queryByText('run_command')).toBeNull();
  });

  it('shows the one-line result for a fast block with no blockId prop', () => {
    render(
      <ToolExecutionCard
        execution={streamed}
        blockOutput="two shares"
        blockExitCode={0}
        blockDuration={0.3}
      />
    );

    // The duration only ever renders on the block branch -- `exit 0` alone
    // would also come from STATUS_CONFIG's label, so asserting on it could
    // not tell a wired card from an unwired one.
    expect(screen.getByText(/0\.3s/)).toBeTruthy();
    // ...and the one-line result the short block collapses to.
    expect(screen.getByText(/\$ smbstatus · exit 0/)).toBeTruthy();
  });

  it('leaves a non-command tool alone', () => {
    const read: ToolExecution = {
      executionId: 'exec-2',
      tool: 'read_file',
      args: { path: '/etc/fstab' },
      status: 'success',
      result: 'contents',
    };
    render(<ToolExecutionCard execution={read} />);

    expect(screen.getByText('read_file')).toBeTruthy();
  });
});
