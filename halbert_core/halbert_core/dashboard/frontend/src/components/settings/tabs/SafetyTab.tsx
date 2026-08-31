// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { Dispatch, SetStateAction } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { apiUrl } from '@/lib/apiBase'
import {
  Trash2,
  Check,
  X,
  Plus,
  Shield,
  AlertTriangle,
  Lock,
  FileCode,
} from 'lucide-react'

const API_BASE = apiUrl('/api')

export interface AIRule {
  id: string
  rule: string
  category: string
  priority: string
  enabled: boolean
  created_at?: string
}

export interface NewRule {
  rule: string
  category: string
  priority: string
}

export interface ToolPolicy {
  default_allow: boolean
  tools: Record<string, { allow: boolean }>
}

interface SafetyTabProps {
  aiRules: AIRule[]
  aiRulesExamples: string[]
  newRule: NewRule
  setNewRule: Dispatch<SetStateAction<NewRule>>
  addingRule: boolean
  onAddRule: () => void
  onDeleteRule: (ruleId: string) => void
  onToggleRule: (rule: AIRule) => void
  policy: ToolPolicy
  setPolicy: Dispatch<SetStateAction<ToolPolicy>>
  savingPolicy: boolean
  setSavingPolicy: Dispatch<SetStateAction<boolean>>
  policyPath: string
}

/** The Safety tab: custom AI rules, tool policy, and guardrails. */
export function SafetyTab({
  aiRules,
  aiRulesExamples,
  newRule,
  setNewRule,
  addingRule,
  onAddRule,
  onDeleteRule,
  onToggleRule,
  policy,
  setPolicy,
  savingPolicy,
  setSavingPolicy,
  policyPath,
}: SafetyTabProps) {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Custom AI Rules
          </CardTitle>
          <CardDescription>
            Define rules and guardrails for edge cases the AI should always follow.
            These override general advice when they apply to your specific setup.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Existing rules - shown first */}
          {aiRules.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <AlertTriangle className="h-8 w-8 mx-auto mb-3 opacity-50" />
              <p className="font-medium">No custom rules yet</p>
              <p className="text-sm mt-1">
                Add rules below to help the AI understand your specific setup and edge cases.
              </p>
              {aiRulesExamples.length > 0 && (
                <div className="mt-4 text-left max-w-lg mx-auto">
                  <p className="text-xs font-medium mb-2">Example rules:</p>
                  <ul className="text-xs space-y-1 text-muted-foreground">
                    {aiRulesExamples.map((ex, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-primary">•</span>
                        <span>{ex}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {aiRules.length} rule{aiRules.length !== 1 ? 's' : ''} active.
                The AI will always consider these when providing advice.
              </p>
              {aiRules.map((rule) => (
                <div
                  key={rule.id}
                  className={`flex items-start justify-between p-3 rounded-lg border ${
                    rule.enabled ? 'bg-background' : 'bg-muted/50 opacity-60'
                  }`}
                >
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant={rule.priority === 'high' ? 'default' : 'outline'} className="text-xs">
                        {rule.priority}
                      </Badge>
                      <Badge variant="secondary" className="text-xs">
                        {rule.category}
                      </Badge>
                      {!rule.enabled && (
                        <Badge variant="outline" className="text-xs text-muted-foreground">
                          Disabled
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm">{rule.rule}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onToggleRule(rule)}
                      title={rule.enabled ? 'Disable rule' : 'Enable rule'}
                    >
                      {rule.enabled ? (
                        <Check className="h-4 w-4 text-success" />
                      ) : (
                        <X className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onDeleteRule(rule.id)}
                      className="text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Add new rule form - at bottom */}
          <div className="space-y-4 p-4 border rounded-lg bg-muted/30">
            <div className="space-y-2">
              <Label htmlFor="new-rule">Add a New Rule</Label>
              <Input
                id="new-rule"
                value={newRule.rule}
                onChange={(e) => setNewRule(prev => ({ ...prev, rule: e.target.value }))}
                placeholder="e.g., My NAS mounts may be offline - don't treat unmounted network shares as errors"
                className="text-sm"
              />
            </div>

            <div className="flex gap-4 items-end">
              <div className="space-y-2 flex-1">
                <Label htmlFor="rule-category">Category</Label>
                <Select
                  id="rule-category"
                  value={newRule.category}
                  onChange={(e) => setNewRule(prev => ({ ...prev, category: e.target.value }))}
                >
                  <option value="general">General</option>
                  <option value="storage">Storage</option>
                  <option value="kernel">Kernel</option>
                  <option value="network">Network</option>
                  <option value="security">Security</option>
                  <option value="docker">Docker/Containers</option>
                  <option value="packages">Packages</option>
                </Select>
              </div>

              <div className="space-y-2 flex-1">
                <Label htmlFor="rule-priority">Priority</Label>
                <Select
                  id="rule-priority"
                  value={newRule.priority}
                  onChange={(e) => setNewRule(prev => ({ ...prev, priority: e.target.value }))}
                >
                  <option value="high">High (Always apply)</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low (Context-dependent)</option>
                </Select>
              </div>

              <Button
                onClick={onAddRule}
                disabled={!newRule.rule.trim() || addingRule}
                size="sm"
              >
                <Plus className="h-4 w-4 mr-1" />
                Add Rule
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tool Policy Section */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Lock className="h-5 w-5" />
            Tool Policy
          </CardTitle>
          <CardDescription>
            Control which tools the AI can execute. Tools not explicitly configured follow the default policy.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="p-4 bg-muted/50 rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">Default Allow</p>
                <p className="text-sm text-muted-foreground">
                  When enabled, tools are allowed unless explicitly denied
                </p>
              </div>
              <Button
                variant={policy.default_allow ? "default" : "outline"}
                size="sm"
                disabled={savingPolicy}
                onClick={async () => {
                  setSavingPolicy(true)
                  try {
                    const newPolicy = { ...policy, default_allow: !policy.default_allow }
                    await fetch(`${API_BASE}/settings/policy`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ policy: newPolicy })
                    })
                    setPolicy(newPolicy)
                  } catch (err) {
                    console.error('Failed to update policy:', err)
                  }
                  setSavingPolicy(false)
                }}
              >
                {policy.default_allow ? (
                  <><Check className="h-4 w-4 mr-1" /> Enabled</>
                ) : (
                  <><X className="h-4 w-4 mr-1" /> Disabled</>
                )}
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <h4 className="font-medium text-sm">Tool Overrides</h4>
            <p className="text-sm text-muted-foreground">
              Click to toggle individual tool permissions
            </p>
            <div className="grid gap-2 mt-2">
              {Object.entries(policy.tools || {}).map(([toolName, config]) => (
                <div key={toolName} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                  <div className="flex items-center gap-2">
                    <FileCode className="h-4 w-4" />
                    <span className="font-mono text-sm">{toolName}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant={config.allow ? "default" : "destructive"}
                      size="sm"
                      disabled={savingPolicy}
                      onClick={async () => {
                        setSavingPolicy(true)
                        try {
                          await fetch(`${API_BASE}/settings/policy/tool`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ tool: toolName, allow: !config.allow })
                          })
                          setPolicy(prev => ({
                            ...prev,
                            tools: { ...prev.tools, [toolName]: { allow: !config.allow } }
                          }))
                        } catch (err) {
                          console.error('Failed to update tool policy:', err)
                        }
                        setSavingPolicy(false)
                      }}
                    >
                      {config.allow ? 'Allowed' : 'Denied'}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={savingPolicy}
                      onClick={async () => {
                        setSavingPolicy(true)
                        try {
                          await fetch(`${API_BASE}/settings/policy/tool/${toolName}`, {
                            method: 'DELETE'
                          })
                          setPolicy(prev => {
                            const newTools = { ...prev.tools }
                            delete newTools[toolName]
                            return { ...prev, tools: newTools }
                          })
                        } catch (err) {
                          console.error('Failed to delete tool policy:', err)
                        }
                        setSavingPolicy(false)
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
              {Object.keys(policy.tools || {}).length === 0 && (
                <p className="text-sm text-muted-foreground p-3">
                  No tool overrides configured. All tools follow the default policy.
                </p>
              )}
            </div>
          </div>

          <div className="pt-4 border-t">
            <p className="text-xs text-muted-foreground">
              Policy file: <code className="px-1 py-0.5 bg-muted rounded">{policyPath || 'config/policy.yml'}</code>
            </p>
          </div>
        </CardContent>
      </Card>
    </>
  )
}