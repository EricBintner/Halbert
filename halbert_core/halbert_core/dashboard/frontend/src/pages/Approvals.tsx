import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { 
  getPendingApprovals, 
  approveRequest, 
  rejectRequest, 
  getApprovalHistory,
  type ApprovalRequest,
  type ApprovalHistoryItem
} from '@/lib/tauri'
import { CheckCircle, XCircle, AlertTriangle, Clock, History, ShieldAlert, X, Brain } from 'lucide-react'

export function Approvals() {
  const [pending, setPending] = useState<ApprovalRequest[]>([])
  const [blockedByRules, setBlockedByRules] = useState(0)
  const [history, setHistory] = useState<ApprovalHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  
  // Rejection modal state
  const [rejectModalOpen, setRejectModalOpen] = useState(false)
  const [rejectingRequestId, setRejectingRequestId] = useState<string | null>(null)
  const [rejectingRequestAction, setRejectingRequestAction] = useState<string>('')
  const [rejectionReason, setRejectionReason] = useState('')
  const [saveToMemory, setSaveToMemory] = useState(true)
  const [rejectLoading, setRejectLoading] = useState(false)

  useEffect(() => {
    loadAll()
    // Poll every 5 seconds for new approvals
    const interval = setInterval(loadAll, 5000)
    return () => clearInterval(interval)
  }, [])

  const loadAll = async () => {
    try {
      const [approvalsResponse, hist] = await Promise.all([
        getPendingApprovals(),
        getApprovalHistory(20)
      ])
      setPending(approvalsResponse.pending)
      setBlockedByRules(approvalsResponse.blocked_by_rules)
      setHistory(hist)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load approvals:', error)
      setLoading(false)
    }
  }

  const handleApprove = async (requestId: string) => {
    try {
      await approveRequest(requestId)
      loadAll()
    } catch (error) {
      console.error('Approval failed:', error)
    }
  }

  const openRejectModal = (requestId: string, action: string) => {
    setRejectingRequestId(requestId)
    setRejectingRequestAction(action)
    setRejectionReason('')
    setSaveToMemory(true)
    setRejectModalOpen(true)
  }
  
  const handleReject = async () => {
    if (!rejectingRequestId || !rejectionReason.trim()) return
    
    setRejectLoading(true)
    try {
      // Reject the request with reason and optional memory flag
      await rejectRequest(rejectingRequestId, rejectionReason, saveToMemory)
      setRejectModalOpen(false)
      loadAll()
    } catch (error) {
      console.error('Rejection failed:', error)
    } finally {
      setRejectLoading(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading approvals...</div>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Approval Requests</h1>
        <p className="text-muted-foreground">
          Review and approve autonomous actions
        </p>
      </div>

      {/* Show blocked count if any */}
      {blockedByRules > 0 && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 text-green-600" />
          <span className="text-sm">
            <strong>{blockedByRules}</strong> approval{blockedByRules > 1 ? 's' : ''} blocked by your AI Rules
          </span>
        </div>
      )}

      <Tabs defaultValue="pending">
        <TabsList>
          <TabsTrigger value="pending" className="gap-2">
            <Clock className="h-4 w-4" />
            Pending {pending.length > 0 && <Badge variant="secondary">{pending.length}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="history" className="gap-2">
            <History className="h-4 w-4" />
            History
          </TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="mt-4">
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
                    {/* Rule Conflict Warning */}
                    {request.rule_conflict && (
                      <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
                        <div className="flex items-start gap-2">
                          <ShieldAlert className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="font-medium text-amber-600 dark:text-amber-400">
                              Conflicts with AI Rule
                            </p>
                            <p className="text-sm text-muted-foreground mt-1">
                              {request.rule_conflict.conflicting_rule}
                            </p>
                            <p className="text-xs text-muted-foreground mt-1">
                              Category: {request.rule_conflict.rule_category} • 
                              Priority: {request.rule_conflict.rule_priority}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}
                    
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
                        onClick={() => openRejectModal(request.id, request.action)}
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
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          {history.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                No approval history
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-0">
                <div className="divide-y">
                  {history.map((item, idx) => (
                    <div key={idx} className="flex items-center justify-between p-4">
                      <div className="flex items-center gap-3">
                        {item.approved ? (
                          <CheckCircle className="h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-500" />
                        )}
                        <div>
                          <p className="font-medium">{item.request_id}</p>
                          <p className="text-sm text-muted-foreground">
                            {item.reason || (item.approved ? 'Approved' : 'Rejected')}
                          </p>
                        </div>
                      </div>
                      <div className="text-right text-sm text-muted-foreground">
                        <p>{item.decided_by}</p>
                        <p>{new Date(item.decided_at).toLocaleString()}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
      
      {/* Rejection Modal */}
      {rejectModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div 
            className="fixed inset-0 bg-background/80 backdrop-blur-sm"
            onClick={() => setRejectModalOpen(false)}
          />
          
          {/* Modal */}
          <div className="relative z-50 w-full max-w-lg rounded-lg border bg-card p-6 shadow-lg animate-in fade-in-0 zoom-in-95">
            {/* Close button */}
            <button
              onClick={() => setRejectModalOpen(false)}
              className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100 transition-opacity"
            >
              <X className="h-4 w-4" />
            </button>

            <div className="space-y-4">
              {/* Header */}
              <div className="space-y-2">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  <XCircle className="h-5 w-5 text-red-500" />
                  Reject Request
                </h3>
                <p className="text-sm text-muted-foreground">
                  {rejectingRequestAction}
                </p>
              </div>

              {/* Reason input */}
              <div className="space-y-2">
                <label className="text-sm font-medium">Why are you rejecting this?</label>
                <Input
                  placeholder="e.g., This conflicts with my setup, Not needed right now, Wrong approach..."
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && rejectionReason.trim()) {
                      handleReject()
                    }
                  }}
                  autoFocus
                />
              </div>

              {/* Memory checkbox */}
              <div className="flex items-start gap-3 rounded-md bg-blue-500/10 border border-blue-500/20 p-3">
                <input
                  type="checkbox"
                  id="saveToMemory"
                  checked={saveToMemory}
                  onChange={(e) => setSaveToMemory(e.target.checked)}
                  className="mt-1"
                />
                <label htmlFor="saveToMemory" className="text-sm cursor-pointer">
                  <span className="flex items-center gap-1.5 font-medium text-blue-600 dark:text-blue-400">
                    <Brain className="h-4 w-4" />
                    Remember this preference
                  </span>
                  <span className="text-muted-foreground block mt-0.5">
                    Store in AI memory so similar requests are handled better in the future
                  </span>
                </label>
              </div>

              {/* Actions */}
              <div className="flex justify-end gap-3 pt-2">
                <Button 
                  variant="outline" 
                  onClick={() => setRejectModalOpen(false)}
                  disabled={rejectLoading}
                >
                  Cancel
                </Button>
                <Button 
                  variant="destructive"
                  onClick={handleReject}
                  disabled={!rejectionReason.trim() || rejectLoading}
                >
                  {rejectLoading ? 'Rejecting...' : 'Reject Request'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
