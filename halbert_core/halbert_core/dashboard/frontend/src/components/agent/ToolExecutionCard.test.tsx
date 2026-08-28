// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Tests for ToolExecutionCard block rendering (Plan B: B18).
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolExecutionCard } from './ToolExecutionCard';
import type { ToolExecution } from '../../hooks/useAgentStream';

const baseExecution: ToolExecution = {
  executionId: 'exec-1',
  tool: 'run_command',
  status: 'success',
  args: { command: 'echo hello' },
  result: 'hello',
};

describe('ToolExecutionCard block rendering (Plan B)', () => {
  it('renders StatusLight in header', () => {
    render(<ToolExecutionCard execution={baseExecution} />);
    // StatusLight renders an SVG
    expect(document.querySelector('svg')).toBeTruthy();
  });

  it('shows measurement labels (exit 0) not "Success"', () => {
    render(
      <ToolExecutionCard
        execution={baseExecution}
        blockId="blk-1"
        blockExitCode={0}
        blockDuration={0.3}
      />
    );
    // StatusLight renders "exit 0" and the card label also shows it
    expect(screen.getAllByText(/exit 0/).length).toBeGreaterThan(0);
  });

  it('shows exit code and duration for completed block', () => {
    render(
      <ToolExecutionCard
        execution={baseExecution}
        blockId="blk-1"
        blockExitCode={1}
        blockDuration={2.5}
      />
    );
    expect(screen.getAllByText(/exit 1/).length).toBeGreaterThan(0);
    expect(screen.getByText(/2\.5s/)).toBeTruthy();
  });

  it('renders short block one-line result when not expanded', () => {
    render(
      <ToolExecutionCard
        execution={baseExecution}
        blockId="blk-1"
        blockOutput="hello\n"
        blockExitCode={0}
        blockDuration={0.3}
      />
    );
    expect(screen.getByText(/\$ echo hello/)).toBeTruthy();
  });

  it('does not render short block one-liner when duration > 2s', () => {
    render(
      <ToolExecutionCard
        execution={baseExecution}
        blockId="blk-1"
        blockOutput="long output\n"
        blockExitCode={0}
        blockDuration={3.0}
      />
    );
    // The one-liner should not be present
    expect(screen.queryByText(/\$ echo hello · exit/)).toBeNull();
  });

  it('suppresses raw result when block output is provided', () => {
    render(
      <ToolExecutionCard
        execution={baseExecution}
        blockId="blk-1"
        blockOutput="hello\n"
        blockExitCode={0}
      />
    );
    // Expand the card
    fireEvent.click(screen.getByText('\u25BC'));
    // "Block output" section should be present
    expect(screen.getByText('Block output')).toBeTruthy();
    // "Result" section should NOT be present (suppressed)
    expect(screen.queryByText('Result')).toBeNull();
  });

  it('shows raw result when no block output', () => {
    render(<ToolExecutionCard execution={baseExecution} />);
    fireEvent.click(screen.getByText('\u25BC'));
    expect(screen.getByText('Result')).toBeTruthy();
  });

  it('has data-terminal-block attribute when blockId provided', () => {
    const { container } = render(
      <ToolExecutionCard
        execution={baseExecution}
        blockId="blk-test"
      />
    );
    expect(container.querySelector('[data-terminal-block="blk-test"]')).toBeTruthy();
  });

  it('shows block output in expanded view', () => {
    render(
      <ToolExecutionCard
        execution={baseExecution}
        blockId="blk-1"
        blockOutput="line1\nline2\n"
        blockExitCode={0}
      />
    );
    fireEvent.click(screen.getByText('\u25BC'));
    expect(screen.getByText(/line1/)).toBeTruthy();
  });

  it('error status maps to error StatusLight state', () => {
    const errorExec: ToolExecution = {
      ...baseExecution,
      status: 'error',
      error: 'command failed',
    };
    render(
      <ToolExecutionCard
        execution={errorExec}
        blockId="blk-1"
        blockExitCode={1}
      />
    );
    expect(screen.getAllByText(/exit 1/).length).toBeGreaterThan(0);
  });

  it('running status shows running state', () => {
    const runningExec: ToolExecution = {
      ...baseExecution,
      status: 'running',
    };
    render(
      <ToolExecutionCard
        execution={runningExec}
        blockId="blk-1"
      />
    );
    // StatusLight SVG should be present
    expect(document.querySelector('svg')).toBeTruthy();
  });
});
