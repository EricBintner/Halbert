import React from 'react';
import { IconDock, GitHubIcon, StorybookIcon, XIcon, RedditIcon } from '@halbert/design-system';

// X and Reddit stay disabled with no address until the accounts exist
// (founder, 2026-09-16). Order is the founder's.
const ITEMS = [
  { id: 'github', label: 'GitHub', icon: GitHubIcon, href: 'https://github.com/EricBintner/Halbert' },
  { id: 'storybook', label: 'Storybook', icon: StorybookIcon, href: 'https://storybook.halbert.computer' },
  { id: 'x', label: 'X', icon: XIcon, disabled: true },
  { id: 'reddit', label: 'Reddit', icon: RedditIcon, disabled: true },
];

/**
 * The corner frame every fixed control shares: the header's px-6 / py-4,
 * plus the notch insets. The dossier trigger uses the same numbers on the
 * other side, so the four corners of the page line up.
 */
export const CORNER_INSET = {
  x: 'calc(env(safe-area-inset-right, 0px) + 1.5rem)',
  y: 'calc(env(safe-area-inset-bottom, 0px) + 1rem)',
};

/** The mask the header and folio bar use: white where the vermilion stroke is. */
export const STROKE_MASK = {
  WebkitMaskImage: 'url(#stroke-intersection-mask)',
  maskImage: 'url(#stroke-intersection-mask)',
};

/**
 * Bottom-right corner links, drawn the way the header logo is drawn: a base
 * copy in ink, and a second copy in on-stroke ink masked to the stroke, so
 * the glyphs invert where the vermilion passes under them.
 *
 * The masked copy is a full-viewport layer because the mask is in viewport
 * coordinates (`maskUnits="userSpaceOnUse"` on a 0,0-origin canvas); a small
 * fixed box would put its own top-left at the mask origin and miss. It is
 * `inert` as well as aria-hidden so its duplicate links never enter the tab
 * order.
 */
export function CornerDock() {
  return (
    <>
      <div
        data-testid="corner-dock"
        className="fixed z-30 text-[var(--color-ink)]"
        style={{ right: CORNER_INSET.x, bottom: CORNER_INSET.y }}
      >
        <IconDock items={ITEMS} label="Halbert elsewhere" />
      </div>

      <div
        aria-hidden="true"
        inert
        className="fixed inset-0 z-30 pointer-events-none select-none text-[var(--color-ink-on-stroke)]"
        style={STROKE_MASK}
      >
        <div className="absolute" style={{ right: CORNER_INSET.x, bottom: CORNER_INSET.y }}>
          <IconDock items={ITEMS} label="Halbert elsewhere" />
        </div>
      </div>
    </>
  );
}
