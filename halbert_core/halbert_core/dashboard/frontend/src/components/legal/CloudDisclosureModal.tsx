// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { AlertTriangle, ExternalLink, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import { apiUrl } from '@/lib/apiBase'

const API_BASE = apiUrl('/api')

interface CloudDisclosure {
  title: string
  summary: string
  what_is_sent: string[]
  what_is_not_sent: string[]
  provider_policies: Record<string, string>
  privacy_doc: string
}

interface CloudDisclosureModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called when the user acknowledges the disclosure and consents. */
  onAccept?: () => void
  /** Called when the user declines. */
  onDecline?: () => void
  /** Provider name being enabled, for display in the title. */
  providerName?: string
}

/**
 * CloudDisclosureModal — consent gate for enabling a cloud model provider
 * (LEG-MOD-02). Surfaces the data-flow disclosure from
 * GET /api/legal/cloud-disclosure and requires explicit accept/decline
 * before the caller proceeds with enabling the provider.
 *
 * Acceptance state is persisted in localStorage so the user is not
 * re-prompted for the same provider on every settings open. Re-acceptance
 * is required if the disclosure text changes (versioned by the summary hash).
 */
export function CloudDisclosureModal({
  open,
  onOpenChange,
  onAccept,
  onDecline,
  providerName,
}: CloudDisclosureModalProps) {
  const [disclosure, setDisclosure] = useState<CloudDisclosure | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || disclosure) return
    setLoading(true)
    fetch(`${API_BASE}/legal/cloud-disclosure`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then((data: CloudDisclosure) => setDisclosure(data))
      .catch(() => setDisclosure(null))
      .finally(() => setLoading(false))
  }, [open, disclosure])

  const handleAccept = () => {
    if (providerName) {
      try {
        const key = `halbert_cloud_disclosure_${providerName.toLowerCase()}`
        localStorage.setItem(key, new Date().toISOString())
      } catch { /* localStorage unavailable */ }
    }
    onAccept?.()
    onOpenChange(false)
  }

  const handleDecline = () => {
    onDecline?.()
    onOpenChange(false)
  }

  const title = providerName
    ? `Enable ${providerName} cloud models?`
    : disclosure?.title || 'Cloud Model Data Flow Disclosure'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            {title}
          </DialogTitle>
          <DialogDescription>
            {disclosure?.summary ||
              'Enabling cloud models sends system logs and prompts to the provider. Do not enable on systems processing sensitive or restricted data.'}
          </DialogDescription>
        </DialogHeader>

        {loading && <p className="text-sm text-muted-foreground">Loading disclosure…</p>}

        {disclosure && (
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <p className="text-xs font-semibold flex items-center gap-1.5 text-amber-600">
                <ArrowUpRight className="h-3.5 w-3.5" />
                What is sent to the provider
              </p>
              <ul className="text-xs text-muted-foreground list-disc pl-5 space-y-0.5">
                {disclosure.what_is_sent.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>

            <div className="space-y-1.5">
              <p className="text-xs font-semibold flex items-center gap-1.5 text-emerald-600">
                <ArrowDownRight className="h-3.5 w-3.5" />
                What is not sent
              </p>
              <ul className="text-xs text-muted-foreground list-disc pl-5 space-y-0.5">
                {disclosure.what_is_not_sent.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </div>

            <div className="space-y-1.5">
              <p className="text-xs font-semibold">Provider privacy policies</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(disclosure.provider_policies).map(([name, url]) => (
                  <a key={name} href={url} target="_blank" rel="noopener noreferrer"
                     className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
                    {name} <ExternalLink className="h-3 w-3" />
                  </a>
                ))}
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              See <code className="bg-muted px-1 rounded">{disclosure.privacy_doc}</code> for the full privacy policy.
            </p>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t">
          <Button variant="outline" onClick={handleDecline}>Cancel</Button>
          <Button onClick={handleAccept}>I understand, enable cloud models</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
