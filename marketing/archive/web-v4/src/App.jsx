import React, { useRef } from 'react';
import { Navbar } from './components/Navbar';
import { MinimalHero } from './components/MinimalHero';
import { FeatureGrid } from './components/FeatureGrid';
import { MinimalCTA } from './components/MinimalCTA';
import { Footer } from './components/Footer';
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
    <div className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-ink)] selection:bg-[var(--color-ink)] selection:text-white flex flex-col font-sans">
      <Navbar onGetAccessClick={handleScrollToWaitlist} />
      <main className="flex-1">
        <MinimalHero waitlistRef={waitlistRef} />
        <FeatureGrid />
        <MinimalCTA />
      </main>
      <Footer />
      <ThemePicker defaultTheme="studio-light" />
    </div>
  );
}

export default App;
