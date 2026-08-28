// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Tests for ContextStage responsive layout (Plan B: B19).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// Mock the child components to avoid pulling in xterm etc.
vi.mock('../agent/TerminalAccordionDock', () => ({
  TerminalAccordionDock: () => <div data-testid="dock" />,
}));
vi.mock('../agent/ProactiveEventsBadge', () => ({
  ProactiveEventsBadge: () => <div data-testid="proactive" />,
}));
vi.mock('../ModuleRenderer', () => ({
  ModuleRenderer: () => <div data-testid="module" />,
}));
vi.mock('./HostVitals', () => ({
  HostVitals: () => <div data-testid="vitals" />,
}));

import { ContextStage } from './ContextStage';

describe('ContextStage responsive layout (Plan B: B19)', () => {
  it('renders desktop stage (hidden md:flex)', () => {
    render(<ContextStage />);
    expect(document.querySelector('[data-context-stage="desktop"]')).toBeTruthy();
  });

  it('renders mobile stage (md:hidden)', () => {
    render(<ContextStage />);
    expect(document.querySelector('[data-context-stage="mobile"]')).toBeTruthy();
  });

  it('renders sheet toggle button on mobile', () => {
    render(<ContextStage />);
    expect(screen.getByRole('button', { name: 'Open context panel' })).toBeTruthy();
  });

  it('sheet is closed by default', () => {
    render(<ContextStage />);
    expect(document.querySelector('[data-sheet]')).toBeNull();
  });

  it('opens sheet when toggle clicked', () => {
    render(<ContextStage />);
    fireEvent.click(screen.getByRole('button', { name: 'Open context panel' }));
    expect(document.querySelector('[data-sheet]')).toBeTruthy();
  });

  it('closes sheet when backdrop clicked', () => {
    render(<ContextStage />);
    fireEvent.click(screen.getByRole('button', { name: 'Open context panel' }));
    expect(document.querySelector('[data-sheet]')).toBeTruthy();
    fireEvent.click(document.querySelector('[data-sheet-backdrop]')!);
    expect(document.querySelector('[data-sheet]')).toBeNull();
  });

  it('closes sheet when close button clicked', () => {
    render(<ContextStage />);
    fireEvent.click(screen.getByRole('button', { name: 'Open context panel' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close context panel' }));
    expect(document.querySelector('[data-sheet]')).toBeNull();
  });

  it('renders aggregate status light in toggle when provided', () => {
    render(
      <ContextStage
        aggregateStatusLight={<span data-testid="agg-light">●</span>}
      />
    );
    expect(screen.getByTestId('agg-light')).toBeTruthy();
  });

  it('sheet has role=dialog and aria-label', () => {
    render(<ContextStage />);
    fireEvent.click(screen.getByRole('button', { name: 'Open context panel' }));
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByRole('dialog').getAttribute('aria-label')).toBe('Context panel');
  });

  it('renders HostVitals in both desktop and sheet', () => {
    render(<ContextStage />);
    // Desktop vitals
    expect(screen.getAllByTestId('vitals').length).toBeGreaterThan(0);
  });

  it('renders dock in both desktop and sheet', () => {
    render(<ContextStage />);
    expect(screen.getAllByTestId('dock').length).toBeGreaterThan(0);
  });

  it('renders staged modules', () => {
    render(
      <ContextStage
        modules={[
          { key: 'm1', module: 'test', props: {} },
        ]}
      />
    );
    expect(screen.getAllByTestId('module').length).toBeGreaterThan(0);
  });
});
