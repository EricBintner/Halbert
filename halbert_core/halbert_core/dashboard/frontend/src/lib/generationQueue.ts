// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Generation queue for AI-produced service explanations/diagnoses.
 *
 * Serializes requests to the local LLM (one generation at a time), caches
 * results, and notifies subscribers so pages can re-render when a result
 * lands. Diagnoses are cached with the service status they were generated
 * against, so a status change invalidates them.
 *
 * Reconstructed 2026-08-22 (original src/lib/ was never committed).
 */

import { apiUrl } from './apiBase'

export type GenerationKind = 'explanation' | 'diagnosis'

const DIAGNOSIS_CACHE_TTL_MS = 5 * 60 * 1000

interface DiagnosisCacheEntry {
  text: string
  status: string
  timestamp: number
}

class GenerationQueue {
  private results = new Map<string, string>()
  private pending = new Set<string>()
  private diagnosisCache = new Map<string, DiagnosisCacheEntry>()
  private listeners = new Set<() => void>()
  private running = false
  private queue: Array<{ name: string; kind: GenerationKind; status?: string }> = []

  private key(name: string, kind: GenerationKind): string {
    return `${kind}:${name}`
  }

  subscribe(callback: () => void): () => void {
    this.listeners.add(callback)
    return () => {
      this.listeners.delete(callback)
    }
  }

  private notify(): void {
    this.listeners.forEach(cb => cb())
  }

  getPendingCount(): number {
    return this.pending.size
  }

  hasPending(name: string, kind: GenerationKind): boolean {
    return this.pending.has(this.key(name, kind))
  }

  getResult(name: string, kind: GenerationKind): string | null {
    return this.results.get(this.key(name, kind)) ?? null
  }

  getCachedDiagnosis(name: string, status: string): string | null {
    const entry = this.diagnosisCache.get(name)
    if (!entry) return null
    if (entry.status !== status) return null
    if (Date.now() - entry.timestamp > DIAGNOSIS_CACHE_TTL_MS) {
      this.diagnosisCache.delete(name)
      return null
    }
    return entry.text
  }

  enqueue(name: string, kind: GenerationKind, status?: string): void {
    const k = this.key(name, kind)
    if (this.pending.has(k)) return
    this.pending.add(k)
    this.queue.push({ name, kind, status })
    this.notify()
    void this.processNext()
  }

  private async processNext(): Promise<void> {
    if (this.running) return
    const item = this.queue.shift()
    if (!item) return

    this.running = true
    const k = this.key(item.name, item.kind)

    try {
      const endpoint =
        item.kind === 'explanation'
          ? `/api/services/${encodeURIComponent(item.name)}/explain`
          : `/api/services/${encodeURIComponent(item.name)}/diagnose`

      const res = await fetch(apiUrl(endpoint), { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        const text: string = item.kind === 'explanation' ? data.explanation : data.diagnosis
        if (typeof text === 'string' && text) {
          this.results.set(k, text)
          if (item.kind === 'diagnosis') {
            this.diagnosisCache.set(item.name, {
              text,
              status: item.status ?? '',
              timestamp: Date.now(),
            })
          }
        }
      } else {
        console.warn(`Generation ${item.kind} for ${item.name} failed (${res.status})`)
      }
    } catch (err) {
      console.warn(`Generation ${item.kind} for ${item.name} errored:`, err)
    } finally {
      this.pending.delete(k)
      this.running = false
      this.notify()
      void this.processNext()
    }
  }
}

export const generationQueue = new GenerationQueue()
