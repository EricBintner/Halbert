import React, { useEffect, useState } from 'react';
import { getCameraState, stopCenterS, timelineFor } from './lib/cameraEngine';
import { STOPS } from './lib/storyboard';
import { STOP_CONTENT } from './content/stops';
import { VectorCanvas } from './components/VectorCanvas';
import { LayoutStage } from './components/LayoutStage';
import { ScrollHUD } from './components/ScrollHUD';
import { Reticle } from './components/Reticle';
import { HalbertMark } from './components/HalbertMark';

function useViewport() {
  const read = () => ({
    width: typeof window !== 'undefined' ? window.innerWidth : 1920,
    height: typeof window !== 'undefined' ? window.innerHeight : 1080,
  });
  const [viewport, setViewport] = useState(read);
  useEffect(() => {
    const onResize = () => setViewport(read());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  return viewport;
}

function useScrollProgress() {
  const [s, setS] = useState(0);
  useEffect(() => {
    let raf = 0;
    const read = () => {
      raf = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setS(max > 0 ? Math.max(0, Math.min(1, window.scrollY / max)) : 0);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(read);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    read();
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);
  return s;
}

export function App() {
  const viewport = useViewport();
  const s = useScrollProgress();
  const [reticle, setReticle] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'd' || e.key === 'D') setReticle((v) => !v);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const aspect = viewport.width / Math.max(1, viewport.height);
  const timeline = timelineFor(aspect);
  const camera = getCameraState(s, aspect, timeline);

  const jumpToStop = (i) => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    window.scrollTo({ top: stopCenterS(i, aspect) * max, behavior: 'smooth' });
  };

  return (
    <div
      className="relative bg-[var(--color-canvas)] text-[var(--color-ink)]"
      style={{ height: `${timeline.totalWeight * 100}vh` }}
    >
      <VectorCanvas camera={camera} viewport={viewport} />

      <LayoutStage camera={camera} stops={STOPS} content={STOP_CONTENT} viewport={viewport} />

      {/* Folio bar — chrome that never moves */}
      <header className="fixed top-0 inset-x-0 z-30 flex items-center justify-between px-6 py-4 text-[11px] font-mono text-[var(--color-ink)] pointer-events-none">
        <div className="flex items-center space-x-3">
          <HalbertMark size={22} density="medium" color="currentColor" />
          <span className="font-bold tracking-wider">HALBERT</span>
        </div>
        <div className="hidden md:flex items-center space-x-4 opacity-80">
          <span>STOP {String(camera.stopIndex + 1).padStart(2, '0')} / {String(STOPS.length).padStart(2, '0')} · {camera.layout.kind.toUpperCase()}</span>
          <span>ZOOM {Math.round(camera.scale * 100)}%</span>
          <span>[D] RETICLE</span>
        </div>
      </header>

      <ScrollHUD currentStop={camera.stopIndex} onSelectStop={jumpToStop} scrollProgress={s} />

      <Reticle visible={reticle} camera={camera} />

    </div>
  );
}

export default App;
