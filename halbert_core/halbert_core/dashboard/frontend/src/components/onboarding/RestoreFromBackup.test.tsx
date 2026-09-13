// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * RestoreFromBackup: path → manifest preview → passphrase → restore →
 * a report that names what came back. The preview comes before the
 * passphrase — the operator confirms whose entity this is first.
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

const INSPECT = {
  entity_name: 'halbert',
  node_id: 'halbert-mac',
  created_at: '2026-09-13T12:00:00Z',
  schema_version: 1,
  file_count: 8,
  key_exported: true,
  key_custody: 'file',
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

function stubFetch(handlers: Record<string, { body: unknown; status?: number }>) {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const h = handlers[url]
    if (!h) return jsonResponse({}, 404)
    return jsonResponse(h.body, h.status ?? 200)
  }))
  return calls
}

async function fillPath(path = '/mnt/usb/halbert.halbert-backup') {
  await userEvent.type(screen.getByLabelText(/backup archive path/i), path)
  await userEvent.click(screen.getByRole('button', { name: /read backup/i }))
}

afterEach(() => vi.unstubAllGlobals())

describe('RestoreFromBackup', () => {
  it('shows the manifest preview before asking for a passphrase', async () => {
    const calls = stubFetch({
      '/api/backup/inspect': { body: INSPECT },
      '/api/backup/restore': { body: REPORT },
    })
    render(<RestoreFromBackup onRestored={vi.fn()} />)

    await fillPath()
    // The preview names the entity and its provenance — before the
    // passphrase field exists.
    expect(await screen.findByTestId('backup-preview')).toBeInTheDocument()
    expect(screen.getByText('halbert')).toBeInTheDocument()
    expect(screen.getByText(/halbert-mac/)).toBeInTheDocument()
    expect(calls.filter((c) => c.url === '/api/backup/restore')).toHaveLength(0)
  })

  it('posts archive path + passphrase and shows what came back', async () => {
    const calls = stubFetch({
      '/api/backup/inspect': { body: INSPECT },
      '/api/backup/restore': { body: REPORT },
    })
    const onRestored = vi.fn()
    render(<RestoreFromBackup onRestored={onRestored} />)

    await fillPath()
    await userEvent.type(
      await screen.findByLabelText(/backup passphrase/i), 'correct horse')
    await userEvent.click(screen.getByRole('button', { name: /^restore$/i }))

    await waitFor(() => {
      const post = calls.find((c) => c.url === '/api/backup/restore')
      expect(post?.init?.method).toBe('POST')
      expect(JSON.parse(String(post?.init?.body))).toEqual({
        archive_path: '/mnt/usb/halbert.halbert-backup',
        passphrase: 'correct horse',
      })
    })
    expect(await screen.findByText(/2,847 memories/)).toBeInTheDocument()
    expect(screen.getByText(/re-pairing/)).toBeInTheDocument()
    expect(screen.getByText(/moved\s+aside/)).toBeInTheDocument()
    expect(onRestored).not.toHaveBeenCalled()
  })

  it('says so when the archive is unreadable', async () => {
    stubFetch({
      '/api/backup/inspect': { body: { detail: 'archive unreadable' }, status: 400 },
    })
    render(<RestoreFromBackup onRestored={vi.fn()} />)
    await fillPath('/x.halbert-backup')
    expect(await screen.findByText(/unreadable/)).toBeInTheDocument()
    expect(screen.queryByTestId('backup-preview')).not.toBeInTheDocument()
  })

  it('shows the error, not a report, when restore is refused', async () => {
    stubFetch({
      '/api/backup/inspect': { body: INSPECT },
      '/api/backup/restore': { body: { detail: 'wrong passphrase' }, status: 400 },
    })
    render(<RestoreFromBackup onRestored={vi.fn()} />)
    await fillPath()
    await userEvent.type(
      await screen.findByLabelText(/backup passphrase/i), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: /^restore$/i }))
    expect(await screen.findByText(/wrong passphrase/)).toBeInTheDocument()
  })

  it('Continue fires onRestored', async () => {
    stubFetch({
      '/api/backup/inspect': { body: INSPECT },
      '/api/backup/restore': { body: REPORT },
    })
    const onRestored = vi.fn()
    render(<RestoreFromBackup onRestored={onRestored} />)
    await fillPath()
    await userEvent.type(
      await screen.findByLabelText(/backup passphrase/i), 'pw')
    await userEvent.click(screen.getByRole('button', { name: /^restore$/i }))
    await userEvent.click(await screen.findByRole('button', { name: /continue/i }))
    expect(onRestored).toHaveBeenCalled()
  })
})
