import React, { useLayoutEffect, useRef, useState } from 'react';
import { ProactiveEventsPlate, VitalsPlate, RationalePlate, KnowledgePlate, VoiceModePlate } from './ui';

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

// max-sm variants compress the copy rhythm on phones only: the top-field copy
// is bottom-anchored to the colour boundary (see LayoutStage), so a stack too
// tall for half a phone screen rides up behind the folio bar. Tighter leading,
// smaller gaps and a slightly wider measure keep it inside the field — desktop
// (>=640px) is untouched.
export const Kicker = ({ children, className = '' }) => (
  <div className={`text-[13px] font-mono font-bold tracking-[0.2em] uppercase opacity-80 mb-4 max-sm:mb-2 max-sm:tracking-[0.12em] ${className}`}>{children}</div>
);

export const Headline = ({
  children,
  size = 'lg',
  weight = 'font-black',
  leading = size === 'sm' ? 'leading-snug' : 'leading-[0.95]',
  className = '',
  style,
  ref,
}) => {
  const cls = {
    xl: 'text-[clamp(3rem,9vw,9rem)]',
    lg: 'text-[clamp(2.25rem,5.5vw,5.5rem)]',
    md: 'text-[clamp(1.75rem,3.8vw,3.75rem)]',
    sm: 'text-[clamp(1.25rem,2.2vw,1.8em)] lg:text-[1.8em]',
  }[size] || '';
  // Phones: the 36px floor wraps long lines to 3 each in a half-width column,
  // blowing the top field's budget. The phone step carries a vh term so short
  // viewports (SE-class heights, Safari's insecure-connection banner stealing
  // height) scale the type down with the field. Tall phones have room to
  // spare, so both the preferred term and the ceiling gain a width-scaled
  // bonus — gated by max(0px, min(w-term, 100vh - 812px)), which is exactly
  // zero on any viewport up to 812px tall: SE, banner-compromised and
  // standard iPhone sizes keep the collision-safe sizes verified for them, by
  // construction; Pro/Pro Max sizes grow with width (1.2–2vw) as well as
  // height. No multiplication — max/min/addition only, valid CSS calc.
  // md runs only on the full-mark reveal stop, whose band is full-width and
  // centered — not a half column — so it carries more size than lg/xl.
  // >=640px wide is untouched entirely.
  const phone = {
    xl: 'max-sm:text-[clamp(1.6rem,calc(4.2vh+max(0px,min(1.2vw,100vh_-_812px))),calc(2.4rem+max(0px,min(1.5vw,100vh_-_812px))))]',
    lg: 'max-sm:text-[clamp(1.3rem,calc(3.7vh+max(0px,min(1vw,100vh_-_812px))),calc(1.9rem+max(0px,min(1.3vw,100vh_-_812px))))]',
    md: 'max-sm:text-[clamp(1.25rem,calc(4vh+max(0px,min(0.45vw,100vh_-_812px))),calc(1.85rem+max(0px,min(0.5vw,100vh_-_812px))))]',
    sm: 'max-sm:text-[clamp(1.05rem,calc(2.8vh+max(0px,min(0.8vw,100vh_-_812px))),calc(1.35rem+max(0px,min(1vw,100vh_-_812px))))]',
  }[size] || '';
  return <h2 ref={ref} className={`font-display tracking-tight ${weight} ${leading} ${cls} ${phone} ${className}`} style={style}>{children}</h2>;
};

export const Body = ({ children }) => (
  <p className="text-[clamp(0.95rem,1.25vw,1.2rem)] leading-relaxed max-w-[38ch] mt-5 opacity-90 max-sm:mt-3 max-sm:text-[0.9rem] max-sm:leading-snug max-sm:max-w-[44ch]">{children}</p>
);

export const Cue = ({ children }) => (
  <div className="mt-8 text-[11px] font-mono font-bold tracking-widest uppercase opacity-70">{children}</div>
);

/**
 * A headline sized by measurement: on phones the line is scaled so it fills
 * the slot's width exactly — the smallest screens get a full-width line,
 * wider phones get a proportionally bigger one, and wrapping or overflow is
 * impossible by construction (the size comes from the text's own measured
 * extent at the authored phone size, not a vw guess). >=640px keeps the
 * authored clamp sizes. The scale rides a CSS variable; the observer
 * watches the SLOT, so a font-size change never re-triggers the fit (the
 * element's own resize can't feed back into the measurement).
 */
function HeadlineFit({ children, ...rest }) {
  const ref = useRef(null);
  const [scale, setScale] = useState(1);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const slot = el.closest('[data-slot]');
    if (!slot) return;
    const fit = () => {
      // Portrait phones only (<640px wide). Desktop/tablet keep authored sizes.
      if (window.innerWidth >= 640) {
        setScale(1);
        return;
      }
      // Force the authored size for the measurement: the !important class
      // beats the inline variable without mutating what React owns. A block
      // h2 reports its slot width, so measure the text through a Range.
      el.classList.add('headline-fitting');
      const range = document.createRange();
      range.selectNodeContents(el);
      const natural = range.getBoundingClientRect().width;
      el.classList.remove('headline-fitting');
      const target = slot.clientWidth;
      if (natural > 0 && target > 0) {
        // A hair under fill so tracking's last letter-space can't tip a wrap.
        setScale(Math.min(1.12, (0.98 * target) / natural));
      }
    };
    fit();
    // Watch the slot, not the element: font-size changes the element's box,
    // which would re-trigger the fit and oscillate. The slot's width changes
    // only with the viewport.
    const ro = new ResizeObserver(fit);
    ro.observe(slot);
    return () => ro.disconnect();
  }, []);

  return (
    <Headline
      ref={ref}
      {...rest}
      className={`headline-fit ${rest.className ?? ''}`}
      style={{ ...(rest.style ?? {}), ['--headline-fit']: String(scale) }}
    >
      {children}
    </Headline>
  );
}

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
      <div className="stage-enter">
        <Kicker>// Native MCP & host intelligence</Kicker>
        <HeadlineFit>I am the computer.</HeadlineFit>
        <Headline size="sm" weight="font-semibold" className="mt-[0.05em]" style={{ marginTop: '0.05em' }}>
          And I put the smart in your home.
        </Headline>
        <Body>
          Halbert bridges host management and home automation into one local intelligence. I monitor my own
          hardware, help automate your home, and give your AI tools MCP access to your systems, their configs
          and their hardware. And I run locally.
        </Body>
      </div>
    ),
    stroke: (
      <div className="stage-enter stage-enter--late w-full">
        <VoiceModePlate />
      </div>
    ),
  },

  open: {
    stroke: (
      <>
        <Kicker>// Proactive triage</Kicker>
        <Headline>I know what’s up and I can fix it.</Headline>
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
        <Kicker>Linux · Mac · Home Assistant</Kicker>
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
        <Headline>I know thousands of system references and docs.</Headline>
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
        <Headline>Nodes of shared&nbsp;intelligence.</Headline>
        <Body>
          I don’t live in a single box. A quiet server in your closet can offload heavy reasoning to your desktop GPU,
          coordinate tasks across paired peers, and keep one continuous memory wherever you sit down.
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
          Linux / macOS / Home Assistant · Any LLM or BYOK
        </div>
        <div className="mt-3 flex items-center justify-center space-x-3 text-[10px] font-mono opacity-50 uppercase tracking-widest">
          <a href="/privacy.html" className="hover:opacity-100 hover:underline">Privacy</a>
          <span>·</span>
          <a href="/terms.html" className="hover:opacity-100 hover:underline">Terms</a>
          <span>·</span>
          <a href="https://github.com/EricBintner/Halbert" target="_blank" rel="noopener noreferrer" className="hover:opacity-100 hover:underline">Open Source GPL-3.0</a>
        </div>
      </>
    ),
  },
};
