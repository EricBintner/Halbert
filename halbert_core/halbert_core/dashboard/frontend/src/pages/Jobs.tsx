import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { 
  getSchedulerStatus, 
  getScheduledJobs,
  cancelScheduledJob,
  getGuardrailsStatus,
  exitSafeMode,
  type SchedulerStatus,
  type ScheduledJob,
  type GuardrailsStatus
} from '@/lib/tauri'
import { Activity, Clock, XCircle, Calendar, Shield, ShieldOff, Trash2, AlertTriangle } from 'lucide-react'

export function Jobs() {
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null)
  const [scheduledJobs, setScheduledJobs] = useState<ScheduledJob[]>([])
  const [guardrails, setGuardrails] = useState<GuardrailsStatus | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAll()
    // Poll every 10 seconds
    const interval = setInterval(loadAll, 10000)
    return () => clearInterval(interval)
  }, [])

  const loadAll = async () => {
    try {
      const [status, jobs, gr] = await Promise.all([
        getSchedulerStatus(),
        getScheduledJobs(),
        getGuardrailsStatus()
      ])
      setSchedulerStatus(status)
      setScheduledJobs(jobs)
      setGuardrails(gr)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load scheduler data:', error)
      setLoading(false)
    }
  }

  const handleCancelJob = async (jobId: string) => {
    if (!confirm(`Cancel job ${jobId}?`)) return
    try {
      await cancelScheduledJob(jobId)
      loadAll()
    } catch (error) {
      console.error('Failed to cancel job:', error)
    }
  }

  const handleExitSafeMode = async () => {
    try {
      await exitSafeMode()
      loadAll()
    } catch (error) {
      console.error('Failed to exit safe mode:', error)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading scheduler...</div>
  }

  return (
    <div className="space-y-6">
      {/* Safe Mode Banner */}
      {guardrails?.safe_mode_active && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            <div>
              <p className="font-medium text-amber-600 dark:text-amber-400">Safe Mode Active</p>
              <p className="text-sm text-muted-foreground">Autonomous operations are paused</p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={handleExitSafeMode}>
            <ShieldOff className="h-4 w-4 mr-2" />
            Exit Safe Mode
          </Button>
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Scheduler & Jobs</h1>
        <p className="text-muted-foreground">
          Autonomous task scheduling and execution
        </p>
      </div>

      {/* Scheduler Status */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Scheduler</CardDescription>
            <CardTitle className="text-2xl flex items-center gap-2">
              {schedulerStatus?.running ? (
                <>
                  <Activity className="h-5 w-5 text-green-500" />
                  Running
                </>
              ) : (
                <>
                  <XCircle className="h-5 w-5 text-muted-foreground" />
                  Stopped
                </>
              )}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Scheduled Jobs</CardDescription>
            <CardTitle className="text-2xl">{schedulerStatus?.scheduled_jobs || 0}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Completed</CardDescription>
            <CardTitle className="text-2xl text-green-500">{schedulerStatus?.completed_jobs || 0}</CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Failed</CardDescription>
            <CardTitle className="text-2xl text-red-500">{schedulerStatus?.failed_jobs || 0}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Guardrails Status */}
      {guardrails && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              Guardrails
            </CardTitle>
            <CardDescription>Confidence thresholds and resource budgets</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <p className="text-sm text-muted-foreground">Auto-execute threshold</p>
                <p className="text-lg font-medium">{(guardrails.config?.confidence?.min_auto_execute || 0.8) * 100}%</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Approval threshold</p>
                <p className="text-lg font-medium">{(guardrails.config?.confidence?.min_approval_execute || 0.5) * 100}%</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Max CPU</p>
                <p className="text-lg font-medium">{guardrails.config?.budgets?.cpu_percent_max || 50}%</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Scheduled Jobs List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Scheduled Jobs
          </CardTitle>
          <CardDescription>Recurring autonomous tasks</CardDescription>
        </CardHeader>
        <CardContent>
          {scheduledJobs.length === 0 ? (
            <p className="text-center text-muted-foreground py-4">No scheduled jobs</p>
          ) : (
            <div className="space-y-2">
              {scheduledJobs.map((job) => (
                <div 
                  key={job.id} 
                  className="flex items-center justify-between p-3 rounded-lg border bg-card"
                >
                  <div className="flex items-center gap-3">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="font-medium">{job.name || job.id}</p>
                      <p className="text-sm text-muted-foreground">
                        Next run: {job.next_run ? new Date(job.next_run).toLocaleString() : 'N/A'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="font-mono text-xs">
                      {job.trigger}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      onClick={() => handleCancelJob(job.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
