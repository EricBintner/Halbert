// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * TetherChip Component
 *
 * Small inline pill in the conversation stream marking where a terminal tile
 * used to be before it docked into the right-column accordion, e.g.
 * "Terminal #a1b2c3d4: zfs scrub → DOCKED". Click scrolls back to the tile's
 * original position; hover highlights the docked card.
 */

interface TetherChipProps {
  sessionId: string;
  label: string;        // e.g. "zfs scrub"
  docked: boolean;
  onClick?: () => void;  // scroll back to original position
  onHover?: () => void;  // highlight docked card
}

export function TetherChip({ sessionId, label, docked, onClick, onHover }: TetherChipProps) {
  const stateClasses = docked
    ? 'bg-info/20 text-info border-info/40 hover:bg-info/30'
    : 'bg-muted text-muted-foreground border-border hover:bg-muted/80';

  return (
    <button
      type="button"
      data-session-id={sessionId}
      onClick={onClick}
      onMouseEnter={onHover}
      className={`
        inline-flex items-center gap-1.5 rounded-full border cursor-pointer
        px-2 py-0.5 text-[10px] font-mono transition-colors
        ${stateClasses}
      `}
    >
      <span>Terminal #{sessionId.slice(0, 8)}</span>
      <span className="text-muted-foreground truncate max-w-[12rem]">{label}</span>
      {docked && <span className="uppercase tracking-wide shrink-0">→ DOCKED</span>}
    </button>
  );
}

export default TetherChip;
