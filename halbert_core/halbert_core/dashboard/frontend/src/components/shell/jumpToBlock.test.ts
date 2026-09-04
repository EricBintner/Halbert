// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * "Go back to this" has to find the thing.
 *
 * A docked terminal leaves `data-terminal-origin` where it used to be; a
 * block leaves `data-terminal-block` on every surface that renders it — the
 * live tool card, the live tile, and the same card after a reload. A task
 * card's jump carries a BLOCK id, so a lookup that only knew about origins
 * silently did nothing for every task in the column.
 */

import { describe, it, expect, afterEach } from 'vitest';
import { findJumpTarget } from './jumpToBlock';

afterEach(() => { document.body.innerHTML = ''; });

describe('findJumpTarget', () => {
  it('finds a docked terminal by its inline origin', () => {
    document.body.innerHTML = '<div data-terminal-origin="term-1" id="hit"></div>';
    expect(findJumpTarget(document.body, 'term-1')?.id).toBe('hit');
  });

  it('finds a block by the anchor every block surface stamps', () => {
    document.body.innerHTML = '<div data-terminal-block="blk-1" id="hit"></div>';
    expect(findJumpTarget(document.body, 'blk-1')?.id).toBe('hit');
  });

  it('prefers the inline origin when an id is somehow both', () => {
    document.body.innerHTML =
      '<div data-terminal-block="x" id="block"></div>' +
      '<div data-terminal-origin="x" id="origin"></div>';
    // The origin is where the thing was in the conversation; the block anchor
    // may be a card rendered elsewhere on the page.
    expect(findJumpTarget(document.body, 'x')?.id).toBe('origin');
  });

  it('returns null rather than throwing on an id with CSS punctuation', () => {
    document.body.innerHTML = '<div data-terminal-block="a" id="hit"></div>';
    expect(findJumpTarget(document.body, 'blk"]:has(*)')).toBeNull();
  });

  it('returns null for an id nothing on the page carries', () => {
    expect(findJumpTarget(document.body, 'nope')).toBeNull();
  });
});
