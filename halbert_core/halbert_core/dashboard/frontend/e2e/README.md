# End-to-end smoke scripts

Two Playwright-based browser smoke scripts live here. Neither is part of
`npm test` (vitest only collects `src/**`) and neither runs in CI (`FE-16`):
both need a live backend and a running dev server, and `continuity.smoke.mjs`
needs a model actually answering on the other end. `playwright` itself is
deliberately **not** a project dependency — installing it into every
`npm install` for two manual smoke scripts isn't worth the weight.

| Script | Covers |
|---|---|
| `plan-b.smoke.mjs` | Terminal block rendering, responsive layout, accessibility |
| `continuity.smoke.mjs` | A full walk through the continuous-conversation flow against a live model |

## Running one

```sh
# one-time, not saved to package.json:
npm i --no-save playwright && npx playwright install chromium

# terminal 1: backend on :8000 (or HALBERT_API_PORT)
# terminal 2:
cd halbert_core/halbert_core/dashboard/frontend
npm run dev

# terminal 3:
node e2e/plan-b.smoke.mjs                # defaults to http://localhost:5173
node e2e/continuity.smoke.mjs
HALBERT_UI_URL=http://localhost:4173 node e2e/continuity.smoke.mjs
```

Without the `playwright` package installed, `continuity.smoke.mjs` prints the
manual checklist instead and exits 0. Exit code is 0 unless a real UI
regression is found; see each script's own header comment for the full
timeout/env-var contract.

Run these by hand before a release that touches terminal rendering or the
chat/continuity flow. A CI job for either would need a mocked-backend variant
(`plan-b.smoke.mjs`) or a stubbed model response (`continuity.smoke.mjs`) —
neither exists today, so this stays a manual gate.
