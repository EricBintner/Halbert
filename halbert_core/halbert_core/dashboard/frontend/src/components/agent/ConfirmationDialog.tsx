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
  safe: { color: 'text-green-400', bgColor: 'bg-green-500/20', icon: '✓' },
  low: { color: 'text-blue-400', bgColor: 'bg-blue-500/20', icon: 'ℹ' },
  medium: { color: 'text-yellow-400', bgColor: 'bg-yellow-500/20', icon: '⚠' },
  high: { color: 'text-orange-400', bgColor: 'bg-orange-500/20', icon: '⚠' },
  critical: { color: 'text-red-400', bgColor: 'bg-red-500/20', icon: '⛔' },
};

export function ConfirmationDialog({ 
  confirmation, 
  onConfirm, 
  onReject 
}: ConfirmationDialogProps) {
  const riskConfig = RISK_CONFIG[confirmation.riskLevel] || RISK_CONFIG.medium;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-zinc-900 rounded-lg shadow-xl max-w-md w-full mx-4 overflow-hidden border border-zinc-700">
        <div className={`${riskConfig.bgColor} px-4 py-3 border-b border-zinc-700`}>
          <div className="flex items-center gap-2">
            <span className={`text-xl ${riskConfig.color}`}>{riskConfig.icon}</span>
            <h3 className={`font-semibold ${riskConfig.color}`}>
              Confirmation Required
            </h3>
          </div>
        </div>

        <div className="p-4 space-y-4">
          <div>
            <div className="text-sm text-zinc-500 mb-1">Tool</div>
            <div className="font-mono text-sm bg-zinc-800 text-zinc-200 px-2 py-1 rounded">
              {confirmation.tool}
            </div>
          </div>

          <div>
            <div className="text-sm text-zinc-500 mb-1">Action</div>
            <div 
              className="text-sm text-zinc-200 prose prose-sm prose-invert max-w-none"
              dangerouslySetInnerHTML={{ 
                __html: confirmation.description
                  .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                  .replace(/```([\s\S]*?)```/g, '<pre class="bg-zinc-800 p-2 rounded text-xs">$1</pre>')
                  .replace(/`([^`]+)`/g, '<code class="bg-zinc-800 px-1 rounded">$1</code>')
                  .replace(/\n/g, '<br/>')
              }}
            />
          </div>

          <div className={`text-xs ${riskConfig.color} ${riskConfig.bgColor} px-2 py-1 rounded inline-block`}>
            Risk Level: {confirmation.riskLevel.toUpperCase()}
          </div>
        </div>

        <div className="flex gap-3 p-4 border-t border-zinc-700 bg-zinc-800/50">
          <button
            onClick={onReject}
            className="flex-1 px-4 py-2 text-sm font-medium text-zinc-300 bg-zinc-800 border border-zinc-600 rounded-lg hover:bg-zinc-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-zinc-900 focus:ring-zinc-500 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`
              flex-1 px-4 py-2 text-sm font-medium text-white rounded-lg
              focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-zinc-900 transition-colors
              ${confirmation.riskLevel === 'high' || confirmation.riskLevel === 'critical'
                ? 'bg-orange-600 hover:bg-orange-500 focus:ring-orange-500'
                : 'bg-blue-600 hover:bg-blue-500 focus:ring-blue-500'
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
