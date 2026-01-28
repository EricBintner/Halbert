import { useEffect, useState, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { 
  Download, 
  HardDrive, 
  Trash2, 
  RefreshCw, 
  AlertTriangle,
  CheckCircle,
  XCircle,
  Package,
  BookOpen,
  ExternalLink,
  Pause
} from 'lucide-react'

const API_BASE = '/api'

interface Dataset {
  id: string
  name: string
  description: string
  size_bytes: number
  size_human: string
  destination: string
  category: string
  required: boolean
  status: 'not_downloaded' | 'downloading' | 'completed' | 'failed' | 'verifying'
  progress: number
  downloaded_bytes: number
  error: string | null
}

interface DownloadStatus {
  dataset_id: string
  status: string
  progress: number
  downloaded_bytes: number
  total_bytes: number
  speed_bps: number
  speed_human: string
  eta_seconds: number | null
  eta_human: string
  error: string | null
}

interface DatasetsResponse {
  datasets: Dataset[]
  by_category: Record<string, Dataset[]>
  total_count: number
  downloaded_count: number
}

export function DatasetManager() {
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeDownloads, setActiveDownloads] = useState<Record<string, DownloadStatus>>({})

  const loadDatasets = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/downloads/datasets`)
      if (!res.ok) throw new Error('Failed to load datasets')
      const data: DatasetsResponse = await res.json()
      setDatasets(data.datasets)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load datasets')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDatasets()
  }, [loadDatasets])

  // Poll for active download progress
  useEffect(() => {
    const downloadingIds = datasets
      .filter(d => d.status === 'downloading')
      .map(d => d.id)

    if (downloadingIds.length === 0) return

    const pollInterval = setInterval(async () => {
      for (const id of downloadingIds) {
        try {
          const res = await fetch(`${API_BASE}/downloads/datasets/${id}/status`)
          if (res.ok) {
            const status: DownloadStatus = await res.json()
            setActiveDownloads(prev => ({ ...prev, [id]: status }))

            // Update dataset status if completed or failed
            if (status.status === 'completed' || status.status === 'failed') {
              loadDatasets()
            }
          }
        } catch (err) {
          console.error(`Failed to poll status for ${id}:`, err)
        }
      }
    }, 500)

    return () => clearInterval(pollInterval)
  }, [datasets, loadDatasets])

  const startDownload = async (datasetId: string) => {
    try {
      const res = await fetch(`${API_BASE}/downloads/datasets/${datasetId}/download`, {
        method: 'POST'
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Failed to start download')
      }
      // Refresh datasets to show downloading status
      await loadDatasets()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start download')
    }
  }

  const cancelDownload = async (datasetId: string) => {
    try {
      await fetch(`${API_BASE}/downloads/datasets/${datasetId}/cancel`, {
        method: 'POST'
      })
      await loadDatasets()
    } catch (err) {
      console.error('Failed to cancel:', err)
    }
  }

  const deleteDataset = async (datasetId: string) => {
    if (!confirm('Delete this dataset? You can re-download it later.')) return
    
    try {
      const res = await fetch(`${API_BASE}/downloads/datasets/${datasetId}`, {
        method: 'DELETE'
      })
      if (!res.ok) throw new Error('Failed to delete')
      await loadDatasets()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete dataset')
    }
  }

  const getStatusBadge = (dataset: Dataset) => {
    switch (dataset.status) {
      case 'completed':
        return (
          <Badge variant="outline" className="text-green-600 border-green-600">
            <CheckCircle className="h-3 w-3 mr-1" />
            Downloaded
          </Badge>
        )
      case 'downloading':
        return (
          <Badge variant="outline" className="text-blue-600 border-blue-600">
            <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
            Downloading
          </Badge>
        )
      case 'failed':
        return (
          <Badge variant="outline" className="text-red-600 border-red-600">
            <XCircle className="h-3 w-3 mr-1" />
            Failed
          </Badge>
        )
      default:
        return (
          <Badge variant="outline" className="text-muted-foreground">
            <Download className="h-3 w-3 mr-1" />
            Not Downloaded
          </Badge>
        )
    }
  }

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'linux_docs':
        return <BookOpen className="h-4 w-4" />
      default:
        return <Package className="h-4 w-4" />
    }
  }

  const getCategoryLabel = (category: string) => {
    switch (category) {
      case 'linux_docs':
        return 'Linux Documentation'
      default:
        return category
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-2 text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Loading datasets...
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-2 text-destructive">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </div>
          <div className="flex justify-center mt-4">
            <Button variant="outline" onClick={loadDatasets}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Group by category
  const byCategory = datasets.reduce((acc, ds) => {
    const cat = ds.category
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(ds)
    return acc
  }, {} as Record<string, Dataset[]>)

  const downloadedCount = datasets.filter(d => d.status === 'completed').length
  const totalSize = datasets.reduce((sum, d) => sum + d.size_bytes, 0)
  const downloadedSize = datasets
    .filter(d => d.status === 'completed')
    .reduce((sum, d) => sum + d.size_bytes, 0)

  return (
    <div className="space-y-4">
      {/* Overview Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <HardDrive className="h-5 w-5" />
                RAG Datasets
              </CardTitle>
              <CardDescription>
                Download documentation for Halbert's knowledge base
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={loadDatasets}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Datasets</p>
              <p className="text-2xl font-bold">{downloadedCount} / {datasets.length}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Downloaded</p>
              <p className="text-2xl font-bold">{formatBytes(downloadedSize)}</p>
            </div>
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Total Available</p>
              <p className="text-2xl font-bold">{formatBytes(totalSize)}</p>
            </div>
          </div>
          
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            <ExternalLink className="h-4 w-4" />
            Hosted on Hugging Face Hub
          </div>
        </CardContent>
      </Card>

      {/* Dataset List by Category */}
      {Object.entries(byCategory).map(([category, categoryDatasets]) => (
        <Card key={category}>
          <CardHeader className="py-3">
            <CardTitle className="text-base flex items-center gap-2">
              {getCategoryIcon(category)}
              {getCategoryLabel(category)}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {categoryDatasets.map(dataset => {
              const downloadStatus = activeDownloads[dataset.id]
              const isDownloading = dataset.status === 'downloading'
              const progress = downloadStatus?.progress ?? dataset.progress

              return (
                <div 
                  key={dataset.id} 
                  className="border rounded-lg p-4 space-y-3"
                >
                  {/* Header */}
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{dataset.name}</span>
                        {getStatusBadge(dataset)}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {dataset.description}
                      </p>
                    </div>
                    <div className="text-right text-sm text-muted-foreground">
                      {dataset.size_human}
                    </div>
                  </div>

                  {/* Progress Bar (when downloading) */}
                  {isDownloading && (
                    <div className="space-y-2">
                      <Progress value={progress} className="h-2" />
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>
                          {formatBytes(downloadStatus?.downloaded_bytes ?? 0)} / {dataset.size_human}
                        </span>
                        <span>
                          {downloadStatus?.speed_human && `${downloadStatus.speed_human} • `}
                          {downloadStatus?.eta_human && `${downloadStatus.eta_human} remaining`}
                          {!downloadStatus?.speed_human && `${progress.toFixed(0)}%`}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Error Message */}
                  {dataset.status === 'failed' && dataset.error && (
                    <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/10 rounded-md p-2">
                      <AlertTriangle className="h-4 w-4 shrink-0" />
                      {dataset.error}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2">
                    {dataset.status === 'not_downloaded' || dataset.status === 'failed' ? (
                      <Button 
                        size="sm" 
                        onClick={() => startDownload(dataset.id)}
                      >
                        <Download className="h-4 w-4 mr-2" />
                        Download
                      </Button>
                    ) : isDownloading ? (
                      <Button 
                        size="sm" 
                        variant="outline"
                        onClick={() => cancelDownload(dataset.id)}
                      >
                        <Pause className="h-4 w-4 mr-2" />
                        Cancel
                      </Button>
                    ) : dataset.status === 'completed' ? (
                      <Button 
                        size="sm" 
                        variant="outline"
                        onClick={() => deleteDataset(dataset.id)}
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Delete
                      </Button>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </CardContent>
        </Card>
      ))}

      {/* Empty State */}
      {datasets.length === 0 && (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            <Package className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>No datasets available</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}
