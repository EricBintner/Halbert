import React, { useState, useEffect } from 'react';
import { ExperimentalHero } from './components/ExperimentalHero';
import { ScrollyProductWindow } from './components/ScrollyProductWindow';
import { SoulPosterWindow } from './components/SoulPosterWindow';
import { GrainShaderOverlay } from './components/GrainShaderOverlay';
import { ThemePicker } from './components/ThemePicker';

export function App() {
  const [scrollY, setScrollY] = useState(0);

  useEffect(() => {
    const handleScroll = () => {
      setScrollY(window.scrollY);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-ink)] selection:bg-[#6366F1] selection:text-white flex flex-col font-sans relative">
      <GrainShaderOverlay />
      <main className="flex-1 w-full">
        {/* Full-Window Hero with Large Centered Logo & 80% Blue-Violet SVG Installation */}
        <ExperimentalHero scrollY={scrollY} />

        {/* Full-Window Experience 1: Product in Action with Scrollytelling Overlay */}
        <ScrollyProductWindow />

        {/* Full-Window Experience 2: Soul Poster & Dispatch */}
        <SoulPosterWindow />
      </main>

      <ThemePicker defaultTheme="linen-violet" />
    </div>
  );
}

export default App;
