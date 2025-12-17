import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { 
  Database, Trash2, Search, ChevronRight, ChevronDown, 
  RefreshCw, MessageSquare, Cpu, FileText, Brain, Loader2 
} from 'lucide-react'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { PageHeader } from '@/components/domain'

interface Collection {
  name: string
  count: number
  known: boolean
}

interface MemoryEntry {
  id: string
  content: string
  metadata: Record<string, string>
}

const COLLECTION_INFO: Record<string, { icon: React.ReactNode; description: string }> = {
  'self_conversations': { icon: <MessageSquare className="h-4 w-4" />, description: 'Chat history for context retrieval' },
  'self_knowledge_all': { icon: <Brain className="h-4 w-4" />, description: 'Global knowledge index' },
  'self_journald': { icon: <FileText className="h-4 w-4" />, description: 'System log events' },
  'self_hwmon': { icon: <Cpu className="h-4 w-4" />, description: 'Hardware sensor readings' },
  'linux_docs': { icon: <FileText className="h-4 w-4" />, description: 'Man pages & documentation' },
  'discoveries': { icon: <Database className="h-4 w-4" />, description: 'System discoveries' },
}

export function Memory() {
  const [collections, setCollections] = useState<Collection[]>([])
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null)
  const [entries, setEntries] = useState<MemoryEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingEntries, setLoadingEntries] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [selectedEntries, setSelectedEntries] = useState<Set<string>>(new Set())
  const [clearDialogOpen, setClearDialogOpen] = useState(false)
  const [collectionToClear, setCollectionToClear] = useState<string | null>(null)

  useEffect(() => {
    loadCollections()
  }, [])

  const loadCollections = async () => {
    try {
      setLoading(true)
      const res = await fetch('/api/chat/memory/collections')
      const data = await res.json()
      if (data.status === 'ok') {
        setCollections(data.collections)
      }
    } catch (error) {
      console.error('Failed to load collections:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadEntries = async (collection: string) => {
    try {
      setLoadingEntries(true)
      setSelectedCollection(collection)
      setSelectedEntries(new Set())
      const res = await fetch(`/api/chat/memory/entries/${encodeURIComponent(collection)}?limit=100`)
      const data = await res.json()
      if (data.status === 'ok') {
        setEntries(data.entries)
      }
    } catch (error) {
      console.error('Failed to load entries:', error)
    } finally {
      setLoadingEntries(false)
    }
  }

  const searchMemory = async () => {
    if (!searchQuery.trim()) return
    try {
      const res = await fetch('/api/chat/memory/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          query: searchQuery, 
          k: 10,
          collection: selectedCollection 
        })
      })
      const data = await res.json()
      if (data.status === 'ok') {
        setSearchResults(data.results)
      }
    } catch (error) {
      console.error('Search failed:', error)
    }
  }

  const deleteSelected = async () => {
    if (!selectedCollection || selectedEntries.size === 0) return
    try {
      const res = await fetch(`/api/chat/memory/delete/${encodeURIComponent(selectedCollection)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entry_ids: Array.from(selectedEntries) })
      })
      const data = await res.json()
      if (data.status === 'ok') {
        // Reload entries and collections
        loadEntries(selectedCollection)
        loadCollections()
        setSelectedEntries(new Set())
      }
    } catch (error) {
      console.error('Delete failed:', error)
    }
  }

  const clearCollection = async (collection: string) => {
    try {
      const res = await fetch(`/api/chat/memory/clear/${encodeURIComponent(collection)}`, {
        method: 'POST'
      })
      const data = await res.json()
      if (data.status === 'ok') {
        loadCollections()
        if (selectedCollection === collection) {
          setEntries([])
        }
      }
    } catch (error) {
      console.error('Clear failed:', error)
    }
    setClearDialogOpen(false)
    setCollectionToClear(null)
  }

  const toggleEntry = (id: string) => {
    const newSelected = new Set(selectedEntries)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedEntries(newSelected)
  }

  const selectAll = () => {
    if (selectedEntries.size === entries.length) {
      setSelectedEntries(new Set())
    } else {
      setSelectedEntries(new Set(entries.map(e => e.id)))
    }
  }

  const totalEntries = collections.reduce((sum, c) => sum + c.count, 0)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Database className="h-8 w-8" />}
        title="Memory"
        description={`ChromaDB vector memory — ${totalEntries.toLocaleString()} total entries`}
        onScan={loadCollections}
        scanText="Refresh"
      />

      {/* Search */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Search Memory</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Input
              placeholder="Search across all memories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && searchMemory()}
            />
            <Button onClick={searchMemory}>
              <Search className="h-4 w-4 mr-2" />
              Search
            </Button>
          </div>
          {searchResults.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-sm text-muted-foreground">{searchResults.length} results</p>
              {searchResults.map((r, i) => (
                <div key={i} className="p-3 border rounded-lg text-sm">
                  <p className="line-clamp-2">{r.content}</p>
                  <div className="flex gap-2 mt-2 text-xs text-muted-foreground">
                    {r.role && <Badge variant="outline">{r.role}</Badge>}
                    {r.conversation_id && <span>Conv: {r.conversation_id.slice(0, 8)}...</span>}
                    {r.distance && <span>Distance: {r.distance.toFixed(3)}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Collections List */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-lg">Collections</CardTitle>
            <CardDescription>{collections.length} collections</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y">
              {collections.map((col) => {
                const info = COLLECTION_INFO[col.name] || { icon: <Database className="h-4 w-4" />, description: '' }
                const isSelected = selectedCollection === col.name
                return (
                  <div
                    key={col.name}
                    className={`flex items-center justify-between p-3 cursor-pointer hover:bg-accent/50 transition-colors ${isSelected ? 'bg-accent' : ''}`}
                    onClick={() => loadEntries(col.name)}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {isSelected ? <ChevronDown className="h-4 w-4 flex-shrink-0" /> : <ChevronRight className="h-4 w-4 flex-shrink-0" />}
                      {info.icon}
                      <div className="min-w-0">
                        <p className="font-medium text-sm truncate">{col.name}</p>
                        <p className="text-xs text-muted-foreground truncate">{info.description}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary">{col.count.toLocaleString()}</Badge>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          setCollectionToClear(col.name)
                          setClearDialogOpen(true)
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>

        {/* Entries View */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">
                  {selectedCollection ? `Entries: ${selectedCollection}` : 'Select a Collection'}
                </CardTitle>
                <CardDescription>
                  {entries.length > 0 ? `${entries.length} entries loaded` : 'Click a collection to browse'}
                </CardDescription>
              </div>
              {selectedEntries.size > 0 && (
                <Button variant="destructive" size="sm" onClick={deleteSelected}>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete {selectedEntries.size}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {loadingEntries ? (
              <div className="flex items-center justify-center h-32">
                <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : entries.length === 0 ? (
              <div className="text-center text-muted-foreground py-8">
                {selectedCollection ? 'No entries in this collection' : 'Select a collection to view entries'}
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center gap-2 mb-3">
                  <input
                    type="checkbox"
                    checked={selectedEntries.size === entries.length && entries.length > 0}
                    onChange={selectAll}
                    className="rounded"
                  />
                  <span className="text-sm text-muted-foreground">Select all</span>
                </div>
                <div className="max-h-[500px] overflow-y-auto space-y-2">
                  {entries.map((entry) => (
                    <div
                      key={entry.id}
                      className={`p-3 border rounded-lg text-sm ${selectedEntries.has(entry.id) ? 'border-primary bg-primary/5' : ''}`}
                    >
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={selectedEntries.has(entry.id)}
                          onChange={() => toggleEntry(entry.id)}
                          className="mt-1 rounded"
                        />
                        <div className="flex-1 min-w-0">
                          <p className="line-clamp-3 break-words">{entry.content}</p>
                          <div className="flex flex-wrap gap-2 mt-2">
                            {entry.metadata.role && (
                              <Badge variant={entry.metadata.role === 'user' ? 'default' : 'secondary'}>
                                {entry.metadata.role}
                              </Badge>
                            )}
                            {entry.metadata.page && (
                              <Badge variant="outline">{entry.metadata.page}</Badge>
                            )}
                            {entry.metadata.conversation_id && (
                              <span className="text-xs text-muted-foreground">
                                Conv: {entry.metadata.conversation_id.slice(0, 8)}...
                              </span>
                            )}
                            {entry.metadata.timestamp && (
                              <span className="text-xs text-muted-foreground">
                                {new Date(parseInt(entry.metadata.timestamp) * 1000).toLocaleString()}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Clear Confirmation Dialog */}
      <ConfirmDialog
        open={clearDialogOpen}
        onClose={() => {
          setClearDialogOpen(false)
          setCollectionToClear(null)
        }}
        onConfirm={() => collectionToClear && clearCollection(collectionToClear)}
        title="Clear Collection?"
        description={`This will permanently delete ALL entries in ${collectionToClear}.`}
        warning="This action cannot be undone."
        confirmText="Clear All"
        variant="destructive"
      />
    </div>
  )
}
