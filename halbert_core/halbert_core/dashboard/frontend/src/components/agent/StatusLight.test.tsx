// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusLight, type StatusLightState } from './StatusLight';

describe('StatusLight', () => {
  const states: StatusLightState[] = [
    'running',
    'needs_attention',
    'done_unseen',
    'error',
    'blocked',
  ];

  it.each(states)('renders state %s with an svg and data attribute', (state) => {
    render(<StatusLight state={state} />);
    const el = screen.getByRole('img');
    expect(el).toHaveAttribute('data-status-light', state);
    expect(el.querySelector('svg')).toBeTruthy();
  });

  it('running shows elapsed timer text', () => {
    render(<StatusLight state="running" elapsedSeconds={3} />);
    expect(screen.getByText('3s')).toBeTruthy();
  });

  it('running with no elapsed shows no text', () => {
    render(<StatusLight state="running" />);
    const el = screen.getByRole('img');
    expect(el.textContent?.trim()).toBe('');
  });

  it('running formats minutes', () => {
    render(<StatusLight state="running" elapsedSeconds={125} />);
    expect(screen.getByText('2m05s')).toBeTruthy();
  });

  it('needs_attention shows "needs input"', () => {
    render(<StatusLight state="needs_attention" />);
    expect(screen.getByText('needs input')).toBeTruthy();
  });

  it('done_unseen shows exit code', () => {
    render(<StatusLight state="done_unseen" exitCode={0} />);
    expect(screen.getByText('exit 0')).toBeTruthy();
  });

  it('done_unseen defaults to exit 0', () => {
    render(<StatusLight state="done_unseen" />);
    expect(screen.getByText('exit 0')).toBeTruthy();
  });

  it('error shows exit code', () => {
    render(<StatusLight state="error" exitCode={1} />);
    expect(screen.getByText('exit 1')).toBeTruthy();
  });

  it('error defaults to exit 1', () => {
    render(<StatusLight state="error" />);
    expect(screen.getByText('exit 1')).toBeTruthy();
  });

  it('blocked shows "awaiting approval"', () => {
    render(<StatusLight state="blocked" />);
    expect(screen.getByText('awaiting approval')).toBeTruthy();
  });

  it('label overrides default text', () => {
    render(<StatusLight state="running" label="custom label" />);
    expect(screen.getByText('custom label')).toBeTruthy();
  });

  it('uses text-status-nominal for running', () => {
    render(<StatusLight state="running" />);
    expect(screen.getByRole('img').className).toContain('text-status-nominal');
  });

  it('uses text-status-warning for needs_attention', () => {
    render(<StatusLight state="needs_attention" />);
    expect(screen.getByRole('img').className).toContain('text-status-warning');
  });

  it('uses text-status-critical for error', () => {
    render(<StatusLight state="error" exitCode={1} />);
    expect(screen.getByRole('img').className).toContain('text-status-critical');
  });

  it('uses text-accent-strong for blocked', () => {
    render(<StatusLight state="blocked" />);
    expect(screen.getByRole('img').className).toContain('text-accent-strong');
  });

  it('uses text-status-nominal for done_unseen', () => {
    render(<StatusLight state="done_unseen" exitCode={0} />);
    expect(screen.getByRole('img').className).toContain('text-status-nominal');
  });

  it('has a transition style for state changes', () => {
    render(<StatusLight state="running" />);
    const el = screen.getByRole('img');
    expect(el.style.transition).toContain('var(--duration-shutter)');
  });

  it('renders size sm as 10px svg', () => {
    render(<StatusLight state="done_unseen" exitCode={0} size="sm" />);
    const svg = screen.getByRole('img').querySelector('svg')!;
    expect(svg.getAttribute('width')).toBe('10');
  });

  it('renders size md as 14px svg', () => {
    render(<StatusLight state="done_unseen" exitCode={0} size="md" />);
    const svg = screen.getByRole('img').querySelector('svg')!;
    expect(svg.getAttribute('width')).toBe('14');
  });

  it('filled states have a filled circle', () => {
    const filled: StatusLightState[] = ['done_unseen', 'error', 'blocked'];
    for (const state of filled) {
      const { container, unmount } = render(<StatusLight state={state} exitCode={0} />);
      const circles = container.querySelectorAll('circle');
      expect(circles.length).toBeGreaterThanOrEqual(1);
      const filledCircle = Array.from(circles).find((c) => c.getAttribute('fill') === 'currentColor');
      expect(filledCircle).toBeTruthy();
      unmount();
    }
  });

  it('outline states have an outline circle', () => {
    const outline: StatusLightState[] = ['running', 'needs_attention'];
    for (const state of outline) {
      const { container, unmount } = render(<StatusLight state={state} />);
      const circles = container.querySelectorAll('circle');
      const outlineCircle = Array.from(circles).find(
        (c) => c.getAttribute('fill') === 'none' && c.getAttribute('stroke') === 'currentColor',
      );
      expect(outlineCircle).toBeTruthy();
      unmount();
    }
  });

  it('running has no glyph', () => {
    const { container } = render(<StatusLight state="running" elapsedSeconds={1} />);
    // Only the outline circle, no path/rect inside
    const glyphs = container.querySelectorAll('path, rect');
    expect(glyphs.length).toBe(0);
  });

  it('needs_attention has a glyph (rect bars)', () => {
    const { container } = render(<StatusLight state="needs_attention" />);
    const rects = container.querySelectorAll('rect');
    expect(rects.length).toBeGreaterThanOrEqual(1);
  });

  it('done_unseen has a checkmark path', () => {
    const { container } = render(<StatusLight state="done_unseen" exitCode={0} />);
    const paths = container.querySelectorAll('path');
    expect(paths.length).toBe(1);
  });

  it('error has an X path', () => {
    const { container } = render(<StatusLight state="error" exitCode={1} />);
    const paths = container.querySelectorAll('path');
    expect(paths.length).toBe(1);
  });

  it('blocked has pause bars', () => {
    const { container } = render(<StatusLight state="blocked" />);
    const rects = container.querySelectorAll('rect');
    expect(rects.length).toBe(2);
  });

  it('aria-label reflects the text or state', () => {
    render(<StatusLight state="error" exitCode={2} />);
    expect(screen.getByRole('img').getAttribute('aria-label')).toBe('exit 2');
  });

  it('aria-label falls back to state when no text', () => {
    render(<StatusLight state="running" />);
    expect(screen.getByRole('img').getAttribute('aria-label')).toBe('running');
  });
});
