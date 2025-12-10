import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { getActiveJobs, type Job } from '@/lib/tauri'
import { Activity, Clock, PlayCircle, CheckCircle, XCircle } from 'lucide-react'

export function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadJobs()
    // Poll every 2 seconds for job updates
    const interval = setInterval(loadJobs, 2000)
    return () => clearInterval(interval)
  }, [])

  const loadJobs = async () => {
    try {
      const activeJobs = await getActiveJobs()
      setJobs(activeJobs)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load jobs:', error)
      setLoading(false)
    }
  }

  if (loading) {
    return <div>Loading...</div>
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Activity className="h-4 w-4 text-primary animate-pulse" />
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-destructive" />
      case 'pending':
        return <Clock className="h-4 w-4 text-muted-foreground" />
      default:
        return <PlayCircle className="h-4 w-4" />
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'running':
        return <Badge variant="default">Running</Badge>
      case 'completed':
        return <Badge variant="secondary" className="bg-green-500/10 text-green-500">Completed</Badge>
      case 'failed':
        return <Badge variant="destructive">Failed</Badge>
      case 'pending':
        return <Badge variant="outline">Pending</Badge>
      default:
        return <Badge>{status}</Badge>
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Autonomous Jobs</h1>
        <p className="text-muted-foreground">
          Active and scheduled background tasks
        </p>
      </div>

      {jobs.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No active jobs
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {jobs.map((job) => (
            <Card key={job.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    {getStatusIcon(job.status)}
                    <div>
                      <CardTitle>{job.name}</CardTitle>
                      <CardDescription className="flex items-center gap-2 mt-1">
                        <span className="capitalize">{job.task_type}</span>
                        <span>•</span>
                        <span>{new Date(job.started_at).toLocaleString()}</span>
                      </CardDescription>
                    </div>
                  </div>
                  {getStatusBadge(job.status)}
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {job.progress > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Progress</span>
                      <span className="font-medium">{(job.progress * 100).toFixed(0)}%</span>
                    </div>
                    <Progress value={job.progress * 100} />
                  </div>
                )}

                {job.logs.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">Recent Activity:</p>
                    <div className="bg-muted rounded-md p-3 space-y-1">
                      {job.logs.slice(-5).map((log, i) => (
                        <p key={i} className="text-xs font-mono text-muted-foreground">
                          {log}
                        </p>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
