// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * A promoted command has somewhere to be.
 *
 * `terminal_block_promote` set `isTaskCard` on a block, and the only surface
 * that could have rendered it — TasksColumn — described itself as the
 * replacement for TerminalAccordionDock and was imported by nothing outside
 * its own test. So crossing the two-second line had no user-visible effect
 * whatsoever. This mounts it.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../agent/ProactiveEventsBadge', () => ({
  ProactiveEventsBadge: () => <div data-testid="proactive" />,
}));
vi.mock('../ModuleRenderer', () => ({ ModuleRenderer: () => <div data-testid="module" /> }));
vi.mock('./HostVitals', () => ({ HostVitals: () => <div data-testid="vitals" /> }));

import { ContextStage } from './ContextStage';
import { terminalSessionStore as store } from '../../hooks/useTerminalSessions';

function seedPromoted(command = 'npm run build', blockId = 'blk-1') {
  store.adopt('term-1', { command, pid: 10, blockId, owner: 'agent' });
  store.addBlock('term-1', {
    block_id: blockId, owner: 'agent', status: 'running', isTaskCard: true,
  });
}

describe('ContextStage — the tasks column', () => {
  beforeEach(() => store.closeAll());
  afterEach(() => store.closeAll());

  it('says nothing is running when nothing is', () => {
    render(<ContextStage />);

    // The empty state is the proof the nervous system is up. An absent column
    // reads as "the feature is not there"; "Nothing running" reads as
    // "nothing is running right now", which is a different fact.
    expect(document.querySelector('[data-tasks-column]')).toBeTruthy();
    expect(screen.getAllByText('Nothing running').length).toBeGreaterThan(0);
  });

  it('shows a promoted command as a running task', () => {
    seedPromoted();
    render(<ContextStage />);

    expect(screen.getAllByText('npm run build').length).toBeGreaterThan(0);
    expect(document.querySelector('[data-task-card="blk-1"]')).toBeTruthy();
    expect(document.querySelector('[data-task-state="running"]')).toBeTruthy();
  });

  it('does not show a command that was never promoted', () => {
    store.adopt('term-1', { command: 'ls', pid: 10, blockId: 'blk-2', owner: 'agent' });
    store.addBlock('term-1', {
      block_id: 'blk-2', owner: 'agent', status: 'running', isTaskCard: false,
    });
    render(<ContextStage />);

    expect(screen.queryByText('ls')).toBeNull();
  });

  it('jumps by block id, which every surface that renders a block stamps', () => {
    seedPromoted();
    const onJump = vi.fn();
    render(<ContextStage onJumpToTerminal={onJump} />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Jump to turn' })[0]);

    // Not the thread id: a thread is a conversation, not a place on screen.
    expect(onJump).toHaveBeenCalledWith('blk-1');
  });
});

describe('ContextStage — your shell', () => {
  beforeEach(() => store.closeAll());
  afterEach(() => { store.closeAll(); vi.restoreAllMocks(); });

  it('still offers a way to open a shell', async () => {
    // The accordion this column replaced carried the ONLY shell launcher on
    // the page. Replacing it without one would have removed the admin's
    // ability to open a terminal at all, silently, as a side effect of a
    // layout change.
    const spawn = vi.spyOn(store, 'spawn').mockResolvedValue('term-new');
    render(<ContextStage />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Open a shell' })[0]);

    expect(spawn).toHaveBeenCalledTimes(1);
    // An interactive login shell, run through /bin/sh so the child expands
    // $SHELL; the fallback keeps it working where $SHELL is not exported.
    expect(spawn.mock.calls[0][0]).toContain('SHELL:-');
  });

  it('says so when the shell could not be opened', async () => {
    vi.spyOn(store, 'spawn').mockRejectedValue(new Error('at capacity'));
    render(<ContextStage />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Open a shell' })[0]);

    // A button that does nothing is indistinguishable from a broken one.
    expect(await screen.findAllByText(/at capacity/)).not.toHaveLength(0);
  });
});
