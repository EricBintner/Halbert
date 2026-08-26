// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useEffect, useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { 
  getPendingApprovals, 
  approveRequest, 
  rejectRequest, 
  getApprovalHistory,
  type ApprovalRequest,
  type ApprovalHistoryItem
} from '@/lib/tauri'
import { CheckCircle, XCircle, AlertTriangle, Clock, History, ShieldAlert, X, Brain, Loader2 } from 'lucide-react'
import { PageHeader } from '@/components/domain'

export function Approvals() {
  const [pending, setPending] = useState<ApprovalRequest[]>([])
  const [blockedByRules, setBlockedByRules] = useState(0)
  const [history, setHistory] = useState<ApprovalHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  
  // Unified decision modal state
  const [decisionModalOpen, setDecisionModalOpen] = useState(false)
  const [decisionType, setDecisionType] = useState<'approve' | 'reject'>('approve')
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null)
  const [selectedRequestAction, setSelectedRequestAction] = useState<string>('')
  const [decisionReason, setDecisionReason] = useState('')
  const [saveToMemory, setSaveToMemory] = useState(true)
  const [decisionLoading, setDecisionLoading] = useState(false)

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

  const openDecisionModal = (requestId: string, action: string, type: 'approve' | 'reject') => {
    setSelectedRequestId(requestId)
    setSelectedRequestAction(action)
    setDecisionType(type)
    setDecisionReason('')
    setSaveToMemory(true)
    setDecisionModalOpen(true)
  }
  
  const handleDecision = async () => {
    if (!selectedRequestId) return
    if (decisionType === 'reject' && !decisionReason.trim()) return
    
    setDecisionLoading(true)
    try {
      if (decisionType === 'approve') {
        await approveRequest(selectedRequestId, saveToMemory)
      } else {
        await rejectRequest(selectedRequestId, decisionReason, saveToMemory)
      }
      setDecisionModalOpen(false)
      loadAll()
    } catch (error) {
      console.error(`${decisionType} failed:`, error)
    } finally {
      setDecisionLoading(false)
    }
  }

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
        icon={<ShieldAlert className="h-8 w-8" />}
        title="Approval Requests"
        description="Review and approve autonomous actions"
        hideScanButton
      />

      {/* Show blocked count if any */}
      {blockedByRules > 0 && (
        <div className="bg-success/10 border border-success/30 rounded-lg p-3 flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 text-success" />
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
                        {request.risk_level === 'medium' && <AlertTriangle className="h-4 w-4 text-warning" />}
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
                      <div className="bg-warning/10 border border-warning/30 rounded-lg p-3">
                        <div className="flex items-start gap-2">
                          <ShieldAlert className="h-5 w-5 text-warning flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="font-medium text-warning dark:text-warning">
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
                        onClick={() => openDecisionModal(request.id, request.action, 'approve')}
                        className="gap-2"
                      >
                        <CheckCircle className="h-4 w-4" />
                        Approve
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => openDecisionModal(request.id, request.action, 'reject')}
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
                          <CheckCircle className="h-4 w-4 text-success" />
                        ) : (
                          <XCircle className="h-4 w-4 text-error" />
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
      
      {/* Decision Modal - Used for both Approve and Reject */}
      {decisionModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div 
            className="fixed inset-0 bg-background/80 backdrop-blur-sm"
            onClick={() => setDecisionModalOpen(false)}
          />
          
          {/* Modal */}
          <div className="relative z-50 w-full max-w-md rounded-lg border bg-card p-6 shadow-lg animate-in fade-in-0 zoom-in-95">
            {/* Close button */}
            <button
              onClick={() => setDecisionModalOpen(false)}
              className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100 transition-opacity"
            >
              <X className="h-4 w-4" />
            </button>

            <div className="space-y-4">
              {/* Header */}
              <div className="space-y-2">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                  {decisionType === 'approve' ? (
                    <CheckCircle className="h-5 w-5 text-success" />
                  ) : (
                    <XCircle className="h-5 w-5 text-error" />
                  )}
                  {decisionType === 'approve' ? 'Approve Request' : 'Reject Request'}
                </h3>
                <p className="text-sm text-muted-foreground">
                  {selectedRequestAction}
                </p>
              </div>

              {/* Reason input - only for rejection */}
              {decisionType === 'reject' && (
                <div className="space-y-2">
                  <label className="text-sm font-medium">Why are you rejecting this?</label>
                  <textarea
                    placeholder="e.g., Conflicts with my setup, Not needed, Wrong approach..."
                    value={decisionReason}
                    onChange={(e) => setDecisionReason(e.target.value)}
                    className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none min-h-[80px]"
                    rows={3}
                    autoFocus
                  />
                </div>
              )}

              {/* Memory checkbox */}
              <div className="flex items-start gap-3 rounded-md bg-error/10 border border-error/20 p-3">
                <input
                  type="checkbox"
                  id="saveToMemory"
                  checked={saveToMemory}
                  onChange={(e) => setSaveToMemory(e.target.checked)}
                  className="mt-1 accent-pink-500"
                />
                <label htmlFor="saveToMemory" className="text-sm cursor-pointer">
                  <span className="flex items-center gap-1.5 font-medium text-error dark:text-error">
                    <Brain className="h-4 w-4" />
                    Remember this decision
                  </span>
                  <span className="text-muted-foreground block mt-0.5">
                    {decisionType === 'approve' 
                      ? 'AI will learn that similar actions are acceptable'
                      : 'AI will learn to avoid similar actions in the future'
                    }
                  </span>
                </label>
              </div>

              {/* Actions */}
              <div className="flex justify-end gap-3 pt-2">
                <Button 
                  variant="outline" 
                  onClick={() => setDecisionModalOpen(false)}
                  disabled={decisionLoading}
                >
                  Cancel
                </Button>
                <Button 
                  variant={decisionType === 'approve' ? 'default' : 'destructive'}
                  onClick={handleDecision}
                  disabled={(decisionType === 'reject' && !decisionReason.trim()) || decisionLoading}
                >
                  {decisionLoading 
                    ? (decisionType === 'approve' ? 'Approving...' : 'Rejecting...')
                    : (decisionType === 'approve' ? 'Approve' : 'Reject')
                  }
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
