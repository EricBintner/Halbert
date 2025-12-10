import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { getMemoryStats, getDocuments, type MemoryStats, type Document } from '@/lib/tauri'
import { Database, FileText, FileCode, BookOpen, HardDrive } from 'lucide-react'

export function Memory() {
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
    // Poll every 10 seconds
    const interval = setInterval(loadData, 10000)
    return () => clearInterval(interval)
  }, [])

  const loadData = async () => {
    try {
      const [memStats, docs] = await Promise.all([
        getMemoryStats(),
        getDocuments()
      ])
      setStats(memStats)
      setDocuments(docs)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load memory data:', error)
      setLoading(false)
    }
  }

  const getDocTypeIcon = (type: string) => {
    switch (type) {
      case 'markdown':
        return <FileText className="h-4 w-4" />
      case 'manpage':
        return <BookOpen className="h-4 w-4" />
      case 'code':
        return <FileCode className="h-4 w-4" />
      default:
        return <FileText className="h-4 w-4" />
    }
  }

  if (loading) {
    return <div>Loading...</div>
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Knowledge Base</h1>
        <p className="text-muted-foreground">
          RAG corpus and indexed documents
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Documents</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_documents.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              Indexed files
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Chunks</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_chunks.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              Searchable segments
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Index Size</CardTitle>
            <HardDrive className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.index_size_mb.toFixed(1)} MB</div>
            <p className="text-xs text-muted-foreground">
              Vector database
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Status</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold capitalize">{stats?.corpus_status}</div>
            <p className="text-xs text-muted-foreground">
              Corpus health
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Documents List */}
      <Card>
        <CardHeader>
          <CardTitle>Indexed Documents</CardTitle>
          <CardDescription>Recently indexed knowledge sources</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {documents.map((doc) => (
              <div key={doc.id} className="flex items-start justify-between p-3 border rounded-lg hover:bg-accent/50 transition-colors">
                <div className="flex items-start gap-3 flex-1">
                  {getDocTypeIcon(doc.doc_type)}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{doc.title}</p>
                    <p className="text-sm text-muted-foreground font-mono truncate">{doc.source}</p>
                    <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                      <span>{doc.chunk_count} chunks</span>
                      <span>•</span>
                      <span>{doc.size_kb.toFixed(1)} KB</span>
                      <span>•</span>
                      <span>{new Date(doc.indexed_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                </div>
                <Badge variant="secondary" className="ml-2">
                  {doc.doc_type}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
