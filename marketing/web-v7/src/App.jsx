import React, { useState, useEffect, useRef } from 'react';
import { getCameraState, WAYPOINTS } from './lib/cameraMotion';
import { VectorCanvas } from './components/VectorCanvas';
import { WaypointOverlay } from './components/WaypointOverlay';
import { ScrollHUD } from './components/ScrollHUD';
import { ThemePicker } from './components/ThemePicker';

export function App() {
  const [scrollProgress, setScrollProgress] = useState(0);
  const containerRef = useRef(null);

  useEffect(() => {
    const handleScroll = () => {
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      if (maxScroll > 0) {
        const s = Math.max(0, Math.min(1, window.scrollY / maxScroll));
        setScrollProgress(s);
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const camera = getCameraState(scrollProgress);

  const handleJumpToWaypoint = (wpIndex) => {
    const targetWp = WAYPOINTS[wpIndex];
    if (targetWp) {
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      window.scrollTo({
        top: targetWp.sCenter * maxScroll,
        behavior: 'smooth',
      });
    }
  };

  return (
    <div ref={containerRef} className="relative min-h-[500vh] bg-[var(--color-canvas)] text-white vector-grit">
      {/* Dynamic 1000% Vector Canvas Layer */}
      <VectorCanvas camera={camera} />

      {/* Interactive Waypoint Content & HUD Layer */}
      <WaypointOverlay camera={camera} onJumpToWaypoint={handleJumpToWaypoint} />

      {/* Right Scroll Scrubber HUD */}
      <ScrollHUD
        currentWaypoint={camera.activeWaypoint}
        onSelectWaypoint={handleJumpToWaypoint}
        scrollProgress={scrollProgress}
      />

      {/* Dev Theme Switcher */}
      <ThemePicker defaultTheme="chartreuse-teal" />
    </div>
  );
}

export default App;
