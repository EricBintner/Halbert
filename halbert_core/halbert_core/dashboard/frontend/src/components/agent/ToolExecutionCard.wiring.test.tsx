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
import { render, screen, fireEvent } from '@testing-library/react';
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

describe('ToolExecutionCard arguments', () => {
  it('does not repeat the command as JSON for a shell block', () => {
    const { container } = render(
      <ToolExecutionCard execution={streamed} blockExitCode={0} blockDuration={0.3} />
    );
    fireEvent.click(screen.getByRole('button', { name: /smbstatus/ }));

    // The command is the header. Repeating it as {"command": "smbstatus"}
    // below adds braces, quotes and a second copy of the one fact the card
    // already leads with.
    expect(screen.queryByText('Arguments')).toBeNull();
    expect(container.textContent).not.toContain('{');
    expect(container.textContent).not.toContain('"command"');
  });

  it('shows another tool’s arguments as fields, not as a JSON dump', () => {
    const read: ToolExecution = {
      executionId: 'exec-2',
      tool: 'read_file',
      args: { path: '/etc/fstab', limit: 40 },
      status: 'success',
    };
    const { container } = render(<ToolExecutionCard execution={read} />);
    fireEvent.click(screen.getByRole('button', { name: /read_file/ }));

    // The path is the useful part and must survive; the punctuation is not.
    expect(screen.getByText('/etc/fstab')).toBeTruthy();
    expect(screen.getByText('path')).toBeTruthy();
    expect(screen.getByText('40')).toBeTruthy();
    expect(container.textContent).not.toContain('{');
    expect(container.textContent).not.toContain('": "');
  });
})

/** What useAgentStream produces once the block has closed. */
const finished: ToolExecution = {
  ...streamed,
  blockExitCode: 1,
  blockDuration: 0.34,
  blockOutputHead: 'no shares',
  blockOutputTail: 'no shares',
};

describe('ToolExecutionCard reads its block from the execution', () => {
  it('shows the one-line result with no block props at all', () => {
    render(<ToolExecutionCard execution={finished} />);

    // This is the whole fast-command behaviour, and until the execution
    // carried the block's result it was unreachable: isShortBlock is gated
    // on a duration and an output that no caller supplied.
    expect(screen.getByText(/\$ smbstatus · exit 1/)).toBeTruthy();
    expect(screen.getByText(/0\.3s/)).toBeTruthy();
  });

  it('does not repeat the raw result once the block renders its output', () => {
    render(<ToolExecutionCard execution={finished} />);
    fireEvent.click(screen.getByRole('button', { name: /smbstatus/ }));

    // suppressResult is gated on the same output; without it the card showed
    // the block output AND the tool's return string, the same text twice.
    expect(screen.queryByText('Result')).toBeNull();
    expect(screen.getByText('Block output')).toBeTruthy();
  });

  it('a slow block keeps its card rather than collapsing to a line', () => {
    render(<ToolExecutionCard execution={{ ...finished, blockDuration: 9.5 }} />);

    expect(screen.queryByText(/\$ smbstatus · exit 1/)).toBeNull();
    expect(screen.getByText(/9\.5s/)).toBeTruthy();
  });

  it('an explicit prop still wins, for the timeline’s stored blocks', () => {
    render(<ToolExecutionCard execution={finished} blockExitCode={0} blockDuration={2.2} />);

    // The StatusLight and the card label both report it, so there are two.
    expect(screen.getAllByText(/exit 0/).length).toBeGreaterThan(0);
    expect(screen.getByText(/2\.2s/)).toBeTruthy();
    // ...and the execution's own exit 1 is not what shows.
    expect(screen.queryByText(/exit 1/)).toBeNull();
  });
})

describe('ToolExecutionCard frozen output', () => {
  it('does not print a short block’s output twice with an ellipsis between', () => {
    // The pool sends head = first 20 lines and tail = the whole text when it
    // fits in 4 KiB, so for any short command head and tail are the SAME
    // string. Joining them unconditionally renders "hi\n…\nhi": the output
    // duplicated, with an elision marker claiming something was cut.
    const short: ToolExecution = {
      ...streamed,
      blockExitCode: 0,
      blockDuration: 5,
      blockOutputHead: 'two shares are up',
      blockOutputTail: 'two shares are up',
    };
    render(<ToolExecutionCard execution={short} />);
    fireEvent.click(screen.getByRole('button', { name: /smbstatus/ }));

    const pre = screen.getByText(/two shares are up/);
    expect(pre.textContent).toBe('two shares are up');
    expect(pre.textContent).not.toContain('…');
  });

  it('marks the elision when output really was cut', () => {
    const long: ToolExecution = {
      ...streamed,
      blockExitCode: 0,
      blockDuration: 5,
      blockOutputHead: 'first twenty lines',
      blockOutputTail: 'last four kilobytes',
    };
    render(<ToolExecutionCard execution={long} />);
    fireEvent.click(screen.getByRole('button', { name: /smbstatus/ }));

    // A reader must be able to tell "this is all of it" from "there is more".
    const pre = screen.getByText(/first twenty lines/);
    expect(pre.textContent).toContain('…');
    expect(pre.textContent).toContain('last four kilobytes');
  });
})

describe('ToolExecutionCard elision', () => {
  it('says how many lines are missing from the middle', () => {
    // A bare "…" says something was cut without saying how much, and a
    // reader cannot tell "this is all of it" from "there is more".
    render(<ToolExecutionCard execution={{
      ...streamed, blockExitCode: 0, blockDuration: 9,
      blockOutputHead: 'first twenty lines',
      blockOutputTail: 'last four kilobytes',
      blockElidedLines: 4812,
    }} />)
    fireEvent.click(screen.getByRole('button', { name: /smbstatus/ }))

    expect(screen.getByText(/4,812 lines elided/)).toBeTruthy()
  })

  it('says nothing when nothing was cut', () => {
    render(<ToolExecutionCard execution={{
      ...streamed, blockExitCode: 0, blockDuration: 9,
      blockOutputHead: 'head', blockOutputTail: 'tail',
      blockElidedLines: 0,
    }} />)
    fireEvent.click(screen.getByRole('button', { name: /smbstatus/ }))

    const pre = screen.getByText(/head/)
    expect(pre.textContent).not.toMatch(/elided/)
    // Head and tail still differ, so they are still both shown.
    expect(pre.textContent).toContain('tail')
  })

  it('falls back to a bare marker when the count is unknown', () => {
    // A stored block from before the count existed. Better an unlabelled
    // elision than a confident "0 lines elided" that is not known to be true.
    render(<ToolExecutionCard execution={{
      ...streamed, blockExitCode: 0, blockDuration: 9,
      blockOutputHead: 'head', blockOutputTail: 'tail',
    }} />)
    fireEvent.click(screen.getByRole('button', { name: /smbstatus/ }))

    const pre = screen.getByText(/head/)
    expect(pre.textContent).toContain('…')
    expect(pre.textContent).not.toMatch(/elided/)
  })
})
