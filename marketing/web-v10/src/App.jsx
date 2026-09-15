import React, { useEffect, useState } from 'react';
import { getCameraState, stopCenterS, timelineFor } from './lib/cameraEngine';
import { STOPS } from './lib/storyboard';
import { STOP_CONTENT } from './content/stops';
import { VectorCanvas } from './components/VectorCanvas';
import { LayoutStage } from './components/LayoutStage';
import { ScrollHUD } from './components/ScrollHUD';
import { Reticle } from './components/Reticle';
import { HalbertMark } from '@halbert/design-system'

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
  const isFixedParam = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('s') !== null;
  const [s, setS] = useState(() => {
    if (typeof window !== 'undefined') {
      const p = new URLSearchParams(window.location.search).get('s');
      if (p !== null) return Math.max(0, Math.min(1, parseFloat(p) || 0));
    }
    return 0;
  });
  useEffect(() => {
    if (isFixedParam) return;
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
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [isFixedParam]);
  return s;
}

function FolioBar({ camera, reticle, isOverlay = false }) {
  return (
    <header
      className={`fixed top-0 inset-x-0 z-30 flex items-center justify-between px-6 py-4 text-[14px] font-mono pointer-events-none ${
        isOverlay
          ? 'text-[var(--color-ink-on-stroke)] select-none'
          : 'text-[var(--color-ink)]'
      }`}
      style={{
        // py-4 base stays; add the notch inset on top so unnotched displays
        // (env() = 0) keep the original 16px padding.
        paddingTop: 'calc(1rem + env(safe-area-inset-top))',
        ...(isOverlay
          ? {
              WebkitMaskImage: 'url(#stroke-intersection-mask)',
              maskImage: 'url(#stroke-intersection-mask)',
            }
          : null),
      }}
      aria-hidden={isOverlay ? 'true' : undefined}
    >
      <div className="flex items-center space-x-3">
        <HalbertMark size={24} density="medium" color="currentColor" />
        <span className="font-bold tracking-wider">HALBERT</span>
      </div>
      <div
        className={`hidden md:flex items-center space-x-4 ${isOverlay ? 'pointer-events-none' : 'pointer-events-auto'}`}
        data-testid={isOverlay ? undefined : 'header-right'}
        data-stop-index={camera.stopIndex}
        data-stop-id={STOPS[camera.stopIndex]?.id}
        data-zoom={Math.round(camera.scale * 100)}
      >
        <span></span>
        {(reticle || (typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('debug'))) && (
          <div className="flex items-center space-x-4 opacity-80">
            <span>STOP {String(camera.stopIndex + 1).padStart(2, '0')} / {String(STOPS.length).padStart(2, '0')} · {camera.layout.kind.toUpperCase()}</span>
            <span>ZOOM {Math.round(camera.scale * 100)}%</span>
            <span>[D] RETICLE</span>
          </div>
        )}
      </div>
    </header>
  );
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

  const jumpToStop = (i, smooth = true) => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    window.scrollTo({ top: stopCenterS(i, aspect) * max, behavior: smooth ? 'smooth' : 'auto' });
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const stopParam = params.get('stop') || window.location.hash.replace('#', '');
    if (stopParam) {
      const idx = STOPS.findIndex(
        (st, i) => st.id.toLowerCase() === stopParam.toLowerCase() || String(i) === stopParam || String(i + 1) === stopParam
      );
      if (idx >= 0) {
        jumpToStop(idx, false);
      }
    }
  }, [aspect]);

  return (
    <div
      className="relative bg-[var(--color-canvas)] text-[var(--color-ink)]"
      style={{ height: `${timeline.totalWeight * 100}vh` }}
    >
      <VectorCanvas camera={camera} viewport={viewport} />

      <LayoutStage camera={camera} stops={STOPS} content={STOP_CONTENT} viewport={viewport} />

      {/* Folio bar — base layer (black ink on canvas) */}
      <FolioBar camera={camera} reticle={reticle} />

      {/* Folio bar — inverted overlay layer (white ink where intersecting red stroke) */}
      <FolioBar camera={camera} reticle={reticle} isOverlay />

      <ScrollHUD currentStop={camera.stopIndex} onSelectStop={jumpToStop} scrollProgress={s} />

      <Reticle visible={reticle} camera={camera} />

    </div>
  );
}

export default App;
