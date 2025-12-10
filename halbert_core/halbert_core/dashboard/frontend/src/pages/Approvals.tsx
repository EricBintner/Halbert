import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { getPendingApprovals, approveRequest, rejectRequest, type ApprovalRequest } from '@/lib/tauri'
import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react'

export function Approvals() {
  const [pending, setPending] = useState<ApprovalRequest[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadApprovals()
    // Poll every 5 seconds for new approvals
    const interval = setInterval(loadApprovals, 5000)
    return () => clearInterval(interval)
  }, [])

  const loadApprovals = async () => {
    try {
      const approvals = await getPendingApprovals()
      setPending(approvals)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load approvals:', error)
      setLoading(false)
    }
  }

  const handleApprove = async (requestId: string) => {
    try {
      await approveRequest(requestId)
      loadApprovals()
    } catch (error) {
      console.error('Approval failed:', error)
    }
  }

  const handleReject = async (requestId: string) => {
    const reason = prompt('Rejection reason:')
    if (reason) {
      try {
        await rejectRequest(requestId, reason)
        loadApprovals()
      } catch (error) {
        console.error('Rejection failed:', error)
      }
    }
  }

  if (loading) {
    return <div>Loading...</div>
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Approval Requests</h1>
        <p className="text-muted-foreground">
          Review and approve autonomous actions
        </p>
      </div>

      {pending.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No pending approval requests
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {pending.map((request) => (
            <Card key={request.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle>{request.action}</CardTitle>
                    <CardDescription>{request.task}</CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    {request.risk_level === 'high' && <AlertTriangle className="h-4 w-4 text-destructive" />}
                    {request.risk_level === 'medium' && <AlertTriangle className="h-4 w-4 text-yellow-500" />}
                    <Badge
                      variant={
                        request.risk_level === 'high' ? 'destructive' :
                        request.risk_level === 'medium' ? 'default' : 'secondary'
                      }
                    >
                      {request.risk_level} risk
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm font-medium">Reasoning:</p>
                  <p className="text-sm text-muted-foreground">{request.reasoning}</p>
                </div>

                <div className="flex items-center gap-4 text-sm">
                  <span>Confidence: <strong>{(request.confidence * 100).toFixed(0)}%</strong></span>
                  <span>•</span>
                  <span className="text-muted-foreground">
                    {new Date(request.requested_at).toLocaleString()}
                  </span>
                </div>

                {request.affected_resources && request.affected_resources.length > 0 && (
                  <div>
                    <p className="text-sm font-medium mb-2">Affected Resources:</p>
                    <ul className="text-sm text-muted-foreground space-y-1">
                      {request.affected_resources.map((resource: string, i: number) => (
                        <li key={i} className="font-mono text-xs">• {resource}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="flex gap-2 pt-4">
                  <Button
                    onClick={() => handleApprove(request.id)}
                    className="gap-2"
                  >
                    <CheckCircle className="h-4 w-4" />
                    Approve
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => handleReject(request.id)}
                    className="gap-2"
                  >
                    <XCircle className="h-4 w-4" />
                    Reject
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
