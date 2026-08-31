// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { Dispatch, SetStateAction } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DataVersionCard } from '@/components/domain'
import {
  Brain,
  BookOpen,
  Check,
  X,
  Plus,
  Zap,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Trash2,
  Database,
  ExternalLink,
  Sparkles,
} from 'lucide-react'

export interface SelfKnowledgeEntry {
  id: string
  type: string
  subject: string
  content: string
  rationale?: string
  source: string
  created_at?: string
}

export interface NewKnowledge {
  subject: string
  content: string
  rationale: string
}

export interface RagStats {
  total_docs: number
  user_docs: number
  sources: Record<string, number>
}

export interface RagIndex {
  name: string
  doc_count: number
  indexed_at: string
  source_file: string
  embedding_model: string
  build_time_seconds: number
}

export interface DocFreshness {
  last_indexed_at: string | null
  docs_at_last_index: number
  info: string
}

export interface IndexProgress {
  percent: number
  currentSource: string | null
  completed: number
  total: number
}

export interface CustomDoc {
  name: string
  source: string
  url: string
  trust_tier: number
  is_custom: boolean
}

export interface CoreSource {
  name: string
  count: number
}

export interface AddSourceResult {
  success: boolean
  message: string
  title?: string
  alreadyExists?: boolean
}

// Documentation Suggestions state (self-learning)
export interface DocSuggestion {
  doc_key: string
  doc_name: string
  doc_url: string
  doc_description: string
  doc_category: string
  discovery_id: string
  discovery_name: string
  confidence: number
  reason: string
  priority: number
}

// Trending Topics state (Phase 34 - Cutting-Edge Discovery)
export interface TrendingSuggestion {
  name: string
  full_name: string
  description: string
  url: string
  doc_url: string
  stars: number
  language: string
  relevance_score: number
  reason: string
  stack_match: string[]
  has_docs: boolean
}

export interface UserStack {
  runtimes: string[]
  package_managers: string[]
  tools: string[]
  editors: string[]
}

interface KnowledgeTabProps {
  // Self-knowledge
  selfKnowledge: SelfKnowledgeEntry[]
  loadingSelfKnowledge: boolean
  onLoadSelfKnowledge: () => void
  showAddKnowledge: boolean
  setShowAddKnowledge: Dispatch<SetStateAction<boolean>>
  newKnowledge: NewKnowledge
  setNewKnowledge: Dispatch<SetStateAction<NewKnowledge>>
  addingKnowledge: boolean
  onAddSelfKnowledge: () => void
  onDeleteKnowledge: (id: string) => void
  // RAG stats and indexes
  ragStats: RagStats | null
  ragIndexes: RagIndex[]
  docFreshness: DocFreshness | null
  indexing: boolean
  indexProgress: IndexProgress
  onReindex: () => void
  showDocList: boolean
  loadingDocs: boolean
  customDocs: CustomDoc[]
  coreSources: CoreSource[]
  onToggleDocList: () => void
  // Suggested documentation
  docSuggestions: DocSuggestion[]
  loadingSuggestions: boolean
  addingSuggestion: string | null
  onAddSuggestion: (docKey: string) => void
  onDismissSuggestion: (docKey: string) => void
  // Trending topics
  trendingSuggestions: TrendingSuggestion[]
  loadingTrending: boolean
  userStack: UserStack | null
  showTrending: boolean
  setShowTrending: Dispatch<SetStateAction<boolean>>
  trendingEnabled: boolean
  setTrendingEnabled: Dispatch<SetStateAction<boolean>>
  onLoadTrendingSuggestions: () => void
  setTrendingSuggestions: Dispatch<SetStateAction<TrendingSuggestion[]>>
  // Add custom documentation source
  showAddKnowledgeSource: boolean
  setShowAddKnowledgeSource: Dispatch<SetStateAction<boolean>>
  newSourceUrl: string
  setNewSourceUrl: Dispatch<SetStateAction<string>>
  newSourceName: string
  setNewSourceName: Dispatch<SetStateAction<string>>
  addingSource: boolean
  addSourceResult: AddSourceResult | null
  onAddKnowledgeSource: () => void
}

/** The Knowledge tab: ChromaDB, self-knowledge, and RAG sources. */
export function KnowledgeTab({
  selfKnowledge,
  loadingSelfKnowledge,
  onLoadSelfKnowledge,
  showAddKnowledge,
  setShowAddKnowledge,
  newKnowledge,
  setNewKnowledge,
  addingKnowledge,
  onAddSelfKnowledge,
  onDeleteKnowledge,
  ragStats,
  ragIndexes,
  docFreshness,
  indexing,
  indexProgress,
  onReindex,
  showDocList,
  loadingDocs,
  customDocs,
  coreSources,
  onToggleDocList,
  docSuggestions,
  loadingSuggestions,
  addingSuggestion,
  onAddSuggestion,
  onDismissSuggestion,
  trendingSuggestions,
  loadingTrending,
  userStack,
  showTrending,
  setShowTrending,
  trendingEnabled,
  setTrendingEnabled,
  onLoadTrendingSuggestions,
  setTrendingSuggestions,
  showAddKnowledgeSource,
  setShowAddKnowledgeSource,
  newSourceUrl,
  setNewSourceUrl,
  newSourceName,
  setNewSourceName,
  addingSource,
  addSourceResult,
  onAddKnowledgeSource,
}: KnowledgeTabProps) {
  return (
    <>
      {/* Data Version & Freshness - Phase 54 */}
      <DataVersionCard />

      {/* Self-Knowledge Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Brain className="h-5 w-5" />
              Self-Knowledge
            </div>
            <Button variant="ghost" size="sm" onClick={onLoadSelfKnowledge}>
              <RefreshCw className={`h-4 w-4 ${loadingSelfKnowledge ? 'animate-spin' : ''}`} />
            </Button>
          </CardTitle>
          <CardDescription>
            What Halbert knows about itself and your system. Teach it new things or edit existing knowledge.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Add new knowledge - collapsible */}
            <div className="space-y-3">
              <button
                className="font-medium flex items-center gap-2 hover:text-primary transition-colors w-full text-left"
                onClick={() => setShowAddKnowledge(!showAddKnowledge)}
              >
                <Plus className={`h-4 w-4 transition-transform ${showAddKnowledge ? 'rotate-45' : ''}`} />
                Teach Something New
                <ChevronDown className={`h-4 w-4 ml-auto transition-transform ${showAddKnowledge ? 'rotate-180' : ''}`} />
              </button>
              {showAddKnowledge && (
                <div className="p-4 border rounded-lg space-y-3 bg-muted/30">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Subject</Label>
                      <Input
                        value={newKnowledge.subject}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewKnowledge({...newKnowledge, subject: e.target.value})}
                        placeholder="e.g., bcachefs pool, main server"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Content</Label>
                      <Input
                        value={newKnowledge.content}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewKnowledge({...newKnowledge, content: e.target.value})}
                        placeholder="What is it? What does it do?"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>Why does it exist? (optional)</Label>
                    <Input
                      value={newKnowledge.rationale}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewKnowledge({...newKnowledge, rationale: e.target.value})}
                      placeholder="The reason or purpose behind this..."
                    />
                  </div>
                  <Button
                    onClick={onAddSelfKnowledge}
                    disabled={!newKnowledge.subject || !newKnowledge.content || addingKnowledge}
                  >
                    {addingKnowledge ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Plus className="h-4 w-4 mr-2" />}
                    Save Knowledge
                  </Button>
                </div>
              )}
            </div>

            {/* Knowledge entries list */}
            {loadingSelfKnowledge ? (
              <div className="p-4 text-center text-muted-foreground">
                <RefreshCw className="h-4 w-4 animate-spin inline mr-2" />
                Loading...
              </div>
            ) : selfKnowledge.length === 0 ? (
              <div className="p-4 text-center text-muted-foreground border rounded-lg">
                No self-knowledge yet. Teach Halbert something!
              </div>
            ) : (
              <div className="border rounded-lg divide-y max-h-96 overflow-y-auto">
                {selfKnowledge.map((entry) => (
                  <div key={entry.id} className="p-3 hover:bg-muted/30 transition-colors">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="outline" className="text-xs">{entry.type.replace(/_/g, ' ')}</Badge>
                          <span className="font-medium">{entry.subject}</span>
                        </div>
                        <p className="text-sm text-muted-foreground line-clamp-2">{entry.content}</p>
                        {entry.rationale && entry.rationale !== entry.content && (
                          <p className="text-xs text-muted-foreground mt-1 italic">Why: {entry.rationale}</p>
                        )}
                      </div>
                      {entry.source === 'user' && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive hover:text-destructive"
                          onClick={() => onDeleteKnowledge(entry.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* RAG Knowledge Sources Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Documentation (RAG)
          </CardTitle>
          <CardDescription>
            Linux documentation and knowledge sources the AI uses for context
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Stats summary */}
            <div className="p-4 bg-muted/50 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium">Indexed Sources</h4>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={onReindex}
                    disabled={indexing}
                  >
                    {indexing ? (
                      <><RefreshCw className="h-4 w-4 mr-1 animate-spin" />Indexing...</>
                    ) : (
                      <><Database className="h-4 w-4 mr-1" />Re-index</>
                    )}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={onToggleDocList}>
                    {showDocList ? <ChevronUp className="h-4 w-4 mr-1" /> : <ChevronDown className="h-4 w-4 mr-1" />}
                    {showDocList ? 'Hide' : 'View All'}
                  </Button>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Total Documents</p>
                  <p className="font-medium">{ragStats?.total_docs?.toLocaleString() || 'Loading...'} docs</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Custom Added</p>
                  <p className="font-medium">{ragStats?.user_docs || 0} docs</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Last Indexed</p>
                  <p className="font-medium text-xs">
                    {docFreshness?.last_indexed_at
                      ? new Date(docFreshness.last_indexed_at).toLocaleDateString()
                      : 'Never'}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Updates</p>
                  <p className="font-medium text-xs text-success dark:text-success">
                    Core docs updated with releases
                  </p>
                </div>
              </div>
              {indexing && (
                <div className="mt-3 p-3 bg-info/10 rounded text-sm text-info dark:text-info">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center">
                      <RefreshCw className="h-3 w-3 mr-2 animate-spin" />
                      <span>Indexing documents...</span>
                    </div>
                    <span className="text-xs">You can navigate away safely</span>
                  </div>
                  <div className="w-full bg-info-muted dark:bg-info rounded-full h-2.5 mb-1">
                    <div
                      className="bg-info h-2.5 rounded-full transition-all duration-300"
                      style={{ width: `${indexProgress.percent}%` }}
                    ></div>
                  </div>
                  <div className="flex justify-between text-xs text-info dark:text-info">
                    <span>{indexProgress.currentSource ? `Processing: ${indexProgress.currentSource}` : 'Starting...'}</span>
                    <span>{indexProgress.percent}% ({indexProgress.completed}/{indexProgress.total} sources)</span>
                  </div>
                </div>
              )}
            </div>

            {/* Expandable document list */}
            {showDocList && (
              <div className="border rounded-lg overflow-hidden">
                <div className="max-h-80 overflow-y-auto">
                  {loadingDocs ? (
                    <div className="p-4 text-center text-muted-foreground">
                      <RefreshCw className="h-4 w-4 animate-spin inline mr-2" />
                      Loading documents...
                    </div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50 sticky top-0">
                        <tr>
                          <th className="text-left p-2 font-medium">Name</th>
                          <th className="text-right p-2 font-medium">Docs</th>
                        </tr>
                      </thead>
                      <tbody>
                        {/* Core sources first */}
                        <tr className="bg-muted/30">
                          <td colSpan={2} className="p-2 text-xs font-medium text-muted-foreground">
                            Core Knowledge Base
                          </td>
                        </tr>
                        {coreSources.map((source, i) => (
                          <tr key={`core-${i}`} className="border-t">
                            <td className="p-2">{source.name}</td>
                            <td className="p-2 text-right text-muted-foreground">{source.count.toLocaleString()}</td>
                          </tr>
                        ))}
                        {/* Custom docs below */}
                        {customDocs.length > 0 && (
                          <>
                            <tr className="border-t-2 border-muted bg-info-muted/50 dark:bg-info/20">
                              <td colSpan={2} className="p-2 text-xs font-medium text-muted-foreground">
                                Custom Added ({customDocs.length})
                              </td>
                            </tr>
                            {customDocs.map((doc, i) => (
                              <tr key={`custom-${i}`} className="border-t bg-info-muted/30 dark:bg-info/10">
                                <td className="p-2">
                                  <span className="font-medium">{doc.name}</span>
                                  {doc.url && (
                                    <a href={doc.url} target="_blank" rel="noopener noreferrer" className="ml-2 text-muted-foreground hover:text-foreground">
                                      <ExternalLink className="h-3 w-3 inline" />
                                    </a>
                                  )}
                                </td>
                                <td className="p-2 text-right">
                                  <Badge variant="outline" className="text-xs">Custom</Badge>
                                </td>
                              </tr>
                            ))}
                          </>
                        )}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}

            {/* RAG Indexes (Phase 27) */}
            {ragIndexes.length > 0 && (
              <div className="border-t pt-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-info" />
                  <span className="font-medium">Search Indexes</span>
                  <Badge variant="secondary" className="text-xs">{ragIndexes.length} indexes</Badge>
                </div>
                <div className="grid gap-2">
                  {ragIndexes.map((idx) => (
                    <div
                      key={idx.name}
                      className="flex items-center justify-between p-2 bg-info/5 border border-info/20 rounded-lg"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">{idx.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                          <Badge variant="outline" className="text-xs">{idx.doc_count.toLocaleString()} docs</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          Indexed {idx.indexed_at} • {idx.embedding_model}
                        </p>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {idx.build_time_seconds.toFixed(1)}s
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Suggested Documentation (Self-Learning) */}
            {docSuggestions.length > 0 && (
              <div className="border-t pt-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-warning" />
                    <span className="font-medium">Suggested Documentation</span>
                    <Badge variant="secondary" className="text-xs">{docSuggestions.length} found</Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">Based on your system</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Halbert detected services on your system that have documentation available.
                </p>
                <div className="space-y-2">
                  {docSuggestions.slice(0, 5).map((suggestion) => (
                    <div
                      key={suggestion.doc_key}
                      className="flex items-center justify-between p-2 bg-warning/5 border border-warning/20 rounded-lg"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">{suggestion.doc_name}</span>
                          <Badge variant="outline" className="text-xs">{suggestion.doc_category}</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground truncate">
                          {suggestion.reason}
                        </p>
                      </div>
                      <div className="flex items-center gap-1 ml-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2"
                          onClick={() => onAddSuggestion(suggestion.doc_key)}
                          disabled={addingSuggestion === suggestion.doc_key}
                        >
                          {addingSuggestion === suggestion.doc_key ? (
                            <RefreshCw className="h-3 w-3 animate-spin" />
                          ) : (
                            <Plus className="h-3 w-3" />
                          )}
                          <span className="ml-1 text-xs">Add</span>
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2 text-muted-foreground hover:text-foreground"
                          onClick={() => onDismissSuggestion(suggestion.doc_key)}
                        >
                          <X className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
                {loadingSuggestions && (
                  <div className="text-xs text-muted-foreground flex items-center gap-2">
                    <RefreshCw className="h-3 w-3 animate-spin" />
                    Loading suggestions...
                  </div>
                )}
              </div>
            )}

            {/* Trending Topics (Phase 34 - Cutting-Edge Discovery) */}
            <div className="border-t pt-4 space-y-3">
              <button
                className="font-medium flex items-center gap-2 hover:text-primary transition-colors w-full text-left"
                onClick={() => setShowTrending(!showTrending)}
              >
                <Zap className={`h-4 w-4 text-warning transition-transform ${showTrending ? '' : '-rotate-90'}`} />
                <span>Trending on GitHub</span>
                {trendingSuggestions.length > 0 && (
                  <Badge variant="secondary" className="text-xs bg-warning/10 text-warning">
                    {trendingSuggestions.length} found
                  </Badge>
                )}
                <ChevronDown className={`h-4 w-4 ml-auto transition-transform ${showTrending ? 'rotate-180' : ''}`} />
              </button>

              {showTrending && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-muted-foreground">
                      Emerging tools relevant to your tech stack
                      {userStack && (
                        <span className="ml-1">
                          ({[...userStack.runtimes, ...userStack.tools].slice(0, 3).join(', ')})
                        </span>
                      )}
                    </p>
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-2 text-xs">
                        <input
                          type="checkbox"
                          checked={trendingEnabled}
                          onChange={(e) => setTrendingEnabled(e.target.checked)}
                          className="h-3 w-3"
                        />
                        Auto-discover
                      </label>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2"
                        onClick={() => onLoadTrendingSuggestions()}
                        disabled={loadingTrending}
                      >
                        <RefreshCw className={`h-3 w-3 ${loadingTrending ? 'animate-spin' : ''}`} />
                      </Button>
                    </div>
                  </div>

                  {loadingTrending ? (
                    <div className="text-xs text-muted-foreground flex items-center gap-2 py-4">
                      <RefreshCw className="h-3 w-3 animate-spin" />
                      Fetching trending repos from GitHub...
                    </div>
                  ) : trendingSuggestions.length > 0 ? (
                    <div className="space-y-2">
                      {trendingSuggestions.slice(0, 5).map((repo) => (
                        <div
                          key={repo.full_name}
                          className="flex items-center justify-between p-2 bg-warning/5 border border-warning/20 rounded-lg"
                        >
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <a
                                href={repo.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="font-medium text-sm hover:underline flex items-center gap-1"
                              >
                                {repo.name}
                                <ExternalLink className="h-3 w-3" />
                              </a>
                              <Badge variant="outline" className="text-xs">{repo.language || 'Multi'}</Badge>
                              <span className="text-xs text-muted-foreground">⭐ {repo.stars.toLocaleString()}</span>
                            </div>
                            <p className="text-xs text-muted-foreground truncate">
                              {repo.description || repo.reason}
                            </p>
                            {repo.stack_match.length > 0 && (
                              <div className="flex items-center gap-1 mt-1">
                                <span className="text-xs text-warning">Related to:</span>
                                {repo.stack_match.slice(0, 3).map((match) => (
                                  <Badge key={match} variant="secondary" className="text-xs px-1 py-0">
                                    {match}
                                  </Badge>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-1 ml-2">
                            {repo.has_docs && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2"
                                onClick={() => window.open(repo.doc_url || repo.url, '_blank')}
                              >
                                <BookOpen className="h-3 w-3" />
                                <span className="ml-1 text-xs">Docs</span>
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2 text-muted-foreground hover:text-foreground"
                              onClick={() => setTrendingSuggestions(prev => prev.filter(s => s.full_name !== repo.full_name))}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground py-2">
                      No trending repos found for your stack. Try refreshing or check your GitHub token.
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Add custom source - collapsible */}
            <div className="border-t pt-4 space-y-4">
              <button
                className="font-medium flex items-center gap-2 hover:text-primary transition-colors w-full text-left"
                onClick={() => setShowAddKnowledgeSource(!showAddKnowledgeSource)}
              >
                <Plus className={`h-4 w-4 transition-transform ${showAddKnowledgeSource ? 'rotate-45' : ''}`} />
                Add Custom Documentation
                <ChevronDown className={`h-4 w-4 ml-auto transition-transform ${showAddKnowledgeSource ? 'rotate-180' : ''}`} />
              </button>
              {showAddKnowledgeSource && (
              <>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>URL</Label>
                  <Input
                    value={newSourceUrl}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewSourceUrl(e.target.value)}
                    placeholder="https://docs.example.com/"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Name (optional)</Label>
                  <Input
                    value={newSourceName}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewSourceName(e.target.value)}
                    placeholder="Example Documentation"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  onClick={onAddKnowledgeSource}
                  disabled={!newSourceUrl || addingSource}
                >
                  {addingSource ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Plus className="h-4 w-4 mr-2" />}
                  Add Source
                </Button>
                {addSourceResult && (
                  <Badge variant={addSourceResult.success ? "default" : addSourceResult.alreadyExists ? "secondary" : "destructive"}>
                    {addSourceResult.success ? <Check className="h-3 w-3 mr-1" /> : <X className="h-3 w-3 mr-1" />}
                    {addSourceResult.message}
                    {addSourceResult.success && addSourceResult.title && `: ${addSourceResult.title}`}
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                Add any documentation URL and Halbert will index it for context-aware responses.
                Auto-detects docs from ReadTheDocs, wikis, /docs/ paths, and more.
              </p>
              </>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  )
}