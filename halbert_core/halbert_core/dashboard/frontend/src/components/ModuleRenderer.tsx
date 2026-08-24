/**
 * ModuleRenderer — renders the correct module component based on name.
 *
 * Looks up the component in a local registry (maps module name → React
 * component). Falls back to a "module not found" message. Data-fetch errors
 * are handled inside each module; a render/code-load failure is caught by an
 * error boundary and shown as a compact "couldn't load <module>" state
 * (Suspense fallback remains for code loading).
 *
 * Phase 8 / T8b.3.
 */

import { Component, lazy, Suspense, type ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'
import { ModuleLoadError } from './modules/ModuleLoadError'

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

interface ModuleErrorBoundaryProps {
  moduleName: string
  children: ReactNode
}

class ModuleErrorBoundary extends Component<ModuleErrorBoundaryProps, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(err: unknown) {
    console.error(`Module "${this.props.moduleName}" failed to render:`, err)
  }

  render() {
    if (this.state.failed) {
      return <ModuleLoadError module={this.props.moduleName} />
    }
    return this.props.children
  }
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
    <ModuleErrorBoundary moduleName={module}>
      <Suspense
        fallback={
          <div className="flex items-center justify-center rounded-lg border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
            Loading module...
          </div>
        }
      >
        <Component {...props} />
      </Suspense>
    </ModuleErrorBoundary>
  )
}
