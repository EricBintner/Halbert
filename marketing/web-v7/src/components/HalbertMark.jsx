import React from 'react';
import { MARK_PATH_D } from '../lib/markGeometry';

/**
 * HalbertMark - Vector Brand Icon & Logo Mark (same geometry as the canvas).
 */
export function HalbertMark({
  size = 48,
  color = 'currentColor',
  backgroundColor = 'transparent',
  strokeWidth = 28,
  className = '',
  style = {},
  ...props
}) {
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
      {backgroundColor && backgroundColor !== 'transparent' && (
        <rect width="1024" height="1024" fill={backgroundColor} />
      )}
      <g
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d={MARK_PATH_D} />
      </g>
    </svg>
  );
}

export default HalbertMark;
