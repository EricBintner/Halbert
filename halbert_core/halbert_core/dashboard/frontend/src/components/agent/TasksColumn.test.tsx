// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TasksColumn, TaskCard, type TaskCardData } from './TasksColumn';

const runningTask: TaskCardData = {
  taskId: 't1',
  title: 'ls -la /tmp',
  threadTopic: 'checking temp files',
  state: 'running',
  elapsedSeconds: 3,
  threadId: 'thread-1',
  blockId: 'blk-1',
};

const finishedTask: TaskCardData = {
  taskId: 't2',
  title: 'echo hello',
  threadTopic: 'greeting test',
  state: 'done_unseen',
  exitCode: 0,
  threadId: 'thread-2',
  blockId: 'blk-2',
};

const errorTask: TaskCardData = {
  taskId: 't3',
  title: 'false',
  threadTopic: 'error test',
  state: 'error',
  exitCode: 1,
  threadId: 'thread-3',
};

describe('TasksColumn', () => {
  it('renders with role=complementary', () => {
    render(<TasksColumn runningTasks={[]} finishedTasks={[]} />);
    expect(screen.getByRole('complementary')).toBeTruthy();
  });

  it('renders Running header', () => {
    render(<TasksColumn runningTasks={[]} finishedTasks={[]} />);
    expect(screen.getByText('Running')).toBeTruthy();
  });

  it('shows "Nothing running" when empty', () => {
    render(<TasksColumn runningTasks={[]} finishedTasks={[]} />);
    expect(screen.getByText('Nothing running')).toBeTruthy();
  });

  it('renders running tasks', () => {
    render(<TasksColumn runningTasks={[runningTask]} finishedTasks={[]} />);
    expect(screen.getByText('ls -la /tmp')).toBeTruthy();
    expect(screen.getByText('checking temp files')).toBeTruthy();
  });

  it('renders finished count in summary', () => {
    render(<TasksColumn runningTasks={[]} finishedTasks={[finishedTask]} />);
    expect(screen.getByText(/Finished 1/)).toBeTruthy();
  });

  it('does not show finished section when empty', () => {
    render(<TasksColumn runningTasks={[]} finishedTasks={[]} />);
    expect(screen.queryByText(/Finished/)).toBeNull();
  });

  it('shows Clear button when finished tasks exist', () => {
    render(<TasksColumn runningTasks={[]} finishedTasks={[finishedTask]} onClear={() => {}} />);
    expect(screen.getByText('Clear')).toBeTruthy();
  });

  it('hides Clear button when no finished tasks', () => {
    render(<TasksColumn runningTasks={[]} finishedTasks={[]} onClear={() => {}} />);
    expect(screen.queryByText('Clear')).toBeNull();
  });

  it('Clear button calls onClear', () => {
    const onClear = vi.fn();
    render(<TasksColumn runningTasks={[]} finishedTasks={[finishedTask]} onClear={onClear} />);
    fireEvent.click(screen.getByText('Clear'));
    expect(onClear).toHaveBeenCalledOnce();
  });

  it('renders yourShell region', () => {
    render(
      <TasksColumn
        runningTasks={[]}
        finishedTasks={[]}
        yourShell={<div data-testid="shell-region">shell</div>}
      />,
    );
    expect(screen.getByTestId('shell-region')).toBeTruthy();
  });

  it('does not render shell region when not provided', () => {
    render(<TasksColumn runningTasks={[]} finishedTasks={[]} />);
    expect(screen.queryByTestId('shell-region')).toBeNull();
  });
});

describe('TaskCard', () => {
  it('renders title and thread topic', () => {
    render(<TaskCard {...runningTask} />);
    expect(screen.getByText('ls -la /tmp')).toBeTruthy();
    expect(screen.getByText('checking temp files')).toBeTruthy();
  });

  it('renders StatusLight with running state', () => {
    render(<TaskCard {...runningTask} />);
    expect(screen.getByRole('img').getAttribute('data-status-light')).toBe('running');
  });

  it('renders StatusLight with done_unseen state', () => {
    render(<TaskCard {...finishedTask} />);
    expect(screen.getByRole('img').getAttribute('data-status-light')).toBe('done_unseen');
  });

  it('renders StatusLight with error state', () => {
    render(<TaskCard {...errorTask} />);
    expect(screen.getByRole('img').getAttribute('data-status-light')).toBe('error');
  });

  it('shows stop button for running tasks', () => {
    const onStop = vi.fn();
    render(<TaskCard {...runningTask} onStop={onStop} />);
    const stopBtn = screen.getByLabelText('Stop task');
    expect(stopBtn).toBeTruthy();
    fireEvent.click(stopBtn);
    expect(onStop).toHaveBeenCalledWith('t1');
  });

  it('does not show stop button for finished tasks', () => {
    const onStop = vi.fn();
    render(<TaskCard {...finishedTask} onStop={onStop} />);
    expect(screen.queryByLabelText('Stop task')).toBeNull();
  });

  it('jumps by block id, not by thread id', () => {
    const onJump = vi.fn();
    render(<TaskCard {...runningTask} onJumpToTurn={onJump} />);
    fireEvent.click(screen.getByLabelText('Jump to turn'));
    // A thread is a conversation, not a place on screen, and the handler
    // scrolls to an element. Every surface that renders a block stamps
    // `data-terminal-block` -- the live tool card, the live tile, and the
    // same card after a reload -- so the block id resolves in all of them
    // and the thread id resolved in none.
    expect(onJump).toHaveBeenCalledWith(runningTask.blockId);
  });

  it('falls back to the thread id when a card has no block', () => {
    const onJump = vi.fn();
    const { blockId: _drop, ...noBlock } = runningTask;
    render(<TaskCard {...noBlock} onJumpToTurn={onJump} />);
    fireEvent.click(screen.getByLabelText('Jump to turn'));
    expect(onJump).toHaveBeenCalledWith(noBlock.threadId);
  });

  it('does not show jump arrow when no callback', () => {
    render(<TaskCard {...runningTask} />);
    expect(screen.queryByLabelText('Jump to turn')).toBeNull();
  });

  it('has data-task-card attribute', () => {
    render(<TaskCard {...runningTask} />);
    const card = document.querySelector('[data-task-card="t1"]');
    expect(card).toBeTruthy();
  });

  it('has data-task-state attribute', () => {
    render(<TaskCard {...runningTask} />);
    const card = document.querySelector('[data-task-state="running"]');
    expect(card).toBeTruthy();
  });

  it('shows stop button for needs_attention state', () => {
    const task: TaskCardData = { ...runningTask, state: 'needs_attention' };
    const onStop = vi.fn();
    render(<TaskCard {...task} onStop={onStop} />);
    expect(screen.getByLabelText('Stop task')).toBeTruthy();
  });

  it('does not show stop for blocked state', () => {
    const task: TaskCardData = { ...runningTask, state: 'blocked' };
    const onStop = vi.fn();
    render(<TaskCard {...task} onStop={onStop} />);
    expect(screen.queryByLabelText('Stop task')).toBeNull();
  });
});
