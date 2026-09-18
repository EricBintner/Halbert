import React, { useRef, useState } from 'react';
import { useSmoothScroll } from './lib/useSmoothScroll';
import { copyVariants } from './copy';
import { Header } from './components/Header';
import { Hero } from './components/Hero';
import { HowItWorks } from './components/HowItWorks';
import { TheBeing } from './components/TheBeing';
import { Footer } from './components/Footer';
import { ThemePicker } from './components/ThemePicker';

export function App() {
  useSmoothScroll();
  const [selectedVariant, setSelectedVariant] = useState('a');
  const copy = copyVariants[selectedVariant] || copyVariants.a;

  const waitlistRef = useRef(null);

  const handleScrollToWaitlist = () => {
    if (waitlistRef.current) {
      waitlistRef.current.scrollIntoView({ behavior: 'smooth' });
      const input = waitlistRef.current.querySelector('input');
      if (input) input.focus();
    }
  };

  return (
    <div className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-ink)] selection:bg-[var(--color-accent)] selection:text-white flex flex-col font-sans">
      {/* 60s Copy Variant Switcher (Discreet Top Bar) */}
      <div className="bg-[var(--color-ink)] text-white text-[11px] font-mono py-1.5 px-6 flex justify-between items-center select-none border-b border-[var(--color-ink)]">
        <span className="hidden sm:inline tracking-wider uppercase text-[var(--color-ink-ghost)]">
          HALBERT PRINT FOLIO · 1960s DDB EDITORIAL EDITION
        </span>
        <div className="flex items-center space-x-3 ml-auto">
          <span className="text-[var(--color-ink-ghost)] uppercase">Copy Strategy:</span>
          <button
            onClick={() => setSelectedVariant('a')}
            className={`px-2 py-0.5 uppercase tracking-wider ${
              selectedVariant === 'a'
                ? 'bg-[var(--color-accent)] text-white font-bold'
                : 'text-[var(--color-ink-ghost)] hover:text-white'
            }`}
          >
            Variant A (Direct)
          </button>
          <button
            onClick={() => setSelectedVariant('b')}
            className={`px-2 py-0.5 uppercase tracking-wider ${
              selectedVariant === 'b'
                ? 'bg-[var(--color-accent)] text-white font-bold'
                : 'text-[var(--color-ink-ghost)] hover:text-white'
            }`}
          >
            Variant B (Minimalist)
          </button>
        </div>
      </div>

      <Header copy={copy} onJoinWaitlistClick={handleScrollToWaitlist} />
      <main className="flex-1">
        <Hero copy={copy} waitlistRef={waitlistRef} />
        <HowItWorks copy={copy} />
        <TheBeing copy={copy} />
      </main>
      <Footer copy={copy} />
      <ThemePicker defaultTheme="olivetti-1968" />
    </div>
  );
}

export default App;
