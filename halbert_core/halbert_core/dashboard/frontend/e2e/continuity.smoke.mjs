#!/usr/bin/env node
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Continuity smoke — a browser walk through the continuous conversation
 * against a LIVE backend and dev server. Deliberately not part of `npm test`
 * (vitest only collects src/**) and never run in CI: it needs a model
 * answering on the other end.
 *
 * Run:
 *   # terminal 1: backend on :8000 (or HALBERT_API_PORT), then
 *   cd halbert_core/halbert_core/dashboard/frontend && npm run dev
 *   # terminal 2:
 *   node e2e/continuity.smoke.mjs                # http://localhost:5173
 *   HALBERT_UI_URL=http://localhost:4173 node e2e/continuity.smoke.mjs
 *
 * Needs the `playwright` package, which is NOT a project dependency:
 *   npm i --no-save playwright && npx playwright install chromium
 * Without it the script prints the manual checklist and exits 0.
 */

const BASE = process.argv[2] ?? process.env.HALBERT_UI_URL ?? 'http://localhost:5173'
const TURN_TIMEOUT_MS = Number(process.env.HALBERT_SMOKE_TURN_TIMEOUT_MS ?? 180_000)

const MESSAGE_1 = 'Please run `uname -a` and tell me the kernel version.'
const MESSAGE_2 = 'Unrelated: what is 2 + 2?'

const MANUAL_CHECKLIST = `
Manual continuity check (playwright not installed):

  1. Start the backend and \`npm run dev\`; open ${BASE} in a browser.
  2. There is no conversation dropdown, no "New Conversation" button and no
     "Session: …" line under the composer.
  3. Send: ${MESSAGE_1}
     - a live block appears under your bubble; when the command runs, a
       terminal tile (or an "in dock" chip) appears inside it;
     - when the reply finishes, the turn moves into the timeline under a
       "Today" divider (<h2>) and the sticky topic label shows a title.
  4. Send: ${MESSAGE_2}
     - the first turn is still on screen above the new one;
     - its terminal tile is still there (or a "terminal · ended" chip).
  5. Reload the page.
     - both turns are back, under a "Today" divider, in order;
     - the first turn shows a terminal tile or a "terminal · ended" chip;
     - the sticky topic label is back.
  6. Send: "did that kernel check work?"
     - a "pulled in: …" chip may appear in the context bar and the live
       region (VoiceOver/NVDA) says "Pulled in earlier work: …" — only when
       the earlier subject had already been paused. Not a failure if absent.
  7. Tab to a live tile, press Ctrl+\` — focus leaves the terminal.
  8. Click the "pulled in: …" chip (when one appeared): the timeline jumps
     to the recalled subject's last turn and a "Back to latest" control
     appears at the bottom; hovering the chip shows "matched: …".
  9. On any stored turn, "Forget this": both bubbles read
     "[redacted by admin]" and the turn keeps its place.
 10. Ask for something that needs confirmation (a HIGH-risk command): the
     screen reader says "Waiting for your approval" at once (the alert
     region), and the dialog opens.
`

function log(step, ok, detail = '') {
  const mark = ok ? 'PASS' : 'FAIL'
  console.log(`[${mark}] ${step}${detail ? ` — ${detail}` : ''}`)
  if (!ok) process.exitCode = 1
}

let chromium
try {
  ;({ chromium } = await import('playwright'))
} catch {
  console.log(MANUAL_CHECKLIST)
  process.exit(0)
}

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ reducedMotion: 'reduce' })
await context.addInitScript(() => {
  // The engaged surface is the default, but pin it so a stored preference
  // on this machine cannot land the smoke on the dashboard.
  window.localStorage.setItem('halbert:shell-mode', 'engaged')
})
const page = await context.newPage()

const consoleErrors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})

const composer = () => page.locator('textarea[placeholder^="Ask Halbert"], textarea[placeholder^="Type to queue"]').first()
const articles = () => page.locator('[role="feed"] article')
const tileOrChip = () => page.locator('[data-terminal-origin], [data-session-id]')

async function articleCount() {
  return (await page.locator('[role="feed"]').count()) === 0 ? 0 : articles().count()
}

async function sendAndWait(text, expectedArticles) {
  await composer().fill(text)
  await composer().press('Enter')
  // The turn is over when it has been folded into the timeline: the article
  // count reaches the expected value and the composer is idle again.
  await page.waitForFunction(
    (n) => document.querySelectorAll('[role="feed"] article').length >= n,
    expectedArticles,
    { timeout: TURN_TIMEOUT_MS },
  )
  await page.waitForSelector('textarea[placeholder^="Ask Halbert"]', { timeout: TURN_TIMEOUT_MS })
}

try {
  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.waitForSelector('textarea[placeholder^="Ask Halbert"]', { timeout: 30_000 })
  log('engaged surface loads', true, BASE)

  log('no conversation dropdown', (await page.getByText('New Conversation').count()) === 0)
  log('no session footer', (await page.getByText(/^Session:/).count()) === 0)

  const before = await articleCount()

  await sendAndWait(MESSAGE_1, before + 1)
  log('turn 1 folded into the timeline', (await articleCount()) === before + 1)
  log('day divider is an h2', (await page.locator('header.thread-divider h2').count()) > 0)
  const hadTerminal = (await tileOrChip().count()) > 0
  log('turn 1 opened a terminal (tile or chip)', hadTerminal, hadTerminal ? '' : 'model did not run a command — the reload check below is skipped for the tile')
  const topic = await page.getByTestId('current-topic').textContent().catch(() => '')
  log('sticky topic label present', !!topic && topic.trim().length > 0, topic ?? '')

  await sendAndWait(MESSAGE_2, before + 2)
  log('turn 2 folded into the timeline', (await articleCount()) === before + 2)
  log('turn 1 still on screen after turn 2', (await page.getByText('uname -a').count()) > 0)
  if (hadTerminal) {
    log('tile from turn 1 survives turn 2', (await tileOrChip().count()) > 0)
  }

  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForSelector('[role="feed"] article', { timeout: 30_000 })
  const after = await articleCount()
  log('both turns are back after reload', after >= before + 2, `${after} articles`)
  log('turn 1 text persisted', (await page.getByText('uname -a').count()) > 0)
  log('turn 2 text persisted', (await page.getByText('2 + 2').count()) > 0)
  if (hadTerminal) {
    const chip = await page.getByText('terminal · ended').count()
    const tile = await page.locator('[data-terminal-origin]').count()
    log('terminal from turn 1 is a tile or an ended chip after reload', chip + tile > 0)
  }
  log('sticky topic label back after reload', (await page.getByTestId('current-topic').count()) > 0)
  log('polite live region exists', (await page.locator('[role="status"][aria-live="polite"]').count()) === 1)
  log('assertive alert region exists', (await page.locator('[role="alert"][aria-live="assertive"]').count()) === 1)

  log('no console errors', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '))
} catch (err) {
  log('smoke aborted', false, err instanceof Error ? err.message : String(err))
} finally {
  await browser.close()
}
