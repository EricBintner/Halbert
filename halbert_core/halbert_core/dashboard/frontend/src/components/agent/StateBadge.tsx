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
    color: 'text-blue-600 dark:text-blue-400', 
    bgColor: 'bg-blue-100 dark:bg-blue-500/20',
    pulseColor: 'bg-blue-500'
  },
  searching: { 
    label: 'Searching', 
    color: 'text-purple-600 dark:text-purple-400', 
    bgColor: 'bg-purple-100 dark:bg-purple-500/20',
    pulseColor: 'bg-purple-500'
  },
  reading: { 
    label: 'Reading', 
    color: 'text-cyan-600 dark:text-cyan-400', 
    bgColor: 'bg-cyan-100 dark:bg-cyan-500/20',
    pulseColor: 'bg-cyan-500'
  },
  executing: { 
    label: 'Executing', 
    color: 'text-orange-600 dark:text-orange-400', 
    bgColor: 'bg-orange-100 dark:bg-orange-500/20',
    pulseColor: 'bg-orange-500'
  },
  observing: { 
    label: 'Observing', 
    color: 'text-yellow-600 dark:text-yellow-400', 
    bgColor: 'bg-yellow-100 dark:bg-yellow-500/20',
    pulseColor: 'bg-yellow-500'
  },
  responding: { 
    label: 'Responding', 
    color: 'text-green-600 dark:text-green-400', 
    bgColor: 'bg-green-100 dark:bg-green-500/20',
    pulseColor: 'bg-green-500'
  },
  awaiting_confirmation: { 
    label: 'Awaiting', 
    color: 'text-amber-600 dark:text-amber-400', 
    bgColor: 'bg-amber-100 dark:bg-amber-500/20',
    pulseColor: 'bg-amber-500'
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
  const config = STATE_CONFIG[state];
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
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${config.pulseColor}`} />
          <span className={`relative inline-flex rounded-full h-2 w-2 ${config.pulseColor}`} />
        </span>
      )}
    </div>
  );
}

export default StateBadge;
