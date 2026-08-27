// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The pill answers one question: what will answer the next turn. These cover
 * the ways it can answer it wrongly — reading a pin off the wrong slot, hiding
 * which tier is in force, and switching without telling a screen reader.
 */
import { render } from '@testing-library/react'
import type {
  DiscoveredModel,
  ModelSelection,
  RoleAssignment,
  SavedEndpoint,
} from '../types'
import type { UseModelPickerResult } from '../useModelPicker'
import { ModelSelectorPill } from './ModelSelectorPill'

// Placeholder names throughout: the package never ships a model name, and
// neither do its fixtures. Providers are named because those are vendors.
const LOCAL: SavedEndpoint = {
  id: 'ep-local',
  name: 'Local runtime',
  provider: 'ollama',
  url: 'http://localhost:11434',
}

const CLOUD: SavedEndpoint = {
  id: 'ep-cloud',
  name: 'Hosted vendor',
  provider: 'anthropic',
  url: 'https://api.example.invalid',
}

const MODELS: DiscoveredModel[] = [
  {
    id: 'model-a',
    name: 'model-a',
    endpointId: LOCAL.id,
    provider: 'ollama',
    isLocal: true,
    capabilities: { tools: true },
  },
  {
    id: 'model-b',
    name: 'model-b',
    endpointId: CLOUD.id,
    provider: 'anthropic',
    isLocal: false,
    capabilities: { reasoning: true },
  },
]

// Host vocabulary the package cannot know, deliberately unlike any real host's.
const DEFAULT_ROLE = 'primary'
const TIER_ROLES = { guide: DEFAULT_ROLE, specialist: 'deep', vision: 'sight' }

const enabled = (endpointId: string, model: string): RoleAssignment => ({
  endpointId,
  model,
  enabled: true,
})

const ASSIGNMENTS: Record<string, RoleAssignment> = {
  [DEFAULT_ROLE]: enabled(LOCAL.id, 'model-a'),
  deep: enabled(CLOUD.id, 'model-b'),
  // The vision slot is left empty on purpose: a host may never configure it.
  sight: { endpointId: '', model: '', enabled: false },
}

function stubPicker(
  selection: ModelSelection,
  assignments: Record<string, RoleAssignment> = ASSIGNMENTS,
): UseModelPickerResult {
  return {
    config: { endpoints: [LOCAL, CLOUD], assignments, chatCapableProviders: [] },
    roles: [],
    loading: false,
    error: null,
    models: MODELS,
    modelsByEndpoint: {},
    listing: [],
    discovery: null,
    discovering: false,
    chatCapableEndpoints: [],
    isChatCapable: () => true,
    modelsForRole: () => MODELS,
    assignmentFor: (roleId) => assignments[roleId],
    effectiveAssignmentFor: (roleId) => assignments[roleId],
    overrideLayerFor: () => undefined,
    endpointFor: (id) => [LOCAL, CLOUD].find((e) => e.id === id),
    selection,
    setSelection: vi.fn(),
    pinModel: vi.fn(),
    pinTier: vi.fn(),
    clearPin: vi.fn(),
    // Mirrors useModelPicker rather than being set per test, so a fixture
    // cannot claim a pin the hook would not have recognised.
    isPinned: Boolean(
      selection.model || (selection.tier && selection.tier !== 'auto'),
    ),
    refresh: vi.fn(async () => {}),
    refreshModels: vi.fn(async () => {}),
    discoverLocal: vi.fn(async () => {}),
    assignRole: vi.fn(async () => {}),
    clearRole: vi.fn(async () => {}),
    saveEndpoint: vi.fn(async () => {}),
    deleteEndpoint: vi.fn(async () => {}),
    testEndpoint: vi.fn(async () => ({ ok: true, message: '' })),
    testModel: vi.fn(async () => ({ ok: true, message: '' })),
    testing: null,
    testResults: {},
  }
}

function mount(
  selection: ModelSelection,
  options: {
    tierRoles?: typeof TIER_ROLES
    assignments?: Record<string, RoleAssignment>
    onAnnounce?: (text: string) => void
  } = {},
) {
  const view = render(
    <ModelSelectorPill
      picker={stubPicker(selection, options.assignments)}
      activeRoleId={DEFAULT_ROLE}
      tierRoles={options.tierRoles}
      onAnnounce={options.onAnnounce}
    />,
  )
  const read = () => ({
    trigger: view.container.querySelector('button') as HTMLButtonElement,
    model: view.container.querySelector('[data-part="model"]')?.textContent,
    provider: view.container.querySelector('[data-part="provider"]')?.textContent,
    badge: view.container.querySelector('[data-part="tier"]')?.textContent,
    pin: view.container.querySelector('[data-part="pin"]'),
    live: view.container.querySelector('[data-model-picker-live]'),
  })
  return {
    ...view,
    read,
    show: (next: ModelSelection) =>
      view.rerender(
        <ModelSelectorPill
          picker={stubPicker(next, options.assignments)}
          activeRoleId={DEFAULT_ROLE}
          tierRoles={options.tierRoles}
          onAnnounce={options.onAnnounce}
        />,
      ),
  }
}

describe('ModelSelectorPill on a tier pin', () => {
  it('names the model of the tier that was pinned, not the default role', () => {
    // The failure this exists to catch: the pill stating a local model with a
    // local badge while the pinned tier sends the turn to a paid cloud model.
    const { read } = mount({ tier: 'specialist' }, { tierRoles: TIER_ROLES })

    expect(read().model).toBe('model-b')
    expect(read().provider).toBe('Anthropic')
    expect(read().trigger).not.toHaveAttribute('data-local')
  })

  it('names the default role when nothing is pinned', () => {
    const { read } = mount({ tier: 'auto' }, { tierRoles: TIER_ROLES })

    expect(read().model).toBe('model-a')
    expect(read().provider).toBe('Ollama')
    expect(read().trigger).toHaveAttribute('data-local', 'true')
  })

  it('keeps naming the default role for a host that maps no tiers', () => {
    // Tier ids are ours and role ids are the host's, so without a map there is
    // nothing to resolve; every host written before the map behaves as before.
    const { read } = mount({ tier: 'specialist' })

    expect(read().model).toBe('model-a')
  })

  it('falls back to the default role when the pinned tier has no model', () => {
    // Routers treat an unconfigured tier as "use the default" rather than
    // refusing the turn, so claiming nothing is configured would be its own lie.
    const { read } = mount({ tier: 'vision' }, { tierRoles: TIER_ROLES })

    expect(read().model).toBe('model-a')
    expect(read().provider).toBe('Ollama')
  })

  it('resolves an exact model pin ahead of any tier it arrives with', () => {
    const { read } = mount(
      { model: 'model-a', endpointId: LOCAL.id, tier: 'specialist' },
      { tierRoles: TIER_ROLES },
    )

    expect(read().model).toBe('model-a')
  })

  it('speaks the pinned tier in the trigger label', () => {
    const { read } = mount({ tier: 'specialist' }, { tierRoles: TIER_ROLES })

    expect(read().trigger.getAttribute('aria-label')).toContain('Specialist tier')
    expect(read().trigger.getAttribute('aria-label')).toContain('Anthropic')
  })
})

describe('ModelSelectorPill tier badge', () => {
  it('shows automatic routing as starting at the guide tier', () => {
    expect(mount({ tier: 'auto' }, { tierRoles: TIER_ROLES }).read().badge).toBe(
      '⚡ Auto: Guide',
    )
  })

  it('shows a pinned tier as locked', () => {
    expect(
      mount({ tier: 'specialist' }, { tierRoles: TIER_ROLES }).read().badge,
    ).toBe('🔒 Pin: Specialist')
  })

  it('shows the vision tier in its own form', () => {
    expect(mount({ tier: 'vision' }, { tierRoles: TIER_ROLES }).read().badge).toBe(
      '👁️ Vision',
    )
  })

  it('drops the badge for an exact model pin, which no tier governs', () => {
    const { read } = mount({ model: 'model-b', endpointId: CLOUD.id })

    expect(read().badge).toBeUndefined()
    // The lock still has to say a pin is in force.
    expect(read().pin).not.toBeNull()
  })

  it('carries one lock, not two, while a tier is pinned', () => {
    const { read } = mount({ tier: 'specialist' }, { tierRoles: TIER_ROLES })

    expect(read().pin).toBeNull()
    expect(read().badge).toContain('🔒')
  })
})

describe('ModelSelectorPill switch announcement', () => {
  it('says nothing on arrival, because arriving is not a switch', () => {
    expect(mount({ tier: 'auto' }).read().live?.textContent).toBe('')
  })

  it('announces a switch the popover had no part in', () => {
    // A `/model` command or a host's own tier control changes the selection
    // without a click here; announcing from a click handler leaves both silent.
    const { read, show } = mount({ tier: 'auto' }, { tierRoles: TIER_ROLES })
    show({ model: 'model-b', endpointId: CLOUD.id })

    expect(read().live).toHaveAttribute('aria-live', 'polite')
    expect(read().live?.textContent).toBe(
      'Switched to model-b on Anthropic for the next turn.',
    )
  })

  it('announces a tier pin by the model that tier will run', () => {
    const { read, show } = mount({ tier: 'auto' }, { tierRoles: TIER_ROLES })
    show({ tier: 'specialist' })

    expect(read().live?.textContent).toBe(
      'Switched to the Specialist tier: model-b on Anthropic will answer the next turn.',
    )
  })

  it('announces a return to automatic routing', () => {
    const { read, show } = mount({ tier: 'specialist' }, { tierRoles: TIER_ROLES })
    show({ tier: 'auto' })

    expect(read().live?.textContent).toBe(
      'Routing automatically: model-a on Ollama will answer the next turn.',
    )
  })

  it('stays quiet when a re-render leaves the selection alone', () => {
    const { read, show } = mount({ tier: 'auto' }, { tierRoles: TIER_ROLES })
    show({ tier: 'auto' })

    expect(read().live?.textContent).toBe('')
  })
})

/**
 * A host with its own polite live region — a shell that already announces
 * "New subject" and "Turn forgotten" — must not end up with two of them.
 * Two polite regions in one document is one more than a screen reader can be
 * relied on to read in a predictable order, so the pill hands the sentence
 * over and renders nothing rather than competing.
 */
describe('ModelSelectorPill announcing through the host', () => {
  it('renders no region of its own once the host takes the announcements', () => {
    const onAnnounce = vi.fn()
    const { read } = mount({ tier: 'auto' }, { tierRoles: TIER_ROLES, onAnnounce })

    expect(read().live).toBeNull()
  })

  it('hands the host the same sentence its own region would have carried', () => {
    const onAnnounce = vi.fn()
    const { show } = mount({ tier: 'auto' }, { tierRoles: TIER_ROLES, onAnnounce })

    show({ tier: 'specialist' })

    expect(onAnnounce).toHaveBeenCalledTimes(1)
    expect(onAnnounce).toHaveBeenCalledWith(
      'Switched to the Specialist tier: model-b on Anthropic will answer the next turn.',
    )
  })

  it('says nothing to the host on arrival either', () => {
    const onAnnounce = vi.fn()
    mount({ tier: 'auto' }, { tierRoles: TIER_ROLES, onAnnounce })

    expect(onAnnounce).not.toHaveBeenCalled()
  })

  it('stays quiet when a re-render leaves the selection alone', () => {
    const onAnnounce = vi.fn()
    const { show } = mount({ tier: 'auto' }, { tierRoles: TIER_ROLES, onAnnounce })

    show({ tier: 'auto' })

    expect(onAnnounce).not.toHaveBeenCalled()
  })

  it('keeps its own region for a host that offers none', () => {
    // The package ships for hosts that have no live region at all; dropping
    // the fallback would make a switch silent for them.
    const { read, show } = mount({ tier: 'auto' }, { tierRoles: TIER_ROLES })
    show({ tier: 'specialist' })

    expect(read().live).not.toBeNull()
    expect(read().live?.textContent).toContain('Specialist tier')
  })
})
