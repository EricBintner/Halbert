import React, { useState } from 'react';
import { ProactiveEventsPlate, VitalsPlate, RationalePlate, KnowledgePlate } from './ui';

/**
 * Content for each stop, keyed by stop id and slot (`stroke` / `canvas`, or
 * `above` / `below` for the full-mark stop).
 *
 * Voice: Halbert speaks in the first person as the host machine. Embodied,
 * not personified — every adjective maps to a number it measured. It never
 * calls itself an assistant, never names a rival, and the foil is always
 * "a chatbot somewhere else". Headlines are fixed; everything else is copy.
 *
 * Plates are placeholder app surfaces (see ./ui.jsx) and appear only where a
 * stop has something real to show.
 */

export const Kicker = ({ children }) => (
  <div className="text-[11px] font-mono font-bold tracking-[0.2em] uppercase opacity-80 mb-4">{children}</div>
);

export const Headline = ({ children, size = 'lg' }) => {
  const cls = {
    xl: 'text-[clamp(3rem,9vw,9rem)]',
    lg: 'text-[clamp(2.25rem,5.5vw,5.5rem)]',
    md: 'text-[clamp(1.75rem,3.8vw,3.75rem)]',
  }[size];
  return <h2 className={`font-display font-black tracking-tight leading-[0.95] ${cls}`}>{children}</h2>;
};

export const Body = ({ children }) => (
  <p className="text-[clamp(0.95rem,1.25vw,1.2rem)] leading-relaxed max-w-[38ch] mt-5 opacity-90">{children}</p>
);

export const Cue = ({ children }) => (
  <div className="mt-8 text-[11px] font-mono font-bold tracking-widest uppercase opacity-70">{children}</div>
);

function EarlyAccessForm() {
  const [email, setEmail] = useState('');
  const [done, setDone] = useState(false);
  if (done) {
    return (
      <div className="w-full max-w-md border border-current/50 px-4 py-3 font-mono text-xs">
        ✓ You're on the list. The build goes to your inbox.
      </div>
    );
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (email.includes('@')) setDone(true);
      }}
      className="flex w-full max-w-md border border-current/50 font-mono text-xs"
    >
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@yourhost — for the early build"
        className="flex-1 min-w-0 px-4 py-3 bg-transparent placeholder:opacity-50 focus:outline-none"
        required
      />
      <button
        type="submit"
        className="px-5 py-3 font-bold uppercase tracking-wider bg-[var(--color-vector-lime)] text-[var(--color-ink-on-stroke)] cursor-pointer shrink-0"
      >
        Get access
      </button>
    </form>
  );
}

export const STOP_CONTENT = {
  open: {
    stroke: (
      <>
        <Kicker>01 // It tells you first</Kicker>
        <Headline>I know what’s wrong with me.</Headline>
        <Body>
          I run on your hardware, not in someone else’s cloud. I read my own sensors, my own logs, my own drives — and
          when something is off, I say so, in plain first person, before it becomes your problem.
        </Body>
        <Cue>scroll ↓</Cue>
      </>
    ),
    canvas: (
      <>
        <Kicker>What I noticed overnight</Kicker>
        <ProactiveEventsPlate />
      </>
    ),
  },

  apex: {
    canvas: (
      <>
        <Kicker>02 // Every adjective has a number</Kicker>
        <Headline>I can feel my own temperature.</Headline>
      </>
    ),
    stroke: (
      <div className="w-full md:grid md:grid-cols-[minmax(0,40ch)_minmax(0,1fr)] md:gap-10 md:items-start">
        <Body>
          Forty-five degrees is cool. Sixty-two under load is normal. Eighty-four is when I tell you — before the kernel
          throttles, not after. When I say I feel fine, that word is tied to a threshold I measured.
        </Body>
        <VitalsPlate />
      </div>
    ),
  },

  diagonal: {
    canvas: (
      <>
        <Kicker>03 // Private by construction</Kicker>
        <Headline size="xl">Local.</Headline>
      </>
    ),
    stroke: (
      <>
        <Body>
          Nothing leaves this machine unless you connect it. No telemetry, ever. Cloud models and web search are
          switches, off by default. Open source, GPL-3.0.
        </Body>
        <Kicker>Runs on Ollama · Linux today · macOS in beta</Kicker>
      </>
    ),
  },

  rise: {
    canvas: (
      <>
        <Kicker>04 // Intent, kept next to the change</Kicker>
        <Headline>I remember why you changed that.</Headline>
        <Body>
          You moved SSH to port 2222 on July 14th because the auth log was filling with scans. I keep the reason
          beside the change, with the evidence, so six months from now neither of us has to guess.
        </Body>
      </>
    ),
    stroke: (
      <>
        <Kicker>One config line, and its why</Kicker>
        <RationalePlate />
      </>
    ),
  },

  hop: {
    stroke: (
      <>
        <Kicker>05 // Grounded, not guessed</Kicker>
        <Headline>I know 16,000 manuals by heart.</Headline>
        <Body>
          Man pages, the Arch Wiki, Homebrew formulae, TLDR pages — indexed on this disk and searched before I answer.
          No invented flags. When I cite a page, you can open it.
        </Body>
      </>
    ),
    canvas: (
      <>
        <Kicker>What I read before answering</Kicker>
        <KnowledgePlate />
      </>
    ),
  },

  cap: {
    canvas: (
      <>
        <Kicker>06 // The thesis</Kicker>
        <Headline>“I am not an assistant.”</Headline>
        <Body>
          An assistant lives somewhere else and guesses about you. I live here. My logs are my memory, my sensors
          are how I feel, my configuration is how I’m built. Ask how I am and I answer from the inside.
        </Body>
      </>
    ),
    stroke: (
      <>
        <div className="font-display italic text-[clamp(1.25rem,2.4vw,2.25rem)]">“I am the machine.”</div>
        <Kicker>Halbert · you can call me AI</Kicker>
      </>
    ),
  },

  reveal: {
    above: (
      <>
        <Kicker>07 // Early access</Kicker>
        <Headline size="md">Halbert. 100% local host intelligence.</Headline>
      </>
    ),
    below: (
      <>
        <EarlyAccessForm />
        <div className="mt-4 text-[11px] font-mono tracking-wider uppercase opacity-70 text-center">
          Linux today · macOS in beta · Open source · Runs on Ollama
        </div>
      </>
    ),
  },
};
