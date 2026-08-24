/**
 * Copy Variant B: "DDB / Bernbach Telegraphic Minimalist"
 * Voice: Sparse, self-deprecating, razor-sharp 1960s print ad copy.
 * Style: Single-word / short statement hooks ("Lemon.", "I remember.")
 */

export const copyVariantB = {
  id: 'variant-b',
  name: 'DDB Minimalist',

  meta: {
    title: 'Halbert — I’m not feeling well.',
    description: 'The computer that talks back. Local-first host intelligence without cloud disclaimers.',
  },

  masthead: {
    vol: 'VOL. 1',
    issue: 'NO. 1 — AUGUST 2026',
    edition: 'MINIMALIST FOLIO',
    tagline: 'You can call me AI.',
    cta: 'Early Access',
  },

  hero: {
    headline: 'I’m not feeling well.',
    bodyBlocks: [
      'My secondary storage drive logged three read errors this morning at 08:00.',
      'A cloud chatbot wouldn’t know. It doesn’t have drives. It doesn’t have fans. It doesn’t live in your home.',
      'I am your computer. I know my own vitals. And when I need a doctor, I tell you.',
    ],
    tagline: 'Halbert. You can call me AI.',
    formPlaceholder: 'Your email address…',
    submitText: 'Join',
    successMessage: 'Subscribed. Watch your inbox for release notices.',
    badges: ['LOCAL OLLAMA', 'MACOS · LINUX', '100% PRIVATE'],
  },

  spreads: [
    {
      figure: 'FIG. 1',
      kicker: 'SELF-KNOWLEDGE',
      headline: 'I know myself.',
      body: [
        'Most operating systems wait until a volume corrupts to alert you.',
        'I inspect my own sensors, memory pressure, and kernel rings every second.',
        'If I get hot, I let you know before the kernel throttles.',
      ],
      caption: 'Continuous self-monitoring via hwmon & systemd journal.',
    },
    {
      figure: 'FIG. 2',
      kicker: 'REASONING',
      headline: 'I remember.',
      body: [
        'You changed sshd_config last month to block brute-force attempts on port 22.',
        'I logged your reason word for word.',
        'When you look at the diff today, you won’t have to wonder why.',
      ],
      caption: 'Configuration diffs anchored to historical rationale.',
    },
    {
      figure: 'FIG. 3',
      kicker: 'THE INTERFACE',
      headline: 'Speak to me.',
      body: [
        'No terminal commands to memorize. No dashboards to click through.',
        'Just ask. I explain what’s wrong, show the diff, and wait for your approval.',
      ],
      caption: 'Conversational control with atomic dry-run verification.',
    },
  ],

  soul: {
    kicker: 'ETHOS',
    headline: 'Your computer has a memory.\nNow it has a voice.',
    body: [
      'For fifty years, computers have beeped when they broke and stayed silent when they worked.',
      'Halbert gives your host machine an autobiography and a voice.',
      'Not an assistant. The machine itself.',
    ],
  },

  colophon: {
    title: 'Halbert.',
    publisher: 'Published by Eric Bintner. Set in Jost and JetBrains Mono.',
    materials: 'Printed on warm paper stock, 2026.',
    subscribePrompt: 'Join the subscriber list for preview builds:',
    subscribeButton: 'Submit',
    legal: 'Local-first. Zero cloud telemetry. All data remains on the physical host.',
    copyright: '© 2026 Halbert Project.',
  },
};
