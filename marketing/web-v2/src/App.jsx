import React, { useRef } from 'react';
import { DraftingHeader } from './components/DraftingHeader';
import { SwissHero } from './components/SwissHero';
import { AutobiographyTape } from './components/AutobiographyTape';
import { ConfigBlueprint } from './components/ConfigBlueprint';
import { ProofConsole } from './components/ProofConsole';
import { ManifestFooter } from './components/ManifestFooter';
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
    <div className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-ink)] selection:bg-[var(--color-accent)] selection:text-white flex flex-col font-sans">
      <DraftingHeader onEarlyAccessClick={handleScrollToWaitlist} />
      <main className="flex-1">
        <SwissHero waitlistRef={waitlistRef} />
        <AutobiographyTape />
        <ConfigBlueprint />
        <ProofConsole />
      </main>
      <ManifestFooter />
      <ThemePicker defaultTheme="bauhaus-amber" />
    </div>
  );
}

export default App;
