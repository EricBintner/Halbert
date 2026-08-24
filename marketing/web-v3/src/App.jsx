import React, { useRef } from 'react';
import { EditorialMasthead } from './components/EditorialMasthead';
import { RetroSerifHero } from './components/RetroSerifHero';
import { LiterarySpreads } from './components/LiterarySpreads';
import { ConfessionalPlate } from './components/ConfessionalPlate';
import { EditorialColophon } from './components/EditorialColophon';
import { ThemePicker } from './components/ThemePicker';

export function App() {
  const waitlistRef = useRef(null);

  const handleScrollToWaitlist = () => {
    if (waitlistRef.current) {
      waitlistRef.current.scrollIntoView({ behavior: 'smooth' });
      const input = waitlistRef.current.querySelector('input');
      if (input) input.focus();
    }
  };

  return (
    <div className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-ink)] selection:bg-[var(--color-accent)] selection:text-[#1B447A] flex flex-col font-sans">
      <EditorialMasthead onSubscribeClick={handleScrollToWaitlist} />
      <main className="flex-1">
        <RetroSerifHero waitlistRef={waitlistRef} />
        <LiterarySpreads />
        <ConfessionalPlate />
      </main>
      <EditorialColophon />
      <ThemePicker defaultTheme="aegean-blue" />
    </div>
  );
}

export default App;
