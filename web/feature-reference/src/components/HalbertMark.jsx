import React from 'react';

const PATHS_10 = [
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

const PATHS_6 = [
  'M 512.00 80.00 V 512.00',
  'M 425.60 88.74 V 512.00 A 86.40 86.40 0 0 0 598.40 512.00 V 88.74',
  'M 339.20 116.14 V 512.00 A 172.80 172.80 0 0 0 684.80 512.00 V 116.14',
  'M 252.80 166.42 V 512.00 A 259.20 259.20 0 0 0 771.20 512.00 V 166.42',
  'M 166.40 252.80 V 512.00 A 345.60 345.60 0 0 0 857.60 512.00 V 252.80',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ');

const PATHS_3 = [
  'M 512.00 80.00 V 512.00',
  'M 296.00 137.94 V 512.00 A 216.00 216.00 0 0 0 728.00 512.00 V 137.94',
  'M 80.00 512.00 A 432.00 432.00 0 0 0 944.00 512.00',
].join(' ');

export function HalbertMark({
  size = 24,
  density = 'medium',
  color = 'currentColor',
  className = '',
  style = {},
  ...props
}) {
  let paths = PATHS_6;
  let strokeWidth = 48.0;

  if (density === 'small' || size <= 20) {
    paths = PATHS_3;
    strokeWidth = 116.0;
  } else if (density === 'display' || size >= 64) {
    paths = PATHS_10;
    strokeWidth = 26.67;
  }

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1024 1024"
      width={size}
      height={size}
      className={`shrink-0 inline-block align-middle ${className}`}
      style={style}
      aria-hidden="true"
      {...props}
    >
      <g
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={paths} />
      </g>
    </svg>
  );
}
