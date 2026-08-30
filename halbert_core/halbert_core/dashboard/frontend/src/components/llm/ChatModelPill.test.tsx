// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-2: the in-chat model control.
 *
 * The package's own suite covers the pill and popover mechanics. These cover
 * what this wrapper adds: that it reports a pin upward so it can ride on the
 * next send, that a pin is never written to the stored configuration, and that
 * the health of the endpoint reaches the user.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type React from 'react'
import { useState } from 'react'
import { useModelPicker } from '@halbert/model-picker'
import type { ModelSelection } from '@halbert/model-picker'
import { HALBERT_MODEL_ROLES, modelPickerTransport } from '@/lib/halbertModelRoles'
import { lastAnnouncement } from '@/lib/announce'
import { LiveRegion } from '../shell/LiveRegion'
import { ChatModelPill } from './ChatModelPill'

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response
}

const ENDPOINT = {
  id: 'ep1', name: 'Local', provider: 'ollama',
  url: 'http://localhost:11434', api_key: '',
}

function config(overrides: Record<string, unknown> = {}) {
  return {
    saved_endpoints: [ENDPOINT],
    chat_model: { enabled: true, endpoint_id: 'ep1', model: 'model-a' },
    specialist_model: { enabled: false, endpoint_id: '', model: '' },
    vision_model: { enabled: false, endpoint_id: '', model: '' },
    secure_model: { enabled: false, endpoint_id: '', model: '' },
    ...overrides,
  }
}

let fetchMock: ReturnType<typeof vi.fn>

function route(ollamaRunning = true) {
  return vi.fn(async (url: string) => {
    const u = String(url)
    if (u.includes('/llm/config')) {
      return jsonResponse({ data: { llm_config: config(), chat_capable_providers: ['ollama'] } })
    }
    if (u.includes('/api/llm/discover')) {
      return jsonResponse({ data: {
        ollama: { running: ollamaRunning, url: ENDPOINT.url, version: '1.2.3', models: ['model-a', 'model-b'] },
        lm_studio: { running: false, url: 'http://localhost:1234', models: [] },
      } })
    }
    if (u.includes('proxy/models')) {
      return jsonResponse({ data: {
        models: ['model-a', 'model-b'],
        model_details: [{ name: 'model-a' }, { name: 'model-b' }],
      } })
    }
    return jsonResponse({ data: {} })
  })
}


/** Mirrors how AgentChat owns the picker and hands it to the pill. */
function Harness({
  onSelected,
  popoverClassName,
}: {
  onSelected?: (s: ModelSelection) => void
  popoverClassName?: string
}) {
  const picker = useModelPicker({
    transport: modelPickerTransport,
    roles: HALBERT_MODEL_ROLES,
  })
  const [open, setOpen] = useState(false)
  return (
    <>
      {/* AgentChat's `/model specialist` handler: it pins through this same
          picker without the popover ever opening. */}
      <button type="button" onClick={() => picker.pinTier('specialist')}>
        pin by command
      </button>
      <ChatModelPill
        picker={picker}
        open={open}
        onOpenChange={setOpen}
        onSelected={onSelected}
        popoverClassName={popoverClassName}
      />
    </>
  )
}

beforeEach(() => {
  fetchMock = route()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

describe('ChatModelPill', () => {
  it('shows the configured chat model without being asked', async () => {
    render(<Harness />)
    expect(await screen.findByText('model-a')).toBeInTheDocument()
  })

  it('exposes the trigger as a combobox for assistive tech', async () => {
    render(<Harness />)
    const trigger = await screen.findByRole('combobox')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox')
  })

  it('reports a pinned model upward so it can ride on the next send', async () => {
    const onSelectionChange = vi.fn()
    render(<Harness onSelected={onSelectionChange} />)

    await userEvent.click(await screen.findByRole('combobox'))
    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))

    await waitFor(() => expect(onSelectionChange).toHaveBeenCalled())
    const calls = onSelectionChange.mock.calls
    expect(calls[calls.length - 1][0]).toMatchObject({ model: 'model-b' })
  })

  it('never writes a pin to the stored configuration', async () => {
    // A pin governs this conversation only. Persisting it would silently
    // change the default for every future session.
    render(<Harness />)
    await userEvent.click(await screen.findByRole('combobox'))
    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))

    const writes = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === 'PUT',
    )
    expect(writes).toEqual([])
  })

  it('marks the pill offline when the local engine is not running', async () => {
    vi.stubGlobal('fetch', route(false))
    render(<Harness />)
    const trigger = await screen.findByRole('combobox')
    await waitFor(() =>
      expect(trigger.getAttribute('aria-label')).toMatch(/not running/i),
    )
  })

  it('closes the popover after a selection', async () => {
    render(<Harness />)
    const trigger = await screen.findByRole('combobox')
    await userEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))
    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'false'))
  })

  it('opens downward by default', async () => {
    render(<Harness />)
    const trigger = await screen.findByRole('combobox')
    await userEvent.click(trigger)
    const popover = await waitFor(() => {
      const el = document.querySelector('[data-model-picker-popover]')
      expect(el).not.toBeNull()
      return el as HTMLElement
    })
    expect(popover.className).toContain('top-full')
    expect(popover.className).toContain('bg-muted')
  })

  it('lets the composer flip the popover upward without losing the surface', async () => {
    // The pill sits in the composer footer, where a 384x384 popover opening
    // downward is off the bottom of the window. Only the position half is a
    // caller's to override — the background, border, scroll and padding are
    // the component's.
    render(<Harness popoverClassName="absolute right-0 bottom-full mb-1 w-96 z-50" />)
    const trigger = await screen.findByRole('combobox')
    await userEvent.click(trigger)
    const popover = await waitFor(() => {
      const el = document.querySelector('[data-model-picker-popover]')
      expect(el).not.toBeNull()
      return el as HTMLElement
    })
    expect(popover.className).toContain('bottom-full')
    expect(popover.className).not.toContain('top-full')
    expect(popover.className).toContain('bg-muted')
    expect(popover.className).toContain('overflow-y-auto')
  })
})


/**
 * A guide on the local runtime and a specialist at a paid cloud vendor — the
 * arrangement where naming the wrong slot costs the user money.
 */
const CLOUD_ENDPOINT = {
  id: 'ep2', name: 'Hosted', provider: 'anthropic',
  url: 'https://api.example.invalid', api_key: 'opaque',
}

function routeWithSpecialist() {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    if (u.includes('/llm/config')) {
      return jsonResponse({ data: {
        llm_config: {
          ...config(),
          saved_endpoints: [ENDPOINT, CLOUD_ENDPOINT],
          specialist_model: { enabled: true, endpoint_id: 'ep2', model: 'model-cloud' },
        },
        chat_capable_providers: ['ollama', 'anthropic'],
      } })
    }
    if (u.includes('/api/llm/discover')) {
      return jsonResponse({ data: {
        ollama: { running: true, url: ENDPOINT.url, version: '1.2.3', models: ['model-a'] },
        lm_studio: { running: false, url: 'http://localhost:1234', models: [] },
      } })
    }
    if (u.includes('proxy/models')) {
      const body = JSON.parse(String(init?.body ?? '{}'))
      const models = body.provider === 'anthropic' ? ['model-cloud'] : ['model-a', 'model-b']
      return jsonResponse({ data: {
        models, model_details: models.map((name) => ({ name })),
      } })
    }
    return jsonResponse({ data: {} })
  })
}

const liveRegion = (container: HTMLElement) =>
  container.querySelector('[data-model-picker-live]')

const tierBadge = (container: HTMLElement) =>
  container.querySelector('[data-model-picker-trigger] [data-part="tier"]')

async function pinTier(name: RegExp) {
  await userEvent.click(await screen.findByRole('combobox'))
  await userEvent.click(await screen.findByRole('button', { name }))
}

describe('ChatModelPill on a tier pin', () => {
  beforeEach(() => vi.stubGlobal('fetch', routeWithSpecialist()))

  it('names the tier’s own model, not the chat model', async () => {
    // The pin routes the turn to the specialist slot. Reading the chat slot
    // instead has the pill promise a local model while a cloud one bills.
    render(<Harness />)
    expect(await screen.findByText('model-a')).toBeInTheDocument()

    await pinTier(/^Specialist$/)

    expect(await screen.findByText('model-cloud')).toBeInTheDocument()
    expect(screen.queryByText('model-a')).not.toBeInTheDocument()
  })

  it('drops the local badge when the pinned tier is a cloud model', async () => {
    const { container } = render(<Harness />)
    await waitFor(() =>
      expect(container.querySelector('[data-model-picker-trigger]'))
        .toHaveAttribute('data-local', 'true'),
    )

    await pinTier(/^Specialist$/)

    await waitFor(() =>
      expect(container.querySelector('[data-model-picker-trigger]'))
        .not.toHaveAttribute('data-local'),
    )
    expect(await screen.findByText('Anthropic')).toBeInTheDocument()
  })

  it('falls back to the chat model when the pinned tier has none', async () => {
    // Matches resolve_turn_model: an unconfigured tier uses the guide rather
    // than refusing the turn, so the pill must not claim nothing will answer.
    render(<Harness />)
    await pinTier(/^Vision$/)

    expect(await screen.findByText('model-a')).toBeInTheDocument()
  })
})

describe('ChatModelPill tier badge', () => {
  beforeEach(() => vi.stubGlobal('fetch', routeWithSpecialist()))

  it('shows automatic routing while nothing is pinned', async () => {
    const { container } = render(<Harness />)
    await screen.findByText('model-a')
    expect(tierBadge(container)).toHaveTextContent('⚡ Auto: Guide')
  })

  it('shows a pinned tier as locked to it', async () => {
    const { container } = render(<Harness />)
    await pinTier(/^Specialist$/)
    await waitFor(() =>
      expect(tierBadge(container)).toHaveTextContent('🔒 Pin: Specialist'),
    )
  })

  it('shows the vision tier in its own form', async () => {
    const { container } = render(<Harness />)
    await pinTier(/^Vision$/)
    await waitFor(() => expect(tierBadge(container)).toHaveTextContent('👁️ Vision'))
  })
})

/**
 * Rewritten, not weakened: the three assertions below are the ones this
 * describe always made — a switch made without the popover is announced, the
 * announcement is hidden but polite, and it survives the popover closing on
 * commit. What changed is which region carries them. The pill used to render
 * a polite region of its own beside the shell's `role="status"`, leaving two
 * polite regions in one document; it now speaks through the shell's, so these
 * read the region the user's screen reader actually watches.
 */
function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <LiveRegion />
      {children}
    </>
  )
}

const politeRegions = (container: HTMLElement) =>
  container.querySelectorAll('[role="status"], [aria-live="polite"]')

describe('ChatModelPill switch announcement', () => {
  beforeEach(() => vi.stubGlobal('fetch', routeWithSpecialist()))

  it('announces a switch made without the popover', async () => {
    // The popover is torn down the moment a selection commits, so an
    // announcement living inside it is never read. This one follows the
    // selection, whether a click, a slash command or a tier button set it.
    render(<Shell><Harness /></Shell>)
    await screen.findByText('model-a')
    expect(screen.getByRole('status')).toHaveTextContent('')

    await userEvent.click(screen.getByRole('button', { name: /pin by command/ }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        'Switched to the Specialist tier: model-cloud on Anthropic will answer the next turn.',
      ),
    )
  })

  it('keeps the announcement out of sight but not out of earshot', async () => {
    render(<Shell><Harness /></Shell>)
    await screen.findByText('model-a')

    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByRole('status')).toHaveClass('sr-only')
  })

  it('survives the popover closing on commit', async () => {
    render(<Shell><Harness /></Shell>)
    await pinTier(/^Specialist$/)

    expect(await screen.findByRole('combobox')).toHaveAttribute('aria-expanded', 'false')
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(/Specialist tier/),
    )
  })

  it('leaves exactly one polite live region in the tree', async () => {
    // Two polite regions is one more than a screen reader can be relied on to
    // read in order, and the switch was the only thing keeping the second one
    // alive.
    const { container } = render(<Shell><Harness /></Shell>)
    await screen.findByText('model-a')

    expect(liveRegion(container)).toBeNull()
    expect(politeRegions(container)).toHaveLength(1)
  })

  it('still reaches the shell region after the popover commits a model', async () => {
    render(<Shell><Harness /></Shell>)
    await userEvent.click(await screen.findByRole('combobox'))
    await userEvent.click(await screen.findByRole('option', { name: /model-b/ }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(/model-b/),
    )
    expect(lastAnnouncement()).toContain('model-b')
  })
})


describe('ChatModelPill on a layered host', () => {
  it('names the model in force, not the one being edited', async () => {
    // The drawer edits the global layer; a workspace file or a session pin can
    // override it. Showing the editable value would have the pill name a model
    // that is not answering — the one question the pill exists to answer.
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url)
      if (u.includes('/llm/config')) {
        return jsonResponse({ data: {
          llm_config: { ...config(), chat_model: { enabled: true, endpoint_id: 'ep1', model: 'model-global' } },
          chat_capable_providers: ['ollama'],
          effective: {
            llm_config: { ...config(), chat_model: { enabled: true, endpoint_id: 'ep1', model: 'model-inforce' } },
            overridden_slots: { chat_model: 'workspace' },
          },
        } })
      }
      if (u.includes('/api/llm/discover')) {
        return jsonResponse({ data: {
          ollama: { running: true, url: ENDPOINT.url, version: '1.2.3', models: ['model-global', 'model-inforce'] },
          lm_studio: { running: false, url: 'http://localhost:1234', models: [] },
        } })
      }
      if (u.includes('proxy/models')) {
        return jsonResponse({ data: {
          models: ['model-global', 'model-inforce'],
          model_details: [{ name: 'model-global' }, { name: 'model-inforce' }],
        } })
      }
      return jsonResponse({ data: {} })
    }))

    render(<Harness />)
    expect(await screen.findByText('model-inforce')).toBeInTheDocument()
    expect(screen.queryByText('model-global')).not.toBeInTheDocument()
  })
})


/**
 * The bug jsdom cannot see on its own: the pill moved from the chat header
 * into the composer footer, where a 384x384 popover opening downward is off
 * the bottom of the window — and the shell's mode container is
 * `overflow-hidden`, so it is clipped rather than scrolled to.
 *
 * jsdom reports every rect as zero, so these stub the one measurement the
 * component makes: the trigger's position in the viewport.
 */
function rect(top: number, height: number): DOMRect {
  return {
    top, bottom: top + height, height,
    left: 0, right: 0, width: 0, x: 0, y: top,
    toJSON: () => ({}),
  } as DOMRect
}

function stubViewport(viewportHeight: number, triggerTop: number) {
  vi.stubGlobal('innerHeight', viewportHeight)
  const real = Element.prototype.getBoundingClientRect
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(
    function (this: Element) {
      return this.hasAttribute('data-model-picker-trigger')
        ? rect(triggerTop, 28)
        : real.call(this)
    },
  )
}

async function openPopover() {
  await userEvent.click(await screen.findByRole('combobox'))
  return await waitFor(() => {
    const el = document.querySelector('[data-model-picker-popover]')
    expect(el).not.toBeNull()
    return el as HTMLElement
  })
}

describe('ChatModelPill popover placement', () => {
  afterEach(() => vi.restoreAllMocks())

  it('opens upward when the pill sits at the bottom of the window', async () => {
    // The composer footer. Opening downward here puts the whole popover
    // past the bottom edge, which is the shipped defect.
    stubViewport(720, 660)
    render(<Harness />)
    const popover = await openPopover()

    expect(popover.className).toContain('bottom-full')
    expect(popover.className).not.toContain('top-full')
  })

  it('opens downward when the pill sits at the top of the window', async () => {
    // Wherever else the pill is mounted — a panel header — downward is still
    // right, so the flip has to be measured rather than hard-coded either way.
    stubViewport(900, 60)
    render(<Harness />)
    const popover = await openPopover()

    expect(popover.className).toContain('top-full')
    expect(popover.className).not.toContain('bottom-full')
  })

  it('is never taller than the room it has, on either side', async () => {
    // A short window: 180px above the pill is less than the 384px the
    // surface would otherwise take, and the overflow would be clipped.
    stubViewport(340, 260)
    render(<Harness />)
    const popover = await openPopover()

    expect(popover.className).toContain('bottom-full')
    const maxHeight = Number.parseInt(popover.style.maxHeight, 10)
    expect(maxHeight).toBeGreaterThan(0)
    expect(maxHeight).toBeLessThanOrEqual(260)
  })

  it('clamps to the caller’s side, not its own, when the caller positions it', async () => {
    // AgentChat hard-codes the upward variant. The height still has to match
    // the side that actually renders, or the clamp protects the wrong edge.
    stubViewport(340, 260)
    render(<Harness popoverClassName="absolute right-0 bottom-full mb-1 w-96 z-50" />)
    const popover = await openPopover()

    const maxHeight = Number.parseInt(popover.style.maxHeight, 10)
    expect(maxHeight).toBeLessThanOrEqual(260)
  })

  it('takes the full surface height when the window is tall enough', async () => {
    stubViewport(1200, 80)
    render(<Harness />)
    const popover = await openPopover()

    expect(popover.style.maxHeight).toBe('384px')
  })
})


/**
 * The frame that clips the popover is not the window.
 *
 * `Layout.tsx` stacks a `h-12` header with a bottom border (49px) above the
 * mode container that holds this surface, and that container is
 * `overflow-hidden` — so the top 49px of the viewport is a ceiling the
 * popover is cut off by rather than room it can open into. Nothing between
 * the pill's wrapper and that container scrolls, so it is the clipping box.
 *
 * jsdom neither lays anything out nor expands the `overflow` shorthand in
 * computed style, so these stub the two rects the component reads and mark
 * the frame with an inline longhand the way a browser would report it.
 */
function stubFramedViewport({
  viewportHeight,
  triggerTop,
  frameTop,
  frameBottom = viewportHeight,
}: {
  viewportHeight: number
  triggerTop: number
  frameTop: number
  frameBottom?: number
}) {
  vi.stubGlobal('innerHeight', viewportHeight)
  const real = Element.prototype.getBoundingClientRect
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(
    function (this: Element) {
      if (this.hasAttribute('data-model-picker-trigger')) return rect(triggerTop, 28)
      if (this.hasAttribute('data-test-frame')) return rect(frameTop, frameBottom - frameTop)
      return real.call(this)
    },
  )
}

/** The shell's `overflow-hidden` mode container, as far as the pill can tell. */
function Framed({ children }: { children: React.ReactNode }) {
  return (
    <div data-test-frame="" style={{ overflowY: 'hidden' }}>
      {children}
    </div>
  )
}

describe('ChatModelPill popover clipping frame', () => {
  afterEach(() => vi.restoreAllMocks())

  it('leaves room for the header the popover is clipped by, not just the window', async () => {
    // A 460px-tall viewport is a 1000px browser window at 210% zoom, which is
    // a low-vision user's ordinary setting. Measured against the window there
    // are 410px above the pill and the surface takes its full 384; measured
    // against the frame there are 361, and the difference is the 45px of the
    // popover's head — including the search box that takes focus on open —
    // that was being cut off above the ceiling.
    stubFramedViewport({ viewportHeight: 460, triggerTop: 418, frameTop: 49 })
    render(<Framed><Harness /></Framed>)
    const popover = await openPopover()

    expect(popover.className).toContain('bottom-full')
    const maxHeight = Number.parseInt(popover.style.maxHeight, 10)
    // `bottom-full mb-1` puts the popover's bottom 4px above the trigger, so
    // its top edge is triggerTop - 4 - maxHeight. That has to stay inside the
    // frame, not merely inside the window.
    expect(418 - 4 - maxHeight).toBeGreaterThanOrEqual(49)
  })

  it('flips upward when the frame ends above the bottom of the window', async () => {
    // Room the window has and the frame does not is not room. Believing the
    // window here opens a 384px popover downward into 24px of frame.
    stubFramedViewport({
      viewportHeight: 1000, triggerTop: 500, frameTop: 49, frameBottom: 560,
    })
    render(<Framed><Harness /></Framed>)
    const popover = await openPopover()

    expect(popover.className).toContain('bottom-full')
    expect(popover.className).not.toContain('top-full')
  })

  it('still measures the window when nothing between clips', async () => {
    // The fallback matters as much as the frame: a pill mounted somewhere
    // with no clipping ancestor must not be clamped to a frame of nothing.
    stubFramedViewport({ viewportHeight: 1200, triggerTop: 80, frameTop: 0 })
    render(<Harness />)
    const popover = await openPopover()

    expect(popover.className).toContain('top-full')
    expect(popover.style.maxHeight).toBe('384px')
  })
})
