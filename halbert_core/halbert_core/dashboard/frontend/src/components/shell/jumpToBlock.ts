// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Where "go back to this" lands.
 *
 * Two kinds of id reach the same handler and they are anchored differently:
 *
 * - a docked terminal's SESSION id, marked by `data-terminal-origin` at the
 *   spot in the conversation the tile was scrolled away from;
 * - a task card's BLOCK id, marked by `data-terminal-block` on every surface
 *   that renders a block — the live tool card, the live tile, and the same
 *   card after a reload.
 *
 * A lookup that knew only about origins did nothing at all for every task in
 * the column, silently: `querySelector` returns null and an optional-chained
 * `scrollIntoView` is a no-op, so the button looked broken rather than
 * unfinished.
 */

/** The element to scroll to for `id`, or null when the page has none. */
export function findJumpTarget(root: ParentNode, id: string): HTMLElement | null {
  if (!id) return null;
  let escaped: string;
  try {
    // An id is data, and data can contain CSS punctuation. Without escaping,
    // a crafted or merely odd id turns a lookup into a selector.
    escaped = CSS.escape(id);
  } catch {
    return null;
  }
  try {
    return (
      (root.querySelector(`[data-terminal-origin="${escaped}"]`) as HTMLElement | null) ??
      (root.querySelector(`[data-terminal-block="${escaped}"]`) as HTMLElement | null)
    );
  } catch {
    return null;
  }
}

export default findJumpTarget;
