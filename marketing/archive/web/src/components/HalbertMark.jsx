import React from 'react';

/**
 * HalbertMark - Vector Brand Icon & Logo Mark
 * 
 * Exact geometric construction:
 * - Concentric U-tracks with pitch p = 48 on 1024x1024 canvas
 * - Perfect spherical / circular envelope of radius R = 432
 * - Center vertical spine with 9 nested concentric U-arcs
 * - Rounded line caps (Mid-century Olivetti / Braun industrial aesthetic)
 */
export function HalbertMark({
  size = 48,
  color = 'var(--color-accent, #D34E24)',
  backgroundColor = 'transparent',
  strokeWidth = 26.67,
  className = '',
  style = {},
  variant = 'default', // 'default' | 'vermilion' | 'charcoal' | 'badge' | 'canvas'
  ...props
}) {
  let fg = color;
  let bg = backgroundColor;
  let rx = 0;

  if (variant === 'vermilion') {
    fg = '#D34E24';
  } else if (variant === 'charcoal') {
    fg = '#1A1918';
  } else if (variant === 'badge') {
    fg = '#F7F5F0';
    bg = '#D34E24';
    rx = 224;
  } else if (variant === 'canvas') {
    fg = '#D34E24';
    bg = '#F7F5F0';
  }

  // Combined path data for the 10 concentric tracks (Center spine + 9 U-curves)
  const pathData = [
    'M 512.00 80.00 V 512.00',
    'M 464.00 82.67 V 512.00 A 48.00 48.00 0 0 0 560.00 512.00 V 82.67',
    'M 416.00 90.80 V 512.00 A 96.00 96.00 0 0 0 608.00 512.00 V 90.80',
    'M 368.00 104.71 V 512.00 A 144.00 144.00 0 0 0 656.00 512.00 V 104.71',
    'M 320.00 125.01 V 512.00 A 192.00 192.00 0 0 0 704.00 512.00 V 125.01',
    'M 272.00 152.80 V 512.00 A 240.00 240.00 0 0 0 752.00 512.00 V 152.80',
    'M 224.00 190.01 V 512.00 A 288.00 288.00 0 0 0 800.00 512.00 V 190.01',
    'M 176.00 240.47 V 512.00 A 336.00 336.00 0 0 0 848.00 512.00 V 240.47',
    'M 128.00 314.09 V 512.00 A 384.00 384.00 0 0 0 896.00 512.00 V 314.09',
    'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00'
  ].join(' ');

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1024 1024"
      width={size}
      height={size}
      className={className}
      style={{ display: 'inline-block', verticalAlign: 'middle', ...style }}
      {...props}
    >
      {bg && bg !== 'transparent' && (
        <rect width="1024" height="1024" rx={rx} fill={bg} />
      )}
      <g
        fill="none"
        stroke={fg}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={pathData} />
      </g>
    </svg>
  );
}

export default HalbertMark;
