// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useRef, useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import type { DiscoveredModel, ModelSelection } from '../types'
import type { UseModelPickerResult } from '../useModelPicker'
import { QuickSwitchPopover } from './QuickSwitchPopover'

// Placeholder names throughout: the package never ships a model name, and
// neither do its fixtures. Providers are named because those are vendors.
const MODELS: DiscoveredModel[] = [
  {
    id: 'model-a',
    name: 'model-a',
    endpointId: 'ep-local',
    provider: 'ollama',
    isLocal: true,
    capabilities: { tools: true },
  },
  {
    id: 'model-b',
    name: 'model-b',
    endpointId: 'ep-local',
    provider: 'ollama',
    isLocal: true,
    capabilities: {},
  },
  {
    id: 'model-c',
    name: 'model-c',
    endpointId: 'ep-hosted',
    provider: 'openai',
    isLocal: false,
    capabilities: { vision: true },
  },
]

function stubPicker(
  overrides: Partial<UseModelPickerResult> = {},
): UseModelPickerResult {
  return {
    config: { endpoints: [], assignments: {}, chatCapableProviders: [] },
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

interface HarnessProps {
  picker: UseModelPickerResult
  /** Off for hosts that hand the popover no trigger at all. */
  withTriggerRef?: boolean
  onRequestFocusReturn?: () => void
  onClose?: () => void
  onSelected?: (selection: ModelSelection) => void
}

/** Stands in for a host: a trigger, a rival focus target, and the popover. */
function Harness({
  picker,
  withTriggerRef = true,
  onRequestFocusReturn,
  onClose,
  onSelected,
}: HarnessProps) {
  const [open, setOpen] = useState(true)
  const triggerRef = useRef<HTMLButtonElement>(null)
  return (
    <div>
      <button type="button" ref={triggerRef} data-model-picker-trigger="">
        Trigger
      </button>
      <input aria-label="Somewhere else" />
      <button type="button" onClick={() => setOpen(false)}>
        Close from the host
      </button>
      <QuickSwitchPopover
        picker={picker}
        open={open}
        onClose={() => {
          onClose?.()
          setOpen(false)
        }}
        onSelected={onSelected}
        triggerRef={withTriggerRef ? triggerRef : undefined}
        onRequestFocusReturn={onRequestFocusReturn}
      />
    </div>
  )
}

const search = () => screen.getByLabelText('Search models')
const trigger = () => screen.getByRole('button', { name: 'Trigger' })
const highlighted = () =>
  document.querySelector('[data-highlighted] [data-part="model"]')?.textContent

describe('QuickSwitchPopover focus and aria', () => {
  it('hands focus back to the host trigger when it closes', () => {
    render(<Harness picker={stubPicker()} />)
    expect(search()).toHaveFocus()

    fireEvent.keyDown(search(), { key: 'Escape' })

    expect(screen.queryByRole('listbox')).toBeNull()
    expect(trigger()).toHaveFocus()
  })

  it('prefers the host callback over the trigger ref', () => {
    const back = vi.fn()
    render(<Harness picker={stubPicker()} onRequestFocusReturn={back} />)

    fireEvent.keyDown(search(), { key: 'Escape' })

    expect(back).toHaveBeenCalledTimes(1)
    expect(trigger()).not.toHaveFocus()
  })

  it('leaves focus where the user moved it', () => {
    render(<Harness picker={stubPicker()} />)
    const elsewhere = screen.getByLabelText('Somewhere else')
    elsewhere.focus()

    fireEvent.click(screen.getByRole('button', { name: 'Close from the host' }))

    expect(screen.queryByRole('listbox')).toBeNull()
    expect(elsewhere).toHaveFocus()
  })

  it('closes without a trigger seam and without throwing', () => {
    render(<Harness picker={stubPicker()} withTriggerRef={false} />)

    fireEvent.keyDown(search(), { key: 'Escape' })

    expect(screen.queryByRole('listbox')).toBeNull()
    expect(document.activeElement).toBe(document.body)
  })

  it('points the trigger at the listbox only while the listbox exists', () => {
    render(<Harness picker={stubPicker()} />)
    const listbox = screen.getByRole('listbox')
    expect(listbox.id).not.toBe('')
    expect(trigger()).toHaveAttribute('aria-controls', listbox.id)

    fireEvent.keyDown(search(), { key: 'Escape' })

    expect(trigger()).not.toHaveAttribute('aria-controls')
  })
})

describe('QuickSwitchPopover keyboard and dismissal', () => {
  it('walks the options in render order and wraps at both ends', () => {
    render(<Harness picker={stubPicker()} />)
    expect(highlighted()).toBe('model-a')

    fireEvent.keyDown(search(), { key: 'ArrowDown' })
    expect(highlighted()).toBe('model-b')

    // Cloud models follow local ones, so the walk crosses the group boundary.
    fireEvent.keyDown(search(), { key: 'ArrowDown' })
    expect(highlighted()).toBe('model-c')

    fireEvent.keyDown(search(), { key: 'ArrowDown' })
    expect(highlighted()).toBe('model-a')

    fireEvent.keyDown(search(), { key: 'ArrowUp' })
    expect(highlighted()).toBe('model-c')
  })

  it('keeps aria-activedescendant on the highlighted option', () => {
    render(<Harness picker={stubPicker()} />)
    fireEvent.keyDown(search(), { key: 'ArrowDown' })

    const option = document.querySelector('[data-highlighted]')
    expect(option).not.toBeNull()
    expect(search()).toHaveAttribute('aria-activedescendant', option?.id)
  })

  it('commits the highlighted option on Enter without dismissing', () => {
    const picker = stubPicker()
    const onSelected = vi.fn()
    render(<Harness picker={picker} onSelected={onSelected} />)

    fireEvent.keyDown(search(), { key: 'ArrowDown' })
    fireEvent.keyDown(search(), { key: 'Enter' })

    expect(picker.pinModel).toHaveBeenCalledWith('model-b', 'ep-local')
    expect(onSelected).toHaveBeenCalledWith({
      model: 'model-b',
      endpointId: 'ep-local',
    })
    expect(screen.getByRole('listbox')).toBeInTheDocument()
  })

  it('commits nothing on Enter when the search matches no model', () => {
    const picker = stubPicker()
    render(<Harness picker={picker} />)

    fireEvent.change(search(), { target: { value: 'qqq' } })
    expect(screen.getByText('No models match that search.')).toBeInTheDocument()

    fireEvent.keyDown(search(), { key: 'Enter' })

    expect(picker.pinModel).not.toHaveBeenCalled()
  })

  it('dismisses on an outside press but not on its own or the trigger', () => {
    const onClose = vi.fn()
    render(<Harness picker={stubPicker()} onClose={onClose} />)

    fireEvent.mouseDown(screen.getByRole('listbox'))
    expect(onClose).not.toHaveBeenCalled()

    // The trigger toggles itself; dismissing here would reopen on its click.
    fireEvent.mouseDown(trigger())
    expect(onClose).not.toHaveBeenCalled()

    fireEvent.mouseDown(screen.getByLabelText('Somewhere else'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
