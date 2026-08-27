// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * The drawer's styling and slot seams.
 *
 * A composite whose only seam is its own root is one a host cannot use: the
 * first host that needed styled rows dropped the drawer and re-implemented
 * every effect inside it. These tests pin the seams that make that
 * unnecessary — a key that stops landing on its element is the same defect
 * returning.
 */
import { render, screen } from '@testing-library/react'
import type { AppRole, DiscoveredModel, SavedEndpoint } from '../types'
import type { UseModelPickerResult } from '../useModelPicker'
import { ModelSettingsDrawer } from './ModelSettingsDrawer'
import type { ModelSettingsDrawerClassNames } from './ModelSettingsDrawer'

// Placeholder names throughout: the package never ships a model name, and
// neither do its fixtures. Providers are named because those are vendors.
const LOCAL: SavedEndpoint = {
  id: 'ep-local',
  name: 'Local runtime',
  provider: 'ollama',
  url: 'http://localhost:11434',
}

const HOSTED: SavedEndpoint = {
  id: 'ep-hosted',
  name: 'Hosted vendor',
  provider: 'openai',
  url: 'https://api.example.invalid/v1',
}

const MODELS: DiscoveredModel[] = [
  {
    id: 'model-a',
    name: 'model-a',
    endpointId: 'ep-local',
    provider: 'ollama',
    isLocal: true,
    capabilities: {},
  },
]

const ROLES: AppRole[] = [
  { id: 'primary', label: 'Primary', description: 'Answers most turns.' },
  { id: 'secondary', label: 'Secondary', description: 'Answers the rest.' },
]

const CLASSES: Required<ModelSettingsDrawerClassNames> = {
  root: 'cls-root',
  rolesSection: 'cls-roles-section',
  roleGrid: 'cls-role-grid',
  roleRow: 'cls-role-row',
  assignPrompt: 'cls-assign-prompt',
  providersSection: 'cls-providers-section',
  providersTrigger: 'cls-providers-trigger',
  providersRegion: 'cls-providers-region',
  providerGroup: 'cls-provider-group',
  providerGroupHeading: 'cls-provider-group-heading',
  providerCard: 'cls-provider-card',
  note: 'cls-note',
  announcement: 'cls-announcement',
}

function stubPicker(
  overrides: Partial<UseModelPickerResult> = {},
): UseModelPickerResult {
  return {
    config: { endpoints: [], assignments: {}, chatCapableProviders: [] },
    roles: ROLES,
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
    assignmentFor: () => undefined,
    endpointFor: () => undefined,
    selection: { tier: 'auto' },
    setSelection: vi.fn(),
    pinModel: vi.fn(),
    pinTier: vi.fn(),
    clearPin: vi.fn(),
    isPinned: false,
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
    ...overrides,
  }
}

function withEndpoints(endpoints: SavedEndpoint[]): UseModelPickerResult {
  return stubPicker({
    config: { endpoints, assignments: {}, chatCapableProviders: ['ollama'] },
  })
}

describe('ModelSettingsDrawer class name seams', () => {
  it('lands every key on the element it names', () => {
    const { container } = render(
      <ModelSettingsDrawer
        picker={withEndpoints([LOCAL, HOSTED])}
        providersOpen
        classNames={CLASSES}
        groupProviders
      />,
    )

    const at = (cls: string) => container.querySelector<HTMLElement>(`.${cls}`)

    expect(at('cls-root')).toBe(container.firstElementChild)
    expect(at('cls-roles-section')).toContainElement(at('cls-role-grid'))
    expect(at('cls-role-grid')).toHaveAttribute('aria-label', 'Model assignments')
    expect(container.querySelectorAll('.cls-role-row')).toHaveLength(ROLES.length)
    expect(at('cls-role-row')).toHaveAttribute('data-role-id', 'primary')

    expect(at('cls-providers-section')).toContainElement(
      at('cls-providers-trigger'),
    )
    expect(at('cls-providers-trigger')).toHaveAttribute('aria-expanded', 'true')
    expect(at('cls-providers-region')).toHaveAttribute('role', 'region')

    expect(container.querySelectorAll('.cls-provider-group')).toHaveLength(2)
    expect(at('cls-provider-group-heading')).toHaveTextContent('Local engines')
    expect(container.querySelectorAll('.cls-provider-card')).toHaveLength(2)
    expect(at('cls-provider-card')).toHaveAttribute('data-provider', 'ollama')

    expect(at('cls-announcement')).toHaveAttribute('role', 'status')
  })

  it('keeps the host class after its own, so the host wins', () => {
    const { container } = render(
      <ModelSettingsDrawer
        picker={stubPicker()}
        className="host-root"
        classNames={{ root: 'cls-root' }}
      />,
    )

    expect(container.querySelector<HTMLElement>('.cls-root')).toHaveClass(
      'host-root',
      'cls-root',
    )
  })

  it('names the empty-state line, so a host can style it', () => {
    const { container } = render(
      <ModelSettingsDrawer
        picker={stubPicker()}
        providersOpen
        classNames={{ note: 'cls-note' }}
      />,
    )

    expect(container.querySelector<HTMLElement>('.cls-note')).toHaveTextContent(
      'No providers configured yet.',
    )
  })

  it('names the offer to use an endpoint nothing is assigned to yet', () => {
    const { container, rerender } = render(
      <ModelSettingsDrawer
        picker={withEndpoints([])}
        classNames={{ assignPrompt: 'cls-assign-prompt' }}
      />,
    )

    rerender(
      <ModelSettingsDrawer
        picker={withEndpoints([LOCAL])}
        classNames={{ assignPrompt: 'cls-assign-prompt' }}
      />,
    )

    expect(
      container.querySelector<HTMLElement>('.cls-assign-prompt'),
    ).toHaveTextContent(
      'is saved but nothing is using it yet',
    )
  })
})

describe('ModelSettingsDrawer render slots', () => {
  it('reaches every role row with renderRoleStatus', () => {
    render(
      <ModelSettingsDrawer
        picker={stubPicker({
          testResults: { primary: { ok: true, message: 'reached' } },
        })}
        renderRoleStatus={(role, result) => (
          <span data-testid={`status-${role.id}`}>
            {result ? result.message : 'untested'}
          </span>
        )}
      />,
    )

    expect(screen.getByTestId('status-primary')).toHaveTextContent('reached')
    expect(screen.getByTestId('status-secondary')).toHaveTextContent('untested')
  })

  it('reaches every provider card with renderProviderBadge', () => {
    render(
      <ModelSettingsDrawer
        picker={withEndpoints([LOCAL, HOSTED])}
        providersOpen
        renderProviderBadge={(endpoint, provider) => (
          <span data-testid={`badge-${endpoint?.id ?? provider}`}>
            {provider}
          </span>
        )}
      />,
    )

    expect(screen.getByTestId('badge-ep-local')).toHaveTextContent('ollama')
    expect(screen.getByTestId('badge-ep-hosted')).toHaveTextContent('openai')
  })

  it('renders providersFooter last in the open region', () => {
    render(
      <ModelSettingsDrawer
        picker={withEndpoints([LOCAL])}
        providersOpen
        providersFooter={<button type="button">Add a provider</button>}
      />,
    )

    const region = screen.getByRole('region')
    const footer = screen.getByRole('button', { name: 'Add a provider' })
    expect(region).toContainElement(footer)
    expect(region.lastElementChild).toBe(footer)
  })

  it('renders rolesHeader above the grid', () => {
    render(
      <ModelSettingsDrawer
        picker={stubPicker()}
        rolesHeader={<p>Role, endpoint, model</p>}
      />,
    )

    const header = screen.getByText('Role, endpoint, model')
    const grid = screen.getByRole('group', { name: 'Model assignments' })
    expect(header.nextElementSibling).toBe(grid)
  })

  it('lets a host replace the trigger label without losing its wiring', () => {
    render(
      <ModelSettingsDrawer
        picker={withEndpoints([LOCAL, HOSTED])}
        providersOpen
        renderProvidersLabel={(open, count) => (
          <span>{`${open ? 'Hide' : 'Show'} ${count}`}</span>
        )}
      />,
    )

    const trigger = screen.getByRole('button', { name: 'Hide 2' })
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(trigger).toHaveAttribute(
      'aria-controls',
      screen.getByRole('region').id,
    )
  })
})

describe('ModelSettingsDrawer provider grouping', () => {
  it('splits the cards into two labelled sections', () => {
    render(
      <ModelSettingsDrawer
        picker={withEndpoints([LOCAL, HOSTED])}
        providersOpen
        groupProviders
      />,
    )

    const local = screen.getByRole('region', { name: 'Local engines' })
    const cloud = screen.getByRole('region', { name: 'Cloud providers' })

    expect(local).toContainElement(
      screen.getByRole('group', { name: 'Local runtime' }),
    )
    expect(cloud).toContainElement(
      screen.getByRole('group', { name: 'Hosted vendor' }),
    )
  })

  it('states each empty half rather than leaving a blank section', () => {
    render(
      <ModelSettingsDrawer
        picker={withEndpoints([HOSTED])}
        providersOpen
        groupProviders
      />,
    )

    expect(
      screen.getByText('Nothing detected on the standard local ports.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('No cloud provider configured.')).toBeNull()
  })

  it('badges each group heading through renderGroupBadge', () => {
    render(
      <ModelSettingsDrawer
        picker={withEndpoints([LOCAL])}
        providersOpen
        groupProviders
        renderGroupBadge={(group) => (
          <span data-testid={`group-badge-${group}`}>{group}</span>
        )}
      />,
    )

    expect(screen.getByTestId('group-badge-local')).toBeInTheDocument()
    expect(screen.getByTestId('group-badge-cloud')).toBeInTheDocument()
  })

  it('leaves the flat list alone when grouping is off', () => {
    render(
      <ModelSettingsDrawer picker={withEndpoints([LOCAL, HOSTED])} providersOpen />,
    )

    expect(screen.queryByRole('region', { name: 'Local engines' })).toBeNull()
    expect(screen.getByRole('button', { name: /Providers \(2\)/ })).toBeInTheDocument()
    expect(screen.getAllByRole('group', { name: /runtime|vendor/ })).toHaveLength(2)
  })
})
