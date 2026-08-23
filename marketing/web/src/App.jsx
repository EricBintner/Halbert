import React, { useRef } from 'react';
import { useSmoothScroll } from './lib/useSmoothScroll';
import { Header } from './components/Header';
import { Hero } from './components/Hero';
import { HowItWorks } from './components/HowItWorks';
import { TheBeing } from './components/TheBeing';
import { Footer } from './components/Footer';

export function App() {
  useSmoothScroll();
  const waitlistRef = useRef(null);

  const handleScrollToWaitlist = () => {
    if (waitlistRef.current) {
      waitlistRef.current.scrollIntoView({ behavior: 'smooth' });
      const input = waitlistRef.current.querySelector('input');
      if (input) input.focus();
    }
  };

  return (
    <div className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-ink)] selection:bg-[var(--color-accent)] selection:text-white flex flex-col">
      <Header onJoinWaitlistClick={handleScrollToWaitlist} />
      <main className="flex-1">
        <Hero waitlistRef={waitlistRef} />
        <HowItWorks />
        <TheBeing />
      </main>
      <Footer />
    </div>
  );
}

export default App;
