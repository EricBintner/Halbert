// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * U6/S1: which model roles a variant offers.
 *
 * The secure slot is a sysadmin-only role: a home instance runs no local
 * model and routes a sensitive turn through the fail-closed chain instead,
 * so the settings drawer and the composer must not offer a slot there that
 * no runtime will ever answer. The filter runs host-side — the picker
 * package stays free of role names by design.
 */
import { describe, it, expect } from 'vitest'
import { HALBERT_MODEL_ROLES, halbertRolesForVariant } from './halbertModelRoles'

const ids = (roles: { id: string }[]) => roles.map((r) => r.id)

describe('halbertRolesForVariant', () => {
  it('keeps every role on the sysadmin variant', () => {
    expect(ids(halbertRolesForVariant('sysadmin'))).toEqual([
      'chat_model',
      'specialist_model',
      'vision_model',
      'secure_model',
    ])
  })

  it('hides the secure role on the home variant', () => {
    expect(ids(halbertRolesForVariant('home'))).toEqual([
      'chat_model',
      'specialist_model',
      'vision_model',
    ])
  })

  it('keeps every role when the variant cannot be resolved', () => {
    // The tag list is authoritative once a variant is known, but a variant
    // that never arrived (route failed, payload malformed) must not shrink
    // the picker — that would take slots away from the machine that needs
    // them because one route answered nothing.
    expect(ids(halbertRolesForVariant(null))).toEqual(ids(HALBERT_MODEL_ROLES))
    expect(ids(halbertRolesForVariant(undefined))).toEqual(ids(HALBERT_MODEL_ROLES))
    expect(ids(halbertRolesForVariant(''))).toEqual(ids(HALBERT_MODEL_ROLES))
  })

  it('hides the secure role on a variant this build has never heard of', () => {
    // The tag list says which variants offer the slot; one that is not on it
    // does not. A future variant opts in by adding itself to the list.
    expect(ids(halbertRolesForVariant('some-future-variant'))).toEqual([
      'chat_model',
      'specialist_model',
      'vision_model',
    ])
  })

  it('tags only the secure role with variants', () => {
    // The other three roles exist on every instance; a stray tag here would
    // silently retire a slot the runtime still reads.
    expect(HALBERT_MODEL_ROLES.filter((r) => r.variants)).toEqual([
      expect.objectContaining({ id: 'secure_model', variants: ['sysadmin'] }),
    ])
  })
})