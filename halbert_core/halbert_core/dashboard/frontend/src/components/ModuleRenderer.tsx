/**
 * ModuleRenderer — renders the correct module component based on name.
 *
 * Looks up the component in a local registry (maps module name → React
 * component). Falls back to a "module not found" message.
 *
 * Phase 8 / T8b.3.
 */

import { lazy, Suspense } from 'react'
import { AlertCircle } from 'lucide-react'

// Lazy-load module components
const ConfigDiffModule = lazy(() => import('./modules/ConfigDiffModule'))
const VitalsModule = lazy(() => import('./modules/VitalsModule'))
const DriveHealthModule = lazy(() => import('./modules/DriveHealthModule'))
const EvidenceModule = lazy(() => import('./modules/EvidenceModule'))

const MODULE_REGISTRY: Record<string, React.LazyExoticComponent<React.ComponentType<any>>> = {
  'config-diff': ConfigDiffModule,
  'vitals': VitalsModule,
  'drive-health': DriveHealthModule,
  'evidence': EvidenceModule,
}

interface ModuleRendererProps {
  module: string
  props: Record<string, any>
}

export function ModuleRenderer({ module, props }: ModuleRendererProps) {
  const Component = MODULE_REGISTRY[module]

  if (!Component) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
        <AlertCircle className="h-4 w-4" />
        <span>Module "{module}" not found</span>
      </div>
    )
  }

  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
          Loading module...
        </div>
      }
    >
      <Component {...props} />
    </Suspense>
  )
}
