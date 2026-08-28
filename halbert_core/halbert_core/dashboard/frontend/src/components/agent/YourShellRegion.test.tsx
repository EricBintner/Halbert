// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Tests for YourShellRegion (Plan B: B16).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { YourShellRegion, type YourShellSession } from './YourShellRegion';

describe('YourShellRegion', () => {
  it('renders nothing state when session is null', () => {
    render(<YourShellRegion session={null} />);
    expect(screen.getByText('No shell session')).toBeTruthy();
  });

  it('renders shell with watched toggle', () => {
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} />);
    expect(screen.getByText('Your shell')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Unwatch shell' })).toBeTruthy();
  });

  it('shows unwatched toggle when not watched', () => {
    const session: YourShellSession = {
      sessionId: 's1',
      watched: false,
      hooked: true,
    };
    render(<YourShellRegion session={session} />);
    expect(screen.getByRole('button', { name: 'Watch shell' })).toBeTruthy();
  });

  it('calls onToggleWatched when toggle clicked', () => {
    const onToggle = vi.fn();
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} onToggleWatched={onToggle} />);
    fireEvent.click(screen.getByRole('button', { name: 'Unwatch shell' }));
    expect(onToggle).toHaveBeenCalledWith('s1', false);
  });

  it('shows unhooked badge when not hooked', () => {
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: false,
    };
    render(<YourShellRegion session={session} />);
    expect(screen.getByText(/Shell unhooked/)).toBeTruthy();
    expect(screen.getByText(/no OSC 133/)).toBeTruthy();
  });

  it('shows unhooked badge when not watched', () => {
    const session: YourShellSession = {
      sessionId: 's1',
      watched: false,
      hooked: true,
    };
    render(<YourShellRegion session={session} />);
    expect(screen.getByText(/Shell unhooked/)).toBeTruthy();
  });

  it('does not show unhooked badge when hooked and watched', () => {
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} />);
    expect(screen.queryByText(/Shell unhooked/)).toBeNull();
  });

  it('renders stage input', () => {
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} />);
    expect(screen.getByPlaceholderText('Stage a command...')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Stage command' })).toBeTruthy();
  });

  it('calls onStageCommand when stage button clicked', () => {
    const onStage = vi.fn();
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} onStageCommand={onStage} />);
    const input = screen.getByPlaceholderText('Stage a command...') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'echo hello' } });
    fireEvent.click(screen.getByRole('button', { name: 'Stage command' }));
    expect(onStage).toHaveBeenCalledWith('s1', 'echo hello');
  });

  it('calls onStageCommand on Enter key', () => {
    const onStage = vi.fn();
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} onStageCommand={onStage} />);
    const input = screen.getByPlaceholderText('Stage a command...');
    fireEvent.change(input, { target: { value: 'ls -la' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onStage).toHaveBeenCalledWith('s1', 'ls -la');
  });

  it('disables stage button when input is empty', () => {
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} />);
    const button = screen.getByRole('button', { name: 'Stage command' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('clears input after staging', () => {
    const onStage = vi.fn();
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} onStageCommand={onStage} />);
    const input = screen.getByPlaceholderText('Stage a command...') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'echo test' } });
    fireEvent.click(screen.getByRole('button', { name: 'Stage command' }));
    expect(input.value).toBe('');
  });

  it('renders terminal mount point with session id', () => {
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} />);
    const terminal = document.querySelector('[data-shell-terminal="s1"]');
    expect(terminal).toBeTruthy();
  });

  it('has data-your-shell attribute', () => {
    const session: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    render(<YourShellRegion session={session} />);
    expect(document.querySelector('[data-your-shell]')).toBeTruthy();
  });

  it('has data-shell-state attribute', () => {
    const hookedSession: YourShellSession = {
      sessionId: 's1',
      watched: true,
      hooked: true,
    };
    const { rerender } = render(<YourShellRegion session={hookedSession} />);
    expect(document.querySelector('[data-your-shell]')?.getAttribute('data-shell-state')).toBe('hooked');

    const unhookedSession: YourShellSession = {
      sessionId: 's1',
      watched: false,
      hooked: true,
    };
    rerender(<YourShellRegion session={unhookedSession} />);
    expect(document.querySelector('[data-your-shell]')?.getAttribute('data-shell-state')).toBe('unhooked');
  });
});
