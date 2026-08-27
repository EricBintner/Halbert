// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState } from 'react'
import type { HTMLAttributes, ReactNode } from 'react'
import type { AppRole, EndpointTestResult } from '../types'
import type { UseModelPickerResult } from '../useModelPicker'

/**
 * `role` is the app slot, so the div's own ARIA `role` attribute is omitted
 * rather than shadowed; hosts that need one wrap the row.
 */
export interface RoleAssignmentRowProps
  extends Omit<HTMLAttributes<HTMLDivElement>, 'role'> {
  picker: UseModelPickerResult
  role: AppRole
  /** Slot for the host to render its own test-result presentation. */
  renderStatus?: (result: EndpointTestResult | undefined) => ReactNode
}

/** A choice the user has made that the transport has not yet acknowledged. */
interface Draft {
  endpointId: string
  model: string
}

function domId(roleId: string): string {
  return `role-${roleId.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}

/**
 * One row of the assignment grid: which endpoint serves a role, which model on
 * it, and a slot-level test.
 *
 * Renders no styling of its own — `className`, `style` and every other div
 * attribute pass straight through to the row element.
 */
export function RoleAssignmentRow({
  picker,
  role,
  renderStatus,
  ...rest
}: RoleAssignmentRowProps) {
  const [draft, setDraft] = useState<Draft | null>(null)

  const assignment = picker.assignmentFor(role.id)
  const endpointId = draft ? draft.endpointId : assignment?.endpointId ?? ''
  const model = draft ? draft.model : assignment?.model ?? ''

  const base = domId(role.id)
  const endpointFieldId = `${base}-endpoint`
  const modelFieldId = `${base}-model`
  const descriptionId = `${base}-description`

  const listing = endpointId !== '' && picker.listing.includes(endpointId)
  const options = picker
    .modelsForRole(role.id)
    .filter((m) => m.endpointId === endpointId)

  // An endpoint that is down lists nothing, and a stored assignment would then
  // disappear from the select and read as "never configured".
  const orphaned = model !== '' && !options.some((m) => m.id === model)

  const endpointName = picker.endpointFor(endpointId)?.name ?? ''
  const result = picker.testResults[role.id]
  const testing = picker.testing === role.id

  const chooseEndpoint = (next: string) => {
    if (next === '') {
      setDraft(null)
      void picker.clearRole(role.id)
      return
    }
    // The previous model almost never exists on a different endpoint, so the
    // role stays unwritten until the user names one.
    setDraft({ endpointId: next, model: '' })
  }

  const chooseModel = async (next: string) => {
    if (next === '') {
      setDraft(null)
      await picker.clearRole(role.id)
      return
    }
    setDraft({ endpointId, model: next })
    await picker.assignRole(role.id, endpointId, next)
    // Falling back to stored config means a write the host rejected visibly
    // reverts rather than leaving a selection nothing saved.
    setDraft(null)
  }

  const summary = model
    ? `${role.label}: ${model}${endpointName ? ` on ${endpointName}` : ''}.`
    : `${role.label}: not assigned.`

  return (
    <div data-role-id={role.id} data-assigned={model ? 'yes' : 'no'} {...rest}>
      <label htmlFor={endpointFieldId}>{role.label}</label>
      <p id={descriptionId}>{role.description}</p>

      <select
        id={endpointFieldId}
        value={endpointId}
        aria-describedby={descriptionId}
        onChange={(event) => chooseEndpoint(event.target.value)}
      >
        <option value="" disabled={!role.optional}>
          {role.optional ? 'None' : 'Choose an endpoint'}
        </option>
        {picker.chatCapableEndpoints.map((candidate) => (
          <option key={candidate.id} value={candidate.id}>
            {candidate.name}
          </option>
        ))}
      </select>

      <select
        id={modelFieldId}
        value={model}
        aria-label={`Model for ${role.label}`}
        aria-describedby={descriptionId}
        aria-invalid={!model && !role.optional}
        aria-busy={listing}
        disabled={listing || endpointId === ''}
        onChange={(event) => void chooseModel(event.target.value)}
      >
        <option value="" disabled={!role.optional}>
          {role.optional ? 'None' : 'Choose a model'}
        </option>
        {orphaned ? <option value={model}>{model}</option> : null}
        {options.map((candidate) => (
          <option
            key={`${candidate.endpointId}:${candidate.id}`}
            value={candidate.id}
          >
            {candidate.name}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={() => void picker.testModel(role.id)}
        disabled={testing || model === '' || endpointId === ''}
      >
        {testing ? 'Testing…' : 'Test'}
      </button>

      {/* Rendered on every pass: a live region inserted at the same moment as
          its text is not reliably announced. */}
      <div role="status" aria-live="polite">
        <span>{summary}</span>
        {renderStatus ? (
          renderStatus(result)
        ) : result ? (
          <span data-result={result.ok ? 'ok' : 'failed'}>
            {result.ok ? '✓' : '✕'} {result.message}
          </span>
        ) : null}
      </div>
    </div>
  )
}
