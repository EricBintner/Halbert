import React from 'react';

export function BlueVioletInstallation({ scrollY = 0 }) {
  // Parallax transform calculation
  const parallaxOffset = scrollY * 0.25;
  const rotationOffset = scrollY * 0.05;

  return (
    <div
      className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[88vw] h-[82vh] pointer-events-none select-none transition-transform duration-75 ease-out"
      style={{
        transform: `translate(-50%, calc(-50% + ${parallaxOffset}px)) rotate(${rotationOffset}deg)`,
      }}
    >
      <svg
        viewBox="0 0 1200 1000"
        className="w-full h-full opacity-80"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="violetGrad1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#C7D2FE" stopOpacity="0.8" />
            <stop offset="50%" stopColor="#818CF8" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#6366F1" stopOpacity="0.3" />
          </linearGradient>

          <linearGradient id="violetGrad2" x1="100%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#A5B4FC" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#4F46E5" stopOpacity="0.2" />
          </linearGradient>

          <filter id="cmyk-shift">
            <feOffset dx="-2" dy="-1" in="SourceGraphic" result="cyan" />
            <feOffset dx="2" dy="1" in="SourceGraphic" result="magenta" />
            <feMerge>
              <feMergeNode in="cyan" />
              <feMergeNode in="magenta" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Outer Architectural Grid Coordinates */}
        <g stroke="#C7D2FE" strokeWidth="1" strokeDasharray="4 8" opacity="0.6">
          <circle cx="600" cy="500" r="460" />
          <circle cx="600" cy="500" r="380" />
          <line x1="600" y1="20" x2="600" y2="980" />
          <line x1="100" y1="500" x2="1100" y2="500" />
        </g>

        {/* 1960s Constructivist Harmonic Ripple Arcs */}
        {[...Array(14)].map((_, i) => {
          const r = 80 + i * 28;
          return (
            <path
              key={`arc-a-${i}`}
              d={`M ${600 - r} 500 A ${r} ${r} 0 0 1 ${600 + r} 500`}
              stroke="url(#violetGrad1)"
              strokeWidth={2 + (i % 3)}
              strokeLinecap="round"
              opacity={0.4 + (i % 5) * 0.12}
            />
          );
        })}

        {[...Array(14)].map((_, i) => {
          const r = 90 + i * 28;
          return (
            <path
              key={`arc-b-${i}`}
              d={`M ${600 - r} 500 A ${r} ${r} 0 0 0 ${600 + r} 500`}
              stroke="url(#violetGrad2)"
              strokeWidth={1.5 + (i % 2)}
              strokeLinecap="round"
              strokeDasharray={i % 2 === 0 ? 'none' : '6 6'}
              opacity={0.35 + (i % 4) * 0.15}
            />
          );
        })}

        {/* Radiating Tangent Crosshairs */}
        <g stroke="#818CF8" strokeWidth="1.5" opacity="0.5">
          <path d="M 200 200 L 1000 800" strokeDasharray="3 9" />
          <path d="M 200 800 L 1000 200" strokeDasharray="3 9" />
        </g>

        {/* Architectural Registration Marks */}
        <g stroke="#6366F1" strokeWidth="2" opacity="0.7">
          <circle cx="600" cy="500" r="28" fill="#FAF8F5" />
          <path d="M 585 500 H 615" />
          <path d="M 600 485 V 515" />
        </g>
      </svg>
    </div>
  );
}
