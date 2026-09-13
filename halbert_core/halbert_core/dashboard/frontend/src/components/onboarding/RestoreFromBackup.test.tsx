// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * RestoreFromBackup: the recovery door — archive path + passphrase, the
 * report names what came back, Continue finishes onboarding.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RestoreFromBackup } from './RestoreFromBackup'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response
}

const REPORT = {
  status: 'restored',
  entity_name: 'halbert',
  backup_date: '2026-09-13T12:00:00Z',
  memory_count: 2847,
  thread_count: 156,
  files_restored: [],
  quarantined: ['/x/being.yml.quarantined-1'],
  warnings: ['peers paired after this backup was taken need re-pairing'],
}

afterEach(() => vi.unstubAllGlobals())

describe('RestoreFromBackup', () => {
  it('posts archive path + passphrase and shows what came back', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      return jsonResponse(REPORT)
    }))
    const onRestored = vi.fn()
    render(<RestoreFromBackup onRestored={onRestored} />)

    await userEvent.type(
      screen.getByLabelText(/backup archive path/i), '/mnt/usb/halbert.halbert-backup')
    await userEvent.type(
      screen.getByLabelText(/backup passphrase/i), 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: /^restore$/i }))

    await waitFor(() => {
      const post = calls.find((c) => c.url === '/api/backup/restore')
      expect(post?.init?.method).toBe('POST')
      expect(JSON.parse(String(post?.init?.body))).toEqual({
        archive_path: '/mnt/usb/halbert.halbert-backup',
        passphrase: 'correct horse',
      })
    })
    // The report names what came back — entity, counts, warnings.
    expect(await screen.findByText(/halbert/)).toBeInTheDocument()
    expect(screen.getByText(/2,847 memories/)).toBeInTheDocument()
    expect(screen.getByText(/re-pairing/)).toBeInTheDocument()
    expect(screen.getByText(/moved\s+aside/)).toBeInTheDocument()
    expect(onRestored).not.toHaveBeenCalled()
  })

  it('shows the error, not a report, when restore is refused', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(
      { detail: 'will not decrypt — wrong passphrase' }, 400)))
    render(<RestoreFromBackup onRestored={vi.fn()} />)
    await userEvent.type(
      screen.getByLabelText(/backup archive path/i), '/x.halbert-backup')
    await userEvent.type(
      screen.getByLabelText(/backup passphrase/i), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: /^restore$/i }))
    expect(await screen.findByText(/wrong passphrase/)).toBeInTheDocument()
  })

  it('Continue fires onRestored', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(REPORT)))
    const onRestored = vi.fn()
    render(<RestoreFromBackup onRestored={onRestored} />)
    await userEvent.type(
      screen.getByLabelText(/backup archive path/i), '/x.halbert-backup')
    await userEvent.type(
      screen.getByLabelText(/backup passphrase/i), 'pw')
    await userEvent.click(screen.getByRole('button', { name: /^restore$/i }))
    await userEvent.click(await screen.findByRole('button', { name: /continue/i }))
    expect(onRestored).toHaveBeenCalled()
  })
})
