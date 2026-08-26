import React from 'react';

const PATHS_DISPLAY = [
  'M 512.00 80.00 V 512.00',
  'M 464.00 82.67 V 512.00 A 48.00 48.00 0 0 0 560.00 512.00 V 82.67',
  'M 416.00 90.80 V 512.00 A 96.00 96.00 0 0 0 608.00 512.00 V 90.80',
  'M 368.00 104.71 V 512.00 A 144.00 144.00 0 0 0 656.00 512.00 V 104.71',
  'M 320.00 125.01 V 512.00 A 192.00 192.00 0 0 0 704.00 512.00 V 125.01',
  'M 272.00 152.80 V 512.00 A 240.00 240.00 0 0 0 752.00 512.00 V 152.80',
  'M 224.00 190.01 V 512.00 A 288.00 288.00 0 0 0 800.00 512.00 V 190.01',
  'M 176.00 240.47 V 512.00 A 336.00 336.00 0 0 0 848.00 512.00 V 240.47',
  'M 128.00 314.09 V 512.00 A 384.00 384.00 0 0 0 896.00 512.00 V 314.09',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ');

const PATHS_MEDIUM = [
  'M 512.00 80.00 V 512.00',
  'M 425.60 88.74 V 512.00 A 86.40 86.40 0 0 0 598.40 512.00 V 88.74',
  'M 339.20 116.14 V 512.00 A 172.80 172.80 0 0 0 684.80 512.00 V 116.14',
  'M 252.80 166.42 V 512.00 A 259.20 259.20 0 0 0 771.20 512.00 V 166.42',
  'M 166.40 252.80 V 512.00 A 345.60 345.60 0 0 0 857.60 512.00 V 252.80',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ');

const PATHS_SMALL = [
  'M 512.00 80.00 V 512.00',
  'M 296.00 137.94 V 512.00 A 216.00 216.00 0 0 0 728.00 512.00 V 137.94',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ');

const TIER_CONFIG = {
  display: { paths: PATHS_DISPLAY, strokeWidth: 26.67 },
  medium: { paths: PATHS_MEDIUM, strokeWidth: 48.0 },
  small: { paths: PATHS_SMALL, strokeWidth: 116.0 },
};

/**
 * HalbertMark - Vector Brand Icon & Logo Mark with responsive optical density.
 */
export function HalbertMark({
  size = 48,
  density = 'auto',
  color = 'currentColor',
  backgroundColor = 'transparent',
  strokeWidth,
  className = '',
  style = {},
  ...props
}) {
  let effectiveDensity = density;
  if (density === 'auto') {
    if (typeof size === 'number') {
      if (size <= 24) effectiveDensity = 'small';
      else if (size <= 64) effectiveDensity = 'medium';
      else effectiveDensity = 'display';
    } else {
      effectiveDensity = 'medium';
    }
  }

  const config = TIER_CONFIG[effectiveDensity] || TIER_CONFIG.medium;
  const finalStrokeWidth = strokeWidth ?? config.strokeWidth;

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1024 1024"
      width={size}
      height={size}
      className={className}
      style={{ display: 'inline-block', verticalAlign: 'middle', flexShrink: 0, ...style }}
      aria-hidden="true"
      {...props}
    >
      {backgroundColor && backgroundColor !== 'transparent' && (
        <rect width="1024" height="1024" fill={backgroundColor} />
      )}
      <g
        fill="none"
        stroke={color}
        strokeWidth={finalStrokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={config.paths} />
      </g>
    </svg>
  );
}

export default HalbertMark;
