import React from 'react';

/**
 * LayoutStage — places content into the solid colour fields the camera has
 * carved out of the mark.
 *
 * Content is authored per stop in *semantic* slots:
 *   stroke   whatever should sit on the stroke-coloured field
 *   canvas   whatever should sit on the canvas-coloured field
 *   above / below   (full-mark stop only) bands above and below the mark
 *
 * The stop's resolved layout decides where those slots land on screen:
 *   vertical    left / right halves (portrait: one stacked column that
 *               straddles the split, type colour changing at the line)
 *   horizontal  top / bottom halves
 *   diagonal    opposite corner quadrants (clean for 45° splits)
 *   cap         top half (canvas) + the dome rising to the centre (stroke)
 *   full        bands above and below the mark
 *
 * Content moves with the camera: while travelling, the outgoing stop slides
 * away opposite to the camera's direction and the incoming one slides in
 * from the direction of travel.
 */

const clamp01 = (v) => Math.max(0, Math.min(1, v));

const INK = {
  stroke: 'var(--color-ink-on-stroke)',
  canvas: 'var(--color-ink)',
  above: 'var(--color-ink)',
  below: 'var(--color-ink)',
};

// Tailwind scans source for literal class names, so keep these literal.
const PAD_CSS = 'clamp(1.25rem,5vw,4.5rem)';
const PAD = 'p-[clamp(1.25rem,5vw,4.5rem)]';
const PAD_TIGHT = 'px-[clamp(1.25rem,5vw,4.5rem)] py-4';

function Slot({ slot, children, className = '', style, tight = false }) {
  if (!children) return null;
  const pad = tight ? PAD_TIGHT : PAD;
  return (
    <div className={`${pad} flex flex-col ${className}`} style={{ color: INK[slot], ...style }} data-slot={slot}>
      {children}
    </div>
  );
}

/**
 * Renders children twice, clipped to the left and right halves of the
 * viewport, so type can run straight across a vertical split and still be
 * the right ink on each field. The wrapper must span the full viewport width.
 */
function Straddle({ layout, children }) {
  const leftInk = layout.strokeSide === 'left' ? INK.stroke : INK.canvas;
  const rightInk = layout.strokeSide === 'left' ? INK.canvas : INK.stroke;
  return (
    <div className="relative w-full">
      <div className={PAD} style={{ color: leftInk, clipPath: 'inset(0 50% 0 0)' }}>{children}</div>
      <div className={`absolute inset-0 ${PAD}`} style={{ color: rightInk, clipPath: 'inset(0 0 0 50%)' }} aria-hidden="true">
        {children}
      </div>
    </div>
  );
}

function PortraitVerticalLayout({ layout, content }) {
  // reading order follows the fields: whatever sits on the left comes first
  const first = layout.strokeSide === 'left' ? 'stroke' : 'canvas';
  const second = first === 'stroke' ? 'canvas' : 'stroke';
  return (
    <div className="absolute inset-0 flex flex-col justify-center pt-14 pb-16">
      {content[first] && <Straddle layout={layout}><div data-slot={first}>{content[first]}</div></Straddle>}
      {content[second] && <Straddle layout={layout}><div data-slot={second}>{content[second]}</div></Straddle>}
    </div>
  );
}

function VerticalLayout({ layout, content, portrait }) {
  if (portrait) return <PortraitVerticalLayout layout={layout} content={content} />;
  const left = layout.strokeSide === 'left' ? 'stroke' : 'canvas';
  const right = left === 'stroke' ? 'canvas' : 'stroke';
  return (
    <div className="absolute inset-0 grid grid-cols-2 pt-14 pb-16">
      <Slot slot={left} className="justify-center items-start text-left">{content[left]}</Slot>
      <Slot slot={right} className="justify-center items-start text-left">{content[right]}</Slot>
    </div>
  );
}

function HorizontalLayout({ layout, content }) {
  const top = layout.strokeSide === 'top' ? 'stroke' : 'canvas';
  const bottom = top === 'stroke' ? 'canvas' : 'stroke';
  // The U's arc rises towards the frame edges, so the top field loses space there.
  const sagPad = { paddingBottom: `calc(${PAD_CSS} + ${((layout.sag ?? 0) * 100).toFixed(1)}vh)` };
  return (
    <div className="absolute inset-0 grid grid-rows-2 pt-14 pb-16">
      <Slot slot={top} className="justify-end items-start" style={sagPad}>{content[top]}</Slot>
      <Slot slot={bottom} className="justify-start items-start">{content[bottom]}</Slot>
    </div>
  );
}

const CORNER = {
  'top-left': 'row-start-1 col-start-1 justify-start items-start text-left',
  'top-right': 'row-start-1 col-start-2 justify-start items-end text-right',
  'bottom-left': 'row-start-2 col-start-1 justify-end items-start text-left',
  'bottom-right': 'row-start-2 col-start-2 justify-end items-end text-right',
};
const OPPOSITE = {
  'top-left': 'bottom-right',
  'top-right': 'bottom-left',
  'bottom-left': 'top-right',
  'bottom-right': 'top-left',
};

function DiagonalLayout({ layout, content }) {
  const strokeCorner = layout.strokeSide;
  const canvasCorner = OPPOSITE[strokeCorner];
  return (
    <div className="absolute inset-0 grid grid-cols-2 grid-rows-2 pt-14 pb-16">
      <Slot slot="stroke" className={CORNER[strokeCorner]}>{content.stroke}</Slot>
      <Slot slot="canvas" className={CORNER[canvasCorner]}>{content.canvas}</Slot>
    </div>
  );
}

function CapLayout({ content }) {
  return (
    <div className="absolute inset-0 grid grid-rows-2 pt-14 pb-16">
      <Slot slot="canvas" className="justify-end items-center text-center">{content.canvas}</Slot>
      <Slot slot="stroke" className="justify-start items-center text-center">{content.stroke}</Slot>
    </div>
  );
}

function FullLayout({ content }) {
  return (
    <div className="absolute inset-0 grid grid-rows-[1fr_auto_1fr] pt-14 pb-14">
      <Slot slot="above" className="justify-end items-center text-center" tight>{content.above}</Slot>
      {/* matches fitScale(aspect, 0.5): the mark spans half the shorter viewport side */}
      <div className="h-[50vmin]" aria-hidden="true" />
      <Slot slot="below" className="justify-start items-center text-center" tight>{content.below}</Slot>
    </div>
  );
}

const LAYOUTS = {
  vertical: VerticalLayout,
  horizontal: HorizontalLayout,
  diagonal: DiagonalLayout,
  cap: CapLayout,
  full: FullLayout,
};

/** Visibility + offset of each stop's content for the current camera state. */
function stageItems(camera, stops, viewport) {
  const D = 0.6;
  return stops.map((stop, i) => {
    let opacity = 0;
    let tx = 0;
    let ty = 0;
    if (camera.phase === 'dwell') {
      if (camera.stopIndex === i) opacity = 1;
    } else if (camera.move) {
      const { from, to, t, dir } = camera.move;
      if (i === from) {
        opacity = clamp01(1 - t * 2.4);
        tx = -dir.x * t * D * viewport.width;
        ty = -dir.y * t * D * viewport.height;
      } else if (i === to) {
        opacity = clamp01((t - 0.5) * 2.4);
        tx = dir.x * (1 - t) * D * viewport.width;
        ty = dir.y * (1 - t) * D * viewport.height;
      }
    }
    return { stop, index: i, opacity, tx, ty };
  });
}

export function LayoutStage({ camera, stops, content, viewport }) {
  const items = stageItems(camera, stops, viewport);
  const portrait = viewport.width < viewport.height;
  return (
    <div className="fixed inset-0 z-10 pointer-events-none overflow-hidden">
      {items.map(({ stop, index, opacity, tx, ty }) => {
        if (opacity <= 0.005) return null;
        const layout = camera.poses[index].layout;
        const Layout = LAYOUTS[layout.kind] ?? VerticalLayout;
        const slots = content[stop.id] ?? {};
        return (
          <div
            key={stop.id}
            className="absolute inset-0 will-change-transform"
            style={{
              opacity,
              transform: `translate3d(${tx.toFixed(1)}px, ${ty.toFixed(1)}px, 0)`,
              pointerEvents: opacity > 0.9 ? 'auto' : 'none',
            }}
            data-stop={stop.id}
            data-layout={layout.kind}
          >
            <Layout layout={layout} content={slots} portrait={portrait} />
          </div>
        );
      })}
    </div>
  );
}
