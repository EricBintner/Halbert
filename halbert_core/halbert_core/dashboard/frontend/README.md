# Halbert Dashboard Frontend

The desktop UI for Halbert — a sentient OS assistant that monitors, diagnoses,
and configures your machine. Built as a Tauri 2 shell wrapping a React SPA that
talks to a FastAPI backend over REST and SSE.

## Tech Stack

- **Tauri 2** — native desktop shell (Rust core + webview), system tray, IPC
- **React 18** + **TypeScript 5.6** — single-page application
- **Vite 5** — dev server and production bundler
- **Tailwind CSS 3** — utility-first styling driven by shared design tokens
- **@halbert/model-picker** — headless model picker (local discovery, BYOK, tier routing)
- **@halbert/design-system** — Olivetti Vermilion & Bone component library
- **@xterm/xterm** — live in-browser terminals
- **Vitest** + **@testing-library/react** — unit and component tests

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Tauri 2 Shell                       │
│  ┌───────────────────────────────────────────────┐  │
│  │            React SPA (this package)            │  │
│  │  ┌─────────────┐  ┌────────────────────────┐  │  │
│  │  │ @halbert/   │  │ @halbert/              │  │  │
│  │  │ model-picker│  │ design-system          │  │  │
│  │  │ (headless)  │  │ (Button, Select, ...)  │  │  │
│  │  └──────┬──────┘  └────────────────────────┘  │  │
│  │         │ modelPickerTransport                │  │
│  └─────────┼─────────────────────────────────────┘  │
│            │ REST / SSE                              │
└────────────┼────────────────────────────────────────┘
             ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI Backend (port 8000)             │
│  /llm/config  /api/llm/discover  /api/agent/stream  │
└─────────────────────────────────────────────────────┘
```

The dashboard consumes two workspace packages:

- **`@halbert/model-picker`** — headless model selection (local engine
  discovery, BYOK cloud endpoints, role-based tier assignment, per-turn
  pinning). The dashboard provides `modelPickerTransport.ts` as the single
  adapter between the package's transport interface and Halbert's backend
  routes. The package itself has zero I/O and zero hardcoded class names —
  it is fully headless and style-agnostic.

- **`@halbert/design-system`** — Olivetti Vermilion & Bone primitives
  (Button, Select, StatusBadge, Input, ParametricSlider, HalbertMark) and
  surfaces (AppWindow, MetricCard). Plain CSS backed by shared design
  tokens — no Tailwind in library source, so it works under both Tailwind
  v3 and v4 hosts. Styles are imported once in `src/index.css`.

## Development

### Prerequisites

- **Node.js 22 LTS** (`nvm use 22`)
- **Rust / Cargo** (for Tauri desktop builds)
- **Halbert backend** running on `localhost:8000`

### Commands

```bash
# Install dependencies (from repo root — npm workspaces)
npm install

# Browser-only dev server (http://localhost:5173, proxies API to :8000)
npm run dev

# Tauri desktop dev (launches native window + dev server + backend proxy)
npm run tauri:dev

# Production build (tsc + vite build → dist/)
npm run build

# Tauri desktop production build (bundles native .app/.deb/.AppImage)
npm run tauri:build

# Run tests
npm test

# Type-check only
npx tsc --noEmit
```

### API Port Override

The dev server proxies `/api`, `/global`, `/llm`, `/embedding`, `/compute`,
and `/ws` to `localhost:8000` by default. Set `HALBERT_API_PORT` to target a
different backend:

```bash
HALBERT_API_PORT=8001 npm run dev
```

## In-Chat Model Picker

The composer footer hosts a `ChatModelPill` backed by `@halbert/model-picker`.
It shows the model that will answer the next turn and supports:

- **Click** — opens a searchable popover with all configured models
- **`/model`** — opens the picker popover
- **`/model <query>`** — pins to the unique matching model, or opens the
  popover with the query pre-filled if multiple match
- **`/model specialist`** / **`/model vision`** — pin to a tier
- **`/model auto`** — clear the pin, return to automatic routing
- **`/model status`** — show current model, provider, tier, and context window

The pin is ephemeral — it governs only the current conversation and is never
written to the stored configuration. The same picker instance drives both the
pill display and the `/model` command, so they can never disagree.

## Live Terminals

The Terminal page and inline agent terminals use `@xterm/xterm` with
`@xterm/addon-fit` and `@xterm/addon-web-links`. Terminal output streams over
WebSocket (`/ws`) and SSE (`/api/agent/stream`), with command execution
proxied through the backend.

## Project Structure

```
src/
├── components/
│   ├── agent/          # Chat, state machine, tools, timeline
│   ├── audio/          # Auditory cortex UI (speaker profiles, aura)
│   ├── fleet/          # Federated multi-node cockpit
│   ├── legal/          # Legal compliance UI (attribution, licenses)
│   ├── llm/            # Model picker pill, settings, quick setup
│   ├── modules/        # Structured agent module renderers
│   ├── shell/          # Layout, live regions, sidebar
│   ├── ui/             # shadcn/ui primitives
│   └── prep-primitives/  # Local primitives (SearchableSelect, Toggle, ...)
├── pages/              # 17 route pages (Dashboard, Storage, GPU, ...)
├── hooks/              # useAgentStream, useTimeline, useHostIdentity, ...
├── lib/                # API client, transport, slash commands, utils
├── types/              # Shared TypeScript types
├── index.css           # Tailwind + shared tokens + design-system styles
└── main.tsx            # App entry
```

## Testing

```bash
# Frontend tests (Vitest + jsdom)
npm test

# Watch mode
npm run test:watch
```

Tests cover the model picker transport, slash command parser, agent stream
hook, terminal tile, and component-level tests for the chat pill, state
badge, and timeline.
