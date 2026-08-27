// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * CurrentTopicLabel — the open subject's title, pinned to the top of the
 * scroll. One quiet line; it is a bearing, not a control. Changes are
 * announced through the shell's live region (announce('New subject')), so
 * this element itself is aria-live="off".
 *
 * No voice rendering here: a title ("Samba share setup") has no pronouns,
 * so first-person / the-computer / hybrid would all print the same thing.
 * The voice setting applies to the <continuity> prose, which is rendered
 * server-side.
 */

interface CurrentTopicLabelProps {
  thread: { title: string } | null;
}

export function CurrentTopicLabel({ thread }: CurrentTopicLabelProps) {
  if (!thread || !thread.title) return null;
  return (
    <div
      aria-live="off"
      className="sticky top-0 z-10 border-b border-hairline-subtle bg-background/95 px-4 py-1 backdrop-blur"
    >
      <p data-testid="current-topic" className="truncate text-xs text-ink-secondary">
        {thread.title}
      </p>
    </div>
  );
}

export default CurrentTopicLabel;
