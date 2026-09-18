import React, { useRef } from 'react';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { TypographicFeatures } from './components/TypographicFeatures';
import { QuoteSection } from './components/QuoteSection';
import { FooterSection } from './components/FooterSection';
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
    <div className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-ink)] selection:bg-white selection:text-[#1D4ED8] flex flex-col font-sans">
      <Navbar onEarlyAccessClick={handleScrollToWaitlist} />
      <main className="flex-1">
        <Hero waitlistRef={waitlistRef} />
        <TypographicFeatures />
        <QuoteSection />
      </main>
      <FooterSection />
      <ThemePicker defaultTheme="cobalt-1968" />
    </div>
  );
}

export default App;
