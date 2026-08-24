/**
 * Copy Variant A: "The Direct / Embodied Computer"
 * Voice: Unsettlingly direct, matter-of-fact self-reporting in first person.
 * Style: DDB / 1960s telegraphic print advertising with period-ending headlines.
 */

export const copyVariantA = {
  id: 'variant-a',
  name: 'Direct Embodied',
  
  meta: {
    title: 'Halbert — I know what’s wrong with me.',
    description: 'A local-first computer that talks back. Grounded in real telemetry, configuration history, and diagnostic truth.',
  },

  masthead: {
    vol: 'VOL. 1',
    issue: 'NO. 1 — AUGUST 2026',
    edition: 'FIRST EDITION',
    tagline: 'You can call me AI.',
    cta: 'Get Early Access',
  },

  hero: {
    headline: 'I know what’s wrong with me.',
    bodyBlocks: [
      'I read my own hardware sensors, system logs, and configuration history.',
      'When something breaks, I don’t give you a dashboard to decode. I tell you — in plain language, with evidence.',
      'No cloud. No disclaimers. I run locally on your machine because I am your machine.',
    ],
    tagline: 'Halbert. You can call me AI.',
    formPlaceholder: 'Enter your email for early access…',
    submitText: 'Subscribe',
    successMessage: 'You are on the list. We will dispatch the build to your inbox.',
    badges: ['100% LOCAL (OLLAMA)', 'MACOS & LINUX', 'ZERO CLOUD TELEMETRY'],
  },

  spreads: [
    {
      figure: 'FIG. 1',
      kicker: 'PHYSIOLOGICAL SELF-AWARENESS',
      headline: 'I can feel my own temperature.',
      body: [
        'Generic AI assistants hallucinate system facts because they live in a data center thousands of miles away.',
        'I live here. I monitor my own CPU thermal zones, load averages, and drive wear in real time.',
        'When I tell you /dev/sda1 is logging read errors, it is not a hypothetical. It is my body.',
      ],
      caption: 'Continuous hwmon & kernel sensor telemetry loop.',
    },
    {
      figure: 'FIG. 2',
      kicker: 'INSTITUTIONAL MEMORY',
      headline: 'I remember why you changed that.',
      body: [
        'Why did you move SSH to port 2222 three months ago? Why is compression turned off on the data volume?',
        'I store the rationale alongside the configuration diff.',
        'You never have to guess who edited /etc/fstab or why. I remember every command you ever gave me.',
      ],
      caption: 'AST-aware configuration diff with historical user rationale.',
    },
    {
      figure: 'FIG. 3',
      kicker: 'CONVERSATIONAL SPRAY & PRAY IS OVER',
      headline: 'Don’t guess. Ask me.',
      body: [
        'You do not need to memorize 400 flags for journalctl or write fragile grep pipelines.',
        'Speak to me like a senior systems colleague. I check my own state, formulate safe dry-runs, and ask your permission before touching anything.',
      ],
      caption: 'Single conversation container with dynamic diagnostic proof.',
    },
  ],

  soul: {
    kicker: 'THE CENTRAL THESIS',
    headline: 'I am not an assistant.\nI am the machine.',
    body: [
      'When you ask a generic AI "How are you doing?", it tells you it is a language model without physical form.',
      'When you ask me, I tell you I’ve been up 42 days, my load is light, and my secondary drive needs attention.',
      'The most helpful colleague you have happens to be your computer.',
    ],
  },

  colophon: {
    title: 'Halbert.',
    publisher: 'Published by Eric Bintner. Set in Jost and JetBrains Mono.',
    materials: 'Printed on warm archival paper, 2026. Open source core.',
    subscribePrompt: 'To receive dispatch notes and preview builds:',
    subscribeButton: 'Submit',
    legal: 'No cloud tracking. 100% XDG Base Directory compliant. All telemetry stays on your host.',
    copyright: '© 2026 Halbert Project. All rights reserved.',
  },
};
