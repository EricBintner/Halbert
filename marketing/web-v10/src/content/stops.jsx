import React, { useState } from 'react';
import { ProactiveEventsPlate, VitalsPlate, RationalePlate, KnowledgePlate, IntroOverviewPlate } from './ui';

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

export const Kicker = ({ children, className = '' }) => (
  <div className={`text-[13px] font-mono font-bold tracking-[0.2em] uppercase opacity-80 mb-4 ${className}`}>{children}</div>
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
        className="px-5 py-3 font-bold uppercase tracking-wider bg-[var(--color-stroke)] text-[var(--color-ink-on-stroke)] cursor-pointer shrink-0"
      >
        Get access
      </button>
    </form>
  );
}

export const STOP_CONTENT = {
  intro: {
    canvas: (
      <>
        <Kicker>// Native MCP & host intelligence</Kicker>
        <Headline>
          I am the computer.
          <br />
          And I put the smart in your home.
        </Headline>
        <Body>
          Halbert bridges host management and home automation into one local intelligence. I monitor my own
          hardware, help automate your home, and give your AI tools MCP access to your systems, their configs
          and their hardware. And I run locally.
        </Body>
      </>
    ),
    stroke: (
      <>
        <Kicker>// MEET HALBERT</Kicker>
        <IntroOverviewPlate />
      </>
    ),
  },

  open: {
    stroke: (
      <>
        <Kicker>// Proactive triage</Kicker>
        <Headline>I know what’s wrong and I can help you fix it.</Headline>
        <Body>
          I run on your hardware, not in someone else’s cloud. I read my own sensors, my own logs, my own drives — and
          when something is off, I say so, in plain first person, before it becomes your problem.
        </Body>
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
        <Kicker>// Home & host management</Kicker>
        <Headline>I can turn out the lights for you.</Headline>
      </>
    ),
    stroke: (
      <div className="w-full md:grid md:grid-cols-[minmax(0,40ch)_minmax(0,1fr)] md:gap-10 md:items-start">
        <Body>
          I don’t stop at the edge of the terminal. From dimming the lights when you step away, to validating ZFS pools,
          rotating system journals, or restarting a stalled service — the routine chores are covered. Just ask me.
        </Body>
        <VitalsPlate />
      </div>
    ),
  },

  diagonal: {
    canvas: (
      <>
        <Kicker>// Private by construction</Kicker>
        <Headline size="xl">Local.</Headline>
        <div className="font-display font-normal text-[clamp(1rem,1.5vw,1.4rem)] mt-3">
          &nbsp;{'{or BYOK, whatever you want}'}
        </div>
      </>
    ),
    stroke: (
      <>
        <Body>
          Built to be local and private first. Nothing leaves the machine unless you connect it. Run local LLMs or
          bring your own cloud keys, but importantly sensitive system configs and credentials always require a private
          local model.
        </Body>
        <div className="text-[clamp(0.95rem,1.25vw,1.2rem)] opacity-90 mt-2 mb-3">
          Open source, GPL-3.0
        </div>
        <Kicker>Linux · Mac · Win · Home Assistant</Kicker>
      </>
    ),
  },

  rise: {
    canvas: (
      <>
        <Kicker>// Intent, kept next to the change</Kicker>
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
        <Kicker>// Grounded, not guessed</Kicker>
        <Headline>I know over 20,000 system references and docs.</Headline>
        <Body>
          Man pages, the Arch Wiki, Homebrew formulae, TLDR pages — indexed on this disk and searched before I answer.
          No invented flags. When I cite a source, you can open it.
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
        <Kicker>// Distributed architecture</Kicker>
        <Headline>Independent nodes. Shared&nbsp;intelligence.</Headline>
        <Body>
          Run local models on your desktop, monitor system vitals from your terminal, and keep your decision history
          synchronized everywhere. A host intelligence that scales across your own hardware.
        </Body>
      </>
    ),
    stroke: (
      <div className="pt-8 sm:pt-14 md:pt-20 flex flex-col items-center">
        <div className="font-display italic text-[clamp(1.25rem,2.4vw,2.25rem)]">“Your machines, thinking together.”</div>
        <Kicker className="mt-3">Shared local models · Peer routing</Kicker>
      </div>
    ),
  },

  reveal: {
    above: (
      <>
        <Kicker>// MEET HALBERT.</Kicker>
        <Headline size="md">Hi, I’m your computer.</Headline>
      </>
    ),
    below: (
      <>
        <EarlyAccessForm />
        <div className="mt-4 text-[11px] font-mono tracking-wider uppercase opacity-70 text-center">
          Linux / macOS · Open source · Any LLM or BYOK
        </div>
        <div className="mt-3 flex items-center justify-center space-x-3 text-[10px] font-mono opacity-50 uppercase tracking-widest">
          <a href="/privacy.html" className="hover:opacity-100 hover:underline">Privacy</a>
          <span>·</span>
          <a href="/terms.html" className="hover:opacity-100 hover:underline">Terms</a>
          <span>·</span>
          <a href="https://github.com/EricBintner/Halbert" target="_blank" rel="noopener noreferrer" className="hover:opacity-100 hover:underline">GPL-3.0</a>
        </div>
      </>
    ),
  },
};
