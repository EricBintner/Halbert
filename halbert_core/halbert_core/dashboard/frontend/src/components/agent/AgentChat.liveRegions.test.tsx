// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The conversation spine declares no live region of its own.
 *
 * `lib/announce.ts` states the rule it exists to serve: "a live region only
 * works when there is exactly one of each kind". The shell owns that one
 * (`LiveRegion.tsx`, mounted by HostShell, whose own test pins the count at 1).
 *
 * AgentChat was declaring two more, each with `role="status"` — an implicit
 * polite region — on elements that mount and unmount: the "could not load the
 * stored conversation" banner, and each `/model` answer. Two defects in one:
 * a second and third polite region competing with the shell's, and an
 * announcement that is unreliable even on its own terms, because a region
 * inserted into the DOM with its text already in it is not what a screen
 * reader watches for. What it watches is a region that was already there
 * changing — which is exactly what `announce()` does.
 *
 * These tests pin the seam in both directions: nothing here declares a region,
 * and the sentences still reach the one that exists.
 */
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { AgentChat } from './AgentChat'
import { LiveRegion } from '../shell/LiveRegion'
import { subscribeAnnouncements } from '../../lib/announce'

vi.mock('./TerminalTile', () => ({
  TerminalTile: ({ session }: { session: { id: string } }) => <div data-testid="live-tile">{session.id}</div>,
}))

/** Every polite live region in the rendered tree, however it was declared. */
function politeRegions(container: HTMLElement) {
  return container.querySelectorAll('[role="status"], [aria-live="polite"]')
}

/** Collects what reaches the shell's regions while a test runs. */
function heard() {
  const said: string[] = []
  const stop = subscribeAnnouncements((text) => said.push(text))
  return { said, stop }
}

const EMPTY_PAGE = { has_more: false, current_thread: null, turns: [] }

describe('AgentChat leaves the live regions to the shell', () => {
  let listener: { said: string[]; stop: () => void }

  beforeEach(() => {
    listener = heard()
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
  })

  afterEach(() => {
    listener.stop()
    vi.unstubAllGlobals()
  })

  it('says the conversation could not be loaded without declaring a region to say it in', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503, text: async () => '', json: async () => ({}) }),
    )
    const { container } = render(<AgentChat />)

    // The banner is still on screen: this is the admin's only way back.
    expect(await screen.findByText('Could not load the stored conversation')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()

    // And it is said out loud — once, through the shell's region.
    await waitFor(() =>
      expect(listener.said).toContain('Could not load the stored conversation'),
    )
    expect(
      listener.said.filter((s) => s === 'Could not load the stored conversation'),
    ).toHaveLength(1)

    expect(politeRegions(container)).toHaveLength(0)
  })

  it('answers /model in the stream without declaring a region either', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve(
          String(url).includes('/api/agent/timeline')
            ? { ok: true, status: 200, text: async () => '', json: async () => EMPTY_PAGE }
            : { ok: false, status: 503, text: async () => '', json: async () => ({}) },
        ),
      ),
    )
    const { container } = render(<AgentChat />)

    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)
    // `/model` on its own just opens the popover; `/model auto` is the shortest
    // form that actually answers in the stream.
    await userEvent.type(composer, '/model auto{Enter}')

    // The answer is a note in the stream, and it is spoken by the shell.
    expect(await screen.findByText('Back to automatic routing.')).toBeInTheDocument()
    await waitFor(() => expect(listener.said).toContain('Back to automatic routing.'))
    expect(politeRegions(container)).toHaveLength(0)
  })
})

describe('AgentChat says the load failed again when it fails again', () => {
  let listener: { said: string[]; stop: () => void }

  beforeEach(() => {
    listener = heard()
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 503, text: async () => '', json: async () => ({}) }),
    )
  })

  afterEach(() => {
    listener.stop()
    vi.unstubAllGlobals()
  })

  const failures = (said: string[]) =>
    said.filter((s) => s === 'Could not load the stored conversation')

  it('announces a Try again that fails, not only the first failure', async () => {
    // "Try again" is the admin's only way back from a backend that was
    // restarting, and pressing it is the moment they are waiting to be told
    // something. A `loadFailed` that is set once and thereafter only ever
    // cleared is not a transition the second time, so an effect keyed on it
    // says nothing from the second failure onward and a screen-reader user
    // is left with a button that appears to do nothing at all. Both halves
    // have to hold: the hook makes every attempt a transition, and this is
    // the component half that speaks on it.
    render(<AgentChat />)
    const retry = await screen.findByRole('button', { name: 'Try again' })
    await waitFor(() => expect(failures(listener.said)).toHaveLength(1))

    await userEvent.click(retry)

    await waitFor(() => expect(failures(listener.said)).toHaveLength(2))
    // And it says only that. A retry that reported success as well would put
    // two contradictory sentences into the same region, in the same breath,
    // over a conversation that is still not there.
    expect(listener.said).not.toContain('Conversation loaded')
  })

  it('keeps the notice — and the focused button — up while its own retry runs', async () => {
    // Every attempt clears `loadFailed` before it asks, which is what makes a
    // second failure audible. Rendering the notice on that flag alone then
    // tore it down the instant the admin pressed its button: the button they
    // were on stopped existing, focus fell to the body, and a screen-reader
    // user was left in an empty conversation with no way back and nothing
    // said. The notice has to outlive the attempt it started.
    let failRetry: (() => void) | undefined
    let asked = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (String(url).includes('/api/agent/timeline')) {
          asked += 1
          if (asked > 1) {
            // Held open so the assertions below run mid-flight.
            return new Promise((_resolve, reject) => {
              failRetry = () => reject(new Error('still restarting'))
            })
          }
        }
        return Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) })
      }),
    )
    render(<AgentChat />)
    const retry = await screen.findByRole('button', { name: 'Try again' })
    await waitFor(() => expect(failures(listener.said)).toHaveLength(1))

    await userEvent.click(retry)
    await waitFor(() => expect(retry).toHaveTextContent('Trying…'))

    expect(retry).toBeInTheDocument()
    expect(retry).toHaveFocus()
    expect(screen.getByText('Could not load the stored conversation')).toBeInTheDocument()

    // And when the attempt does fail, it is said again and the button comes
    // back — still the same element, still where the admin left it.
    await act(async () => {
      failRetry?.()
      await Promise.resolve()
    })
    await waitFor(() => expect(retry).toHaveTextContent('Try again'))
    await waitFor(() => expect(failures(listener.said)).toHaveLength(2))
  })

  it('says so when the retry works, not only when it fails', async () => {
    // The other half of the same button. A failure is announced on the
    // transition into `loadFailed`; a success changes nothing a screen reader
    // reads out — the page quietly fills with turns and the notice quietly
    // disappears. So the admin who could not see the screen heard the
    // failure, pressed the button, and then heard nothing at all, with no way
    // to tell a conversation that had come back from one that had not.
    let asked = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (String(url).includes('/api/agent/timeline')) {
          asked += 1
          // The backend finishes restarting between the two attempts.
          if (asked > 1) {
            return Promise.resolve({
              ok: true, status: 200, text: async () => '', json: async () => EMPTY_PAGE,
            })
          }
        }
        return Promise.resolve({ ok: false, status: 503, text: async () => '', json: async () => ({}) })
      }),
    )
    render(<AgentChat />)
    const retry = await screen.findByRole('button', { name: 'Try again' })
    await waitFor(() => expect(failures(listener.said)).toHaveLength(1))
    expect(listener.said).not.toContain('Conversation loaded')

    await userEvent.click(retry)

    // Heard: the conversation is back. And the failure was not repeated —
    // this attempt did not fail.
    await waitFor(() => expect(listener.said).toContain('Conversation loaded'))
    expect(failures(listener.said)).toHaveLength(1)
    // And the notice it came from is gone, rather than left contradicting it.
    await waitFor(() =>
      expect(screen.queryByText('Could not load the stored conversation')).not.toBeInTheDocument(),
    )
  })
})


/**
 * The seam the subscriber-level tests above cannot see.
 *
 * `subscribeAnnouncements` proves a sentence was handed to the announcer.
 * What a screen reader watches is the region itself, and the region is
 * downstream of that: it used to keep only the latest sentence, so of the two
 * every `/model` command produces — the note in the stream, then the pill's
 * switch announcement in the same commit — the first never arrived, and what
 * was read out contradicted what was on screen. These render the real region
 * and read what it actually held.
 */
const ENDPOINT = {
  id: 'ep1', name: 'Local', provider: 'ollama',
  url: 'http://localhost:11434', api_key: '',
}

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

/**
 * The empty-state greeting reads host identity on mount and throws on a
 * partial shape, taking the whole component — and the region under test —
 * down with it.
 */
const IDENTITY = {
  display_name: 'Test-Host',
  hostname: 'test-host.local',
  os: { name: 'macOS', version: '26.5.1', pretty: 'macOS 26.5.1', platform: 'Darwin', kernel: '25.5.0', arch: 'arm64' },
  uptime: { seconds: 86400, human: '1 day', boot_time: '' },
  cpu: { cores: 8, physical_cores: 8, percent: 12, temperature: null },
  memory: { total_gb: 32, used_gb: 8, percent: 25 },
  storage: { pools: [], healthy: 0, total: 0 },
  load_average: { '1min': 1, '5min': 1, '15min': 1 },
  all_healthy: true,
  first_person: 'I am Test-Host.',
  timestamp: '',
}

function routeWithModels() {
  return vi.fn(async (url: string) => {
    const u = String(url)
    if (u.includes('/api/identity')) return jsonResponse(IDENTITY)
    if (u.includes('/api/agent/timeline')) {
      return { ok: true, status: 200, text: async () => '', json: async () => EMPTY_PAGE } as Response
    }
    if (u.includes('/llm/config')) {
      return jsonResponse({ data: {
        llm_config: {
          saved_endpoints: [ENDPOINT],
          chat_model: { enabled: true, endpoint_id: 'ep1', model: 'model-alpha' },
          specialist_model: { enabled: false, endpoint_id: '', model: '' },
          vision_model: { enabled: false, endpoint_id: '', model: '' },
        },
        chat_capable_providers: ['ollama'],
      } })
    }
    if (u.includes('/api/llm/discover')) {
      return jsonResponse({ data: {
        ollama: { running: true, url: ENDPOINT.url, version: '1.0', models: ['model-alpha', 'model-beta'] },
        lm_studio: { running: false, url: 'http://localhost:1234', models: [] },
      } })
    }
    if (u.includes('proxy/models')) {
      return jsonResponse({ data: {
        models: ['model-alpha', 'model-beta'],
        model_details: [{ name: 'model-alpha' }, { name: 'model-beta' }],
      } })
    }
    return jsonResponse({ data: {} })
  })
}

/** Every sentence the region actually held, in order, as a reader would see it. */
function transcriptOf(region: HTMLElement) {
  const said: string[] = []
  const observer = new MutationObserver(() => {
    const text = region.textContent ?? ''
    if (text && text !== said[said.length - 1]) said.push(text)
  })
  observer.observe(region, { childList: true, characterData: true, subtree: true })
  return { said, stop: () => observer.disconnect() }
}

describe('AgentChat /model in the region a screen reader watches', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
    HTMLCanvasElement.prototype.getContext = vi.fn() as never
    fetchMock = routeWithModels()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => vi.unstubAllGlobals())

  it('speaks the answer in the stream as well as the pill’s switch', async () => {
    render(<><LiveRegion /><AgentChat /></>)
    await screen.findByRole('combobox')
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([u]) => String(u).includes('proxy/models'))).toBe(true),
    )

    const transcript = transcriptOf(screen.getByRole('status'))
    const composer = await screen.findByPlaceholderText(/^Ask Halbert/)
    await userEvent.type(composer, '/model beta{Enter}')

    // On screen: the note the command answered with.
    expect(await screen.findByText(/Pinned to model-beta/)).toBeInTheDocument()

    // Out loud: that same note, and then the pill's switch — in that order,
    // neither eating the other.
    await waitFor(() => expect(transcript.said).toHaveLength(2))
    expect(transcript.said[0]).toMatch(/^Pinned to model-beta/)
    expect(transcript.said[1]).toMatch(/^Switched to model-beta/)
    transcript.stop()
  })
})
