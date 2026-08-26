// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * ConfirmationDialog Component
 * 
 * Modal dialog for confirming high-risk agent actions.
 * Based on research5.md Part 8.3.
 */

import { type ConfirmationRequest } from '../../hooks/useAgentStream';

interface ConfirmationDialogProps {
  confirmation: ConfirmationRequest;
  onConfirm: () => void;
  onReject: () => void;
}

const RISK_CONFIG: Record<string, { color: string; bgColor: string; icon: string }> = {
  safe: { color: 'text-success', bgColor: 'bg-success/20', icon: '✓' },
  low: { color: 'text-info', bgColor: 'bg-info/20', icon: 'ℹ' },
  medium: { color: 'text-warning', bgColor: 'bg-warning/20', icon: '⚠' },
  high: { color: 'text-warning', bgColor: 'bg-warning/20', icon: '⚠' },
  critical: { color: 'text-error', bgColor: 'bg-error/20', icon: '⛔' },
};

export function ConfirmationDialog({ 
  confirmation, 
  onConfirm, 
  onReject 
}: ConfirmationDialogProps) {
  const riskConfig = RISK_CONFIG[confirmation.riskLevel] || RISK_CONFIG.medium;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-background rounded-lg shadow-xl max-w-md w-full mx-4 overflow-hidden border border-border">
        <div className={`${riskConfig.bgColor} px-4 py-3 border-b border-border`}>
          <div className="flex items-center gap-2">
            <span className={`text-xl ${riskConfig.color}`}>{riskConfig.icon}</span>
            <h3 className={`font-semibold ${riskConfig.color}`}>
              Confirmation Required
            </h3>
          </div>
        </div>

        <div className="p-4 space-y-4">
          <div>
            <div className="text-sm text-muted-foreground mb-1">Tool</div>
            <div className="font-mono text-sm bg-muted text-foreground px-2 py-1 rounded">
              {confirmation.tool}
            </div>
          </div>

          <div>
            <div className="text-sm text-muted-foreground mb-1">Action</div>
            <div 
              className="text-sm text-foreground prose prose-sm prose-invert max-w-none"
              dangerouslySetInnerHTML={{ 
                __html: confirmation.description
                  .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                  .replace(/```([\s\S]*?)```/g, '<pre class="bg-muted p-2 rounded text-xs">$1</pre>')
                  .replace(/`([^`]+)`/g, '<code class="bg-muted px-1 rounded">$1</code>')
                  .replace(/\n/g, '<br/>')
              }}
            />
          </div>

          <div className={`text-xs ${riskConfig.color} ${riskConfig.bgColor} px-2 py-1 rounded inline-block`}>
            Risk Level: {confirmation.riskLevel.toUpperCase()}
          </div>
        </div>

        <div className="flex gap-3 p-4 border-t border-border bg-muted/50">
          <button
            onClick={onReject}
            className="flex-1 px-4 py-2 text-sm font-medium text-foreground bg-muted border border-border rounded-lg hover:bg-muted focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-zinc-900 focus:ring-ring transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`
              flex-1 px-4 py-2 text-sm font-medium text-white rounded-lg
              focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-zinc-900 transition-colors
              ${confirmation.riskLevel === 'high' || confirmation.riskLevel === 'critical'
                ? 'bg-warning hover:bg-warning focus:ring-warning'
                : 'bg-primary text-primary-foreground hover:bg-primary/90 focus:ring-ring'
              }
            `}
          >
            Confirm & Execute
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmationDialog;
