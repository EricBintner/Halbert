// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ExternalLink, ShieldCheck, AlertTriangle, FileText, BookOpen, Boxes, Cpu } from 'lucide-react'
import { apiUrl } from '@/lib/apiBase'

const API_BASE = apiUrl('/api')

interface RagSource {
  name: string
  documents: number
  license: string
  license_url: string
  upstream: string
  attribution: string
  mac_build: boolean
  commercial_ok: boolean
}

interface SoftwareDep {
  name: string
  license: string
  purpose: string
  language: string
}

interface FoundationModel {
  name: string
  license: string
  notice: string
  license_id?: string | null
  license_url?: string | null
  /** The runtime served no licence text, so any notice it requires is unmet. */
  unknown_license?: boolean
}

interface LegalNotices {
  project: {
    name: string
    license: string
    license_url: string
    copyright: string
    source: string
  }
  rag_sources: RagSource[]
  software_dependencies: SoftwareDep[]
  foundation_models: FoundationModel[]
  /** ok | no_models | runtime_unreachable — why the list is what it is. */
  foundation_models_status?: string
  foundation_models_detail?: string
  legal_docs: Record<string, string>
}

interface LegalNoticesModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * LegalNoticesModal — "About & Third-Party Notices" panel (LEG-MOD-01).
 *
 * Fetches the structured third-party license manifest from
 * GET /api/legal/notices and renders the project license, RAG source
 * attributions, software dependency licenses, and foundation model
 * attribution notices. Satisfies the attribution requirements of the
 * permissive licenses (MIT, BSD, Apache 2.0, CC BY) bundled with Halbert.
 */
export function LegalNoticesModal({ open, onOpenChange }: LegalNoticesModalProps) {
  const [notices, setNotices] = useState<LegalNotices | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'project' | 'rag' | 'software' | 'models'>('project')

  useEffect(() => {
    if (!open || notices) return
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}/legal/notices`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then((data: LegalNotices) => setNotices(data))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [open, notices])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5" />
            About & Third-Party Notices
          </DialogTitle>
          <DialogDescription>
            Licenses and attributions for Halbert and its bundled content.
          </DialogDescription>
        </DialogHeader>

        {/* Tab bar */}
        <div className="flex gap-1 border-b">
          {([
            ['project', 'Project', Cpu],
            ['rag', 'RAG Sources', BookOpen],
            ['software', 'Software', Boxes],
            ['models', 'Models', FileText],
          ] as const).map(([key, label, Icon]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px flex items-center gap-1.5 transition-colors ${
                tab === key
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        <div className="overflow-y-auto flex-1 py-4 space-y-4">
          {loading && <p className="text-sm text-muted-foreground">Loading notices…</p>}
          {error && (
            <p className="text-sm text-destructive">Failed to load notices: {error}</p>
          )}

          {notices && tab === 'project' && (
            <div className="space-y-4">
              <div>
                <h4 className="font-medium mb-1">{notices.project.name}</h4>
                <p className="text-sm text-muted-foreground">{notices.project.copyright}</p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-muted-foreground">License</p>
                  <a href={notices.project.license_url} target="_blank" rel="noopener noreferrer"
                     className="font-medium text-primary hover:underline inline-flex items-center gap-1">
                    {notices.project.license}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
                <div>
                  <p className="text-muted-foreground">Source</p>
                  <a href={notices.project.source} target="_blank" rel="noopener noreferrer"
                     className="font-medium text-primary hover:underline inline-flex items-center gap-1">
                    GitHub
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
              <div>
                <h5 className="text-sm font-medium mb-2">Legal documents</h5>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(notices.legal_docs).map(([key, path]) => (
                    <Badge key={key} variant="outline" className="font-mono text-xs">
                      {path}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          )}

          {notices && tab === 'rag' && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground mb-3">
                The Halbert RAG corpus contains content under multiple upstream
                licenses. Attribution is required for all sources.
              </p>
              {notices.rag_sources.map(s => (
                <div key={s.name} className="rounded-md border p-3 space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-sm font-medium">{s.name}</span>
                    <div className="flex gap-1.5">
                      <Badge variant="secondary" className="text-xs">{s.documents.toLocaleString()} docs</Badge>
                      {!s.commercial_ok && (
                        <Badge variant="destructive" className="text-xs">
                          <AlertTriangle className="h-3 w-3 mr-1" />
                          Non-commercial
                        </Badge>
                      )}
                      {!s.mac_build && (
                        <Badge variant="outline" className="text-xs">macOS build excluded</Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground">License:</span>
                    {s.license_url ? (
                      <a href={s.license_url} target="_blank" rel="noopener noreferrer"
                         className="text-primary hover:underline inline-flex items-center gap-1">
                        {s.license}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : (
                      <span>{s.license}</span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{s.attribution}</p>
                </div>
              ))}
            </div>
          )}

          {notices && tab === 'software' && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground mb-3">
                Third-party software libraries bundled with or depended on by Halbert.
              </p>
              <div className="rounded-md border overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-muted">
                    <tr>
                      <th className="text-left p-2 font-medium">Package</th>
                      <th className="text-left p-2 font-medium">License</th>
                      <th className="text-left p-2 font-medium">Purpose</th>
                      <th className="text-left p-2 font-medium">Lang</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notices.software_dependencies.map(d => (
                      <tr key={d.name} className="border-t">
                        <td className="p-2 font-mono">{d.name}</td>
                        <td className="p-2">{d.license}</td>
                        <td className="p-2 text-muted-foreground">{d.purpose}</td>
                        <td className="p-2"><Badge variant="outline" className="text-xs">{d.language}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {notices && tab === 'models' && (
            <div className="space-y-2">
              {/* The models named here are the ones THIS machine serves, read
                  from the licence text its runtime ships with the weights.
                  Halbert's own source names no model: a list baked in here
                  would be a licence claim about models the reader may never
                  have installed, while saying nothing about the ones they
                  have. */}
              <p className="text-xs text-muted-foreground mb-3">
                Models this machine can serve, and the licence each one's
                runtime reports. Some licences require the notice shown to
                appear on a user-facing page while the model is in use.
              </p>

              {notices.foundation_models_status === 'runtime_unreachable' && (
                <div className="rounded-md border border-dashed p-3">
                  <p className="text-xs text-muted-foreground">
                    No local model runtime answered, so the licences of the
                    models this machine serves could not be read. This is not a
                    statement that there are none.
                  </p>
                </div>
              )}

              {notices.foundation_models_status === 'no_models' && (
                <div className="rounded-md border border-dashed p-3">
                  <p className="text-xs text-muted-foreground">
                    The model runtime is reachable and serving no models.
                  </p>
                </div>
              )}

              {notices.foundation_models.map(m => (
                <div key={m.name} className="rounded-md border p-3 space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-sm break-all">{m.name}</span>
                    <Badge
                      variant={m.unknown_license ? 'outline' : 'secondary'}
                      className="text-xs shrink-0"
                    >
                      {m.license}
                    </Badge>
                  </div>
                  {m.unknown_license ? (
                    <p className="text-xs text-muted-foreground">
                      The runtime supplied no licence text for this model. If its
                      licence requires a notice, it is not being shown.
                    </p>
                  ) : m.notice ? (
                    <p className="text-xs text-muted-foreground italic">"{m.notice}"</p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      This licence asks for no user-facing notice.
                    </p>
                  )}
                </div>
              ))}

              {notices.foundation_models_detail && (
                <p className="text-xs text-muted-foreground pt-1">
                  {notices.foundation_models_detail}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2 border-t">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
