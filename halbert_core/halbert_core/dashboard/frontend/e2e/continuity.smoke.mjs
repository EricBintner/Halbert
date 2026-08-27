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
 *
 * Exit code: 0 unless the UI regressed. Lines the model's own choices can
 * decide — whether it ran a command at all — print as [SKIP] and leave the
 * exit code alone, so a red run is always worth investigating.
 *
 * Timeouts: HALBERT_SMOKE_TURN_TIMEOUT_MS (default 180s) covers waiting for a
 * model to answer; HALBERT_SMOKE_SETTLE_TIMEOUT_MS (default 30s) covers
 * everything else — navigation, stored history, rendering.
 */

const BASE = process.argv[2] ?? process.env.HALBERT_UI_URL ?? 'http://localhost:5173'
const TURN_TIMEOUT_MS = Number(process.env.HALBERT_SMOKE_TURN_TIMEOUT_MS ?? 180_000)
// Everything that is not "wait for a model to answer": the navigation, the
// stored history landing, the feed committing. Seconds, not minutes.
const SETTLE_TIMEOUT_MS = Number(process.env.HALBERT_SMOKE_SETTLE_TIMEOUT_MS ?? 30_000)

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

/**
 * A check that could not be made, for a reason that is not a regression —
 * the model choosing to answer from memory rather than running a command.
 * Deliberately does NOT touch the exit code: a red run has to mean the UI
 * broke, otherwise nobody can trust it enough to act on it.
 */
function skip(step, detail = '') {
  console.log(`[SKIP] ${step}${detail ? ` — ${detail}` : ''}`)
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

/**
 * Load (or reload) the surface and wait for the stored conversation to be on
 * screen. Both halves of that are load-bearing.
 *
 * `waitUntil: 'networkidle'` is unusable anywhere on this surface. The
 * engaged shell opens an EventSource on mount — HostShell -> ContextStage ->
 * ProactiveEventsBadge -> useBeingEvents -> `/api/being/events` — and that
 * backend route is an endless generator with a 15s keepalive. One held-open
 * stream keeps the in-flight request count above zero for as long as the page
 * lives, so the idle state never arrives and every navigation would die on
 * the navigation timeout before a single assertion ran.
 *
 * Waiting for the composer is not a substitute: it renders immediately while
 * `useTimeline` is still fetching, and `Timeline` renders nothing at all
 * until its first page has landed. Reading the article count in that window
 * yields 0 for a conversation that has plenty of history, which then makes
 * `sendAndWait(..., before + 1)` return the instant the history lands rather
 * than when the turn finishes — every later assertion would be measured
 * mid-turn.
 *
 * The timeline response is the signal that covers both cases: once it has
 * landed, a conversation with anything stored renders `[role="feed"]` and
 * drops `aria-busy`, and a brand new install renders no feed at all, ever.
 */
async function navigateAndSettle(navigate) {
  const timelinePage = page
    .waitForResponse((res) => res.url().includes('/api/agent/timeline'), {
      timeout: SETTLE_TIMEOUT_MS,
    })
    .catch(() => null)
  await navigate()
  await page.waitForSelector('textarea[placeholder^="Ask Halbert"]', { timeout: SETTLE_TIMEOUT_MS })
  const response = await timelinePage
  const body = response ? await response.json().catch(() => null) : null
  // No body means the request never landed or was not JSON — the backend is
  // not answering, so expect the feed and let the wait below fail loudly
  // rather than walking a conversation that never loaded.
  const expectsFeed = body
    ? (Array.isArray(body.turns) && body.turns.length > 0) || !!body.has_more
    : true
  if (expectsFeed) {
    // React commits the page after the response resolves; the feed only drops
    // aria-busy on that commit, so this is the end of the load, not the wire.
    await page.waitForSelector('[role="feed"][aria-busy="false"]', { timeout: SETTLE_TIMEOUT_MS })
  }
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
  await navigateAndSettle(() =>
    page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: SETTLE_TIMEOUT_MS }),
  )
  log('engaged surface loads', true, BASE)

  log('no conversation dropdown', (await page.getByText('New Conversation').count()) === 0)
  log('no session footer', (await page.getByText(/^Session:/).count()) === 0)

  const before = await articleCount()

  await sendAndWait(MESSAGE_1, before + 1)
  log('turn 1 folded into the timeline', (await articleCount()) === before + 1)
  log('day divider is an h2', (await page.locator('header.thread-divider h2').count()) > 0)
  // Whether a command ran at all is the model's call, not the UI's. Treating
  // "answered from memory" as a failure would make a red run ambiguous, so it
  // is a SKIP: a non-zero exit from this script means the UI regressed.
  const hadTerminal = (await tileOrChip().count()) > 0
  if (hadTerminal) {
    log('turn 1 opened a terminal (tile or chip)', true)
  } else {
    skip(
      'turn 1 opened a terminal (tile or chip)',
      'the model answered without running a command — the tile checks below are skipped, not failed',
    )
  }
  const topic = await page.getByTestId('current-topic').textContent().catch(() => '')
  log('sticky topic label present', !!topic && topic.trim().length > 0, topic ?? '')

  await sendAndWait(MESSAGE_2, before + 2)
  log('turn 2 folded into the timeline', (await articleCount()) === before + 2)
  log('turn 1 still on screen after turn 2', (await page.getByText('uname -a').count()) > 0)
  if (hadTerminal) {
    log('tile from turn 1 survives turn 2', (await tileOrChip().count()) > 0)
  }

  await navigateAndSettle(() =>
    page.reload({ waitUntil: 'domcontentloaded', timeout: SETTLE_TIMEOUT_MS }),
  )
  await page.waitForSelector('[role="feed"] article', { timeout: SETTLE_TIMEOUT_MS })
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
