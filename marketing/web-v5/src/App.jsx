import React from 'react';
import { MagazinePage } from './components/MagazinePage';
import { ThemePicker } from './components/ThemePicker';

export function App() {
  return (
    <div className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-ink)] py-6 px-4 sm:px-8 flex flex-col justify-center items-center">
      <main className="w-full">
        <MagazinePage />
      </main>
      <ThemePicker defaultTheme="cobalt-1968" />
    </div>
  );
}

export default App;
