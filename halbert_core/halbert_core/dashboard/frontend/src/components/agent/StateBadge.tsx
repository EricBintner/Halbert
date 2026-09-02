// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * StateBadge Component
 * 
 * Displays the current agent state with appropriate styling.
 * Based on research5.md Part 8.3.
 */

import { type AgentState } from '../../hooks/useAgentStream';

interface StateBadgeProps {
  state: AgentState;
  size?: 'sm' | 'md' | 'lg';
  showPulse?: boolean;
}

const STATE_CONFIG: Record<AgentState, { label: string; color: string; bgColor: string; pulseColor: string }> = {
  idle: { 
    label: 'Idle', 
    color: 'text-muted-foreground', 
    bgColor: 'bg-muted',
    pulseColor: 'bg-muted-foreground'
  },
  planning: {
    label: 'Planning',
    color: 'text-info dark:text-info',
    bgColor: 'bg-info-muted dark:bg-info/20',
    pulseColor: 'bg-info'
  },
  searching: {
    label: 'Searching',
    color: 'text-info dark:text-info',
    bgColor: 'bg-info-muted dark:bg-info/20',
    pulseColor: 'bg-info'
  },
  reading: {
    label: 'Reading',
    color: 'text-info dark:text-info',
    bgColor: 'bg-info-muted dark:bg-info/20',
    pulseColor: 'bg-info'
  },
  executing: { 
    label: 'Executing', 
    color: 'text-warning dark:text-warning', 
    bgColor: 'bg-warning-muted dark:bg-warning/20',
    pulseColor: 'bg-warning'
  },
  observing: {
    label: 'Observing',
    color: 'text-warning dark:text-warning',
    bgColor: 'bg-warning-muted dark:bg-warning/20',
    pulseColor: 'bg-warning'
  },
  reflecting: {
    label: 'Reflecting',
    color: 'text-info dark:text-info',
    bgColor: 'bg-info-muted dark:bg-info/20',
    pulseColor: 'bg-info'
  },
  responding: {
    label: 'Responding', 
    color: 'text-success dark:text-success', 
    bgColor: 'bg-success-muted dark:bg-success/20',
    pulseColor: 'bg-success'
  },
  awaiting_confirmation: { 
    label: 'Awaiting', 
    color: 'text-warning dark:text-warning', 
    bgColor: 'bg-warning-muted dark:bg-warning/20',
    pulseColor: 'bg-warning'
  },
  error: { 
    label: 'Error', 
    color: 'text-destructive', 
    bgColor: 'bg-destructive/10',
    pulseColor: 'bg-destructive'
  },
};

const SIZE_CLASSES = {
  sm: 'px-1.5 py-0.5 text-[10px]',
  md: 'px-2 py-0.5 text-xs',
  lg: 'px-3 py-1 text-sm',
};

export function StateBadge({ state, size = 'md', showPulse = true }: StateBadgeProps) {
  const config = STATE_CONFIG[state] ?? STATE_CONFIG.idle;
  const isActive = !['idle', 'error'].includes(state);
  
  return (
    <div 
      className={`
        inline-flex items-center gap-2 rounded-full font-medium
        ${config.bgColor} ${config.color} ${SIZE_CLASSES[size]}
      `}
    >
      <span>{config.label}</span>
      {showPulse && isActive && (
        <span className="relative flex h-2 w-2">
          {/* The ping is decoration; for a reader who has asked the system
              for less movement it is nausea. The dot stays — it is the part
              that carries the meaning (R11-06). */}
          <span className={`motion-safe:animate-ping motion-reduce:hidden absolute inline-flex h-full w-full rounded-full opacity-75 ${config.pulseColor}`} />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${config.pulseColor}`} />
        </span>
      )}
    </div>
  );
}

export default StateBadge;
