/**
 * Development Page - Development environment overview.
 * 
 * Phase 16: Development Environment
 * Shows installed languages, tools, projects, and provides dev-focused AI assistance.
 */

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { AIAnalysisPanel } from '@/components/AIAnalysisPanel'
import {
  Code2,
  RefreshCw,
  FolderGit2,
  Package,
  AlertTriangle,
  Wrench,
  Layers,
  GitBranch,
  Clock,
  Box,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface LanguageInfo {
  name: string
  version: string
  path: string
  icon?: string
}

interface ToolInfo {
  name: string
  version: string
  path: string
}

interface ProjectInfo {
  name: string
  path: string
  type: 'git' | 'node' | 'python' | 'rust' | 'go' | 'unknown'
  languages: string[]
  last_modified: string
  git_branch?: string
  git_status?: 'clean' | 'dirty' | 'untracked'
}

interface VersionManagerInfo {
  name: string
  type: string
  path: string
  versions: string[]
  total_versions: number
  current: string | null
  lts_available: string | null
}

interface VirtualEnvInfo {
  name: string
  type: 'venv' | 'conda' | 'poetry'
  path: string
  project: string | null
  project_path: string | null
  python_version: string | null
  package_count: number | null
}

interface DevData {
  languages: LanguageInfo[]
  tools: ToolInfo[]
  projects: ProjectInfo[]
  package_managers: string[]
  version_managers: VersionManagerInfo[]
  virtual_environments: VirtualEnvInfo[]
  stats: {
    total_languages: number
    total_tools: number
    total_projects: number
    total_version_managers: number
    total_virtual_environments: number
  }
}

// Language color classes for visual distinction without emojis
const languageColors: Record<string, string> = {
  python: 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400',
  python3: 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400',
  node: 'bg-green-500/20 text-green-600 dark:text-green-400',
  nodejs: 'bg-green-500/20 text-green-600 dark:text-green-400',
  rust: 'bg-orange-500/20 text-orange-600 dark:text-orange-400',
  rustc: 'bg-orange-500/20 text-orange-600 dark:text-orange-400',
  go: 'bg-cyan-500/20 text-cyan-600 dark:text-cyan-400',
  java: 'bg-red-500/20 text-red-600 dark:text-red-400',
  ruby: 'bg-red-500/20 text-red-600 dark:text-red-400',
  php: 'bg-purple-500/20 text-purple-600 dark:text-purple-400',
  perl: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
  lua: 'bg-indigo-500/20 text-indigo-600 dark:text-indigo-400',
  r: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
  julia: 'bg-purple-500/20 text-purple-600 dark:text-purple-400',
  elixir: 'bg-purple-500/20 text-purple-600 dark:text-purple-400',
  clojure: 'bg-green-500/20 text-green-600 dark:text-green-400',
  scala: 'bg-red-500/20 text-red-600 dark:text-red-400',
  kotlin: 'bg-orange-500/20 text-orange-600 dark:text-orange-400',
  swift: 'bg-orange-500/20 text-orange-600 dark:text-orange-400',
  dotnet: 'bg-purple-500/20 text-purple-600 dark:text-purple-400',
  deno: 'bg-gray-500/20 text-gray-600 dark:text-gray-400',
  bun: 'bg-amber-500/20 text-amber-600 dark:text-amber-400',
}

const projectTypeIcons: Record<string, React.ReactNode> = {
  git: <GitBranch className="h-4 w-4" />,
  node: <Package className="h-4 w-4" />,
  python: <Code2 className="h-4 w-4" />,
  rust: <Layers className="h-4 w-4" />,
  go: <Code2 className="h-4 w-4" />,
  unknown: <FolderGit2 className="h-4 w-4" />,
}

export function Development() {
  const [data, setData] = useState<DevData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const loadDevData = async () => {
    try {
      const response = await fetch('/api/development/info')
      if (!response.ok) throw new Error('Failed to load development info')
      const result = await response.json()
      setData(result)
      setError(null)
    } catch (err) {
      setError('Failed to load development environment information')
      console.error(err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadDevData()
  }, [])

  const handleRefresh = () => {
    setRefreshing(true)
    loadDevData()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Development</h1>
            <p className="text-muted-foreground">Development environment overview</p>
          </div>
        </div>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-8">
              <Code2 className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">{error || 'No development information available'}</p>
              <Button variant="outline" className="mt-4" onClick={handleRefresh}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Retry
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Development</h1>
          <p className="text-muted-foreground">
            {data.stats.total_languages} languages • {data.stats.total_tools} tools
            {data.stats.total_version_managers > 0 && ` • ${data.stats.total_version_managers} version managers`}
            {data.stats.total_virtual_environments > 0 && ` • ${data.stats.total_virtual_environments} envs`}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
          <RefreshCw className={cn("h-4 w-4 mr-2", refreshing && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-500/10 rounded-lg">
                <Code2 className="h-5 w-5 text-blue-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{data.stats.total_languages}</p>
                <p className="text-xs text-muted-foreground">Languages</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-500/10 rounded-lg">
                <Wrench className="h-5 w-5 text-purple-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{data.stats.total_tools}</p>
                <p className="text-xs text-muted-foreground">Tools</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-500/10 rounded-lg">
                <FolderGit2 className="h-5 w-5 text-green-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{data.stats.total_projects}</p>
                <p className="text-xs text-muted-foreground">Projects</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Languages */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Code2 className="h-5 w-5" />
            Languages & Runtimes
          </CardTitle>
          <CardDescription>Installed programming languages and their versions</CardDescription>
        </CardHeader>
        <CardContent>
          {data.languages.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">No programming languages detected</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {data.languages.map((lang) => (
                <div 
                  key={lang.name}
                  className="flex items-center gap-3 p-3 rounded-lg border bg-card hover:bg-muted/50 transition-colors"
                >
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center font-bold text-sm",
                    languageColors[lang.name.toLowerCase()] || 'bg-muted text-muted-foreground'
                  )}>
                    {lang.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium capitalize truncate">{lang.name}</p>
                    <p className="text-xs text-muted-foreground truncate">{lang.version}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tools */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wrench className="h-5 w-5" />
            Development Tools
          </CardTitle>
          <CardDescription>Build tools, package managers, and utilities</CardDescription>
        </CardHeader>
        <CardContent>
          {data.tools.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">No development tools detected</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
              {data.tools.map((tool) => (
                <div 
                  key={tool.name}
                  className="flex items-center gap-2 p-2 rounded-lg border text-sm"
                >
                  <span className="font-medium">{tool.name}</span>
                  <span className="text-xs text-muted-foreground ml-auto">{tool.version}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Version Managers */}
      {data.version_managers && data.version_managers.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="h-5 w-5" />
              Version Managers
            </CardTitle>
            <CardDescription>Manage multiple versions of languages and runtimes</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {data.version_managers.map((vm) => (
                <div key={vm.name} className="p-4 rounded-lg border bg-card">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "w-10 h-10 rounded-lg flex items-center justify-center font-bold text-sm",
                        languageColors[vm.type] || 'bg-muted text-muted-foreground'
                      )}>
                        {vm.name.split('-')[0].slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <p className="font-medium">{vm.name}</p>
                        <p className="text-xs text-muted-foreground">{vm.path}</p>
                      </div>
                    </div>
                    {vm.current && (
                      <Badge variant="default" className="text-xs">
                        Current: {vm.current}
                      </Badge>
                    )}
                  </div>
                  
                  {vm.versions.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs text-muted-foreground">
                        {vm.total_versions} version{vm.total_versions !== 1 ? 's' : ''} installed:
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {vm.versions.map((version) => (
                          <Badge
                            key={version}
                            variant={version === vm.current ? "default" : "outline"}
                            className="text-xs"
                          >
                            {version}
                          </Badge>
                        ))}
                        {vm.total_versions > vm.versions.length && (
                          <span className="text-xs text-muted-foreground">
                            +{vm.total_versions - vm.versions.length} more
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Virtual Environments */}
      {data.virtual_environments && data.virtual_environments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Box className="h-5 w-5" />
              Virtual Environments
            </CardTitle>
            <CardDescription>Python venvs, conda environments, and project isolations</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {data.virtual_environments.slice(0, 15).map((env) => (
                <div 
                  key={env.path}
                  className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "w-8 h-8 rounded flex items-center justify-center text-xs font-bold",
                      env.type === 'conda' ? 'bg-green-500/20 text-green-600' :
                      env.type === 'poetry' ? 'bg-purple-500/20 text-purple-600' :
                      'bg-yellow-500/20 text-yellow-600'
                    )}>
                      {env.type === 'conda' ? 'C' : env.type === 'poetry' ? 'P' : 'V'}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{env.name}</p>
                        <Badge variant="outline" className="text-xs">
                          {env.type}
                        </Badge>
                        {env.python_version && (
                          <Badge variant="secondary" className="text-xs">
                            Python {env.python_version}
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground truncate max-w-md">
                        {env.project ? `Project: ${env.project}` : env.path}
                      </p>
                    </div>
                  </div>
                  {env.package_count !== null && env.package_count > 0 && (
                    <span className="text-xs text-muted-foreground">
                      {env.package_count} packages
                    </span>
                  )}
                </div>
              ))}
              {data.virtual_environments.length > 15 && (
                <p className="text-xs text-muted-foreground text-center pt-2">
                  +{data.virtual_environments.length - 15} more environments
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Projects (if any discovered) */}
      {data.projects.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FolderGit2 className="h-5 w-5" />
              Recent Projects
            </CardTitle>
            <CardDescription>Git repositories and project directories</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {data.projects.slice(0, 10).map((project) => (
                <div 
                  key={project.path}
                  className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-muted rounded">
                      {projectTypeIcons[project.type]}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{project.name}</p>
                        {project.git_branch && (
                          <Badge variant="outline" className="text-xs">
                            <GitBranch className="h-3 w-3 mr-1" />
                            {project.git_branch}
                          </Badge>
                        )}
                        {project.git_status === 'dirty' && (
                          <Badge variant="secondary" className="text-xs text-amber-600">
                            <AlertTriangle className="h-3 w-3 mr-1" />
                            Uncommitted
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">{project.path}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {project.last_modified}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* AI Analysis */}
      <AIAnalysisPanel
        type="development"
        title="Development"
        canAnalyze={data.languages.length > 0 || data.tools.length > 0}
        buildContext={() => {
          const parts = [`## Development Environment Analysis\n`]
          
          parts.push(`### Languages (${data.languages.length}):`)
          data.languages.forEach(lang => {
            parts.push(`- ${lang.name}: ${lang.version}`)
          })
          
          parts.push(`\n### Tools (${data.tools.length}):`)
          data.tools.forEach(tool => {
            parts.push(`- ${tool.name}: ${tool.version}`)
          })
          
          if (data.package_managers.length > 0) {
            parts.push(`\n### Package Managers:`)
            parts.push(`- ${data.package_managers.join(', ')}`)
          }
          
          if (data.version_managers && data.version_managers.length > 0) {
            parts.push(`\n### Version Managers:`)
            data.version_managers.forEach(vm => {
              parts.push(`- ${vm.name}: ${vm.total_versions} versions installed${vm.current ? ` (current: ${vm.current})` : ''}`)
              if (vm.versions.length > 0) {
                parts.push(`  Versions: ${vm.versions.slice(0, 5).join(', ')}${vm.total_versions > 5 ? '...' : ''}`)
              }
            })
          }
          
          if (data.virtual_environments && data.virtual_environments.length > 0) {
            parts.push(`\n### Virtual Environments (${data.virtual_environments.length}):`)
            data.virtual_environments.slice(0, 10).forEach(env => {
              const info: string[] = [env.type]
              if (env.python_version) info.push(`Python ${env.python_version}`)
              if (env.project) info.push(`project: ${env.project}`)
              parts.push(`- ${env.name}: ${info.join(', ')}`)
            })
            if (data.virtual_environments.length > 10) {
              parts.push(`  ... and ${data.virtual_environments.length - 10} more`)
            }
          }
          
          return parts.join('\n')
        }}
        researchQuestion="Review my development environment and suggest any missing tools or version updates."
      />
    </div>
  )
}
