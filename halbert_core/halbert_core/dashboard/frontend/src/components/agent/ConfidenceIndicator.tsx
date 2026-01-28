/**
 * ConfidenceIndicator Component
 * 
 * Visual indicator of agent confidence level with CRAG action.
 */

import { type CRAGAction } from '../../hooks/useAgentStream';

interface ConfidenceIndicatorProps {
  confidence: number;
  cragAction?: CRAGAction;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

const CRAG_CONFIG: Record<CRAGAction, { label: string; color: string }> = {
  CORRECT: { label: 'High confidence', color: 'text-green-600 dark:text-green-400' },
  AMBIGUOUS: { label: 'Uncertain', color: 'text-yellow-600 dark:text-yellow-400' },
  INCORRECT: { label: 'Low confidence', color: 'text-destructive' },
  PENDING: { label: 'Evaluating...', color: 'text-muted-foreground' },
};

const SIZE_CONFIG = {
  sm: { bar: 'h-1', text: 'text-[10px]', width: 'w-12' },
  md: { bar: 'h-1.5', text: 'text-xs', width: 'w-16' },
  lg: { bar: 'h-2', text: 'text-sm', width: 'w-24' },
};

export function ConfidenceIndicator({
  confidence,
  cragAction = 'PENDING',
  size = 'md',
  showLabel = true,
}: ConfidenceIndicatorProps) {
  const cragConfig = CRAG_CONFIG[cragAction];
  const sizeConfig = SIZE_CONFIG[size];
  
  // Calculate color based on confidence
  const getBarColor = () => {
    if (confidence >= 0.7) return 'bg-green-500';
    if (confidence >= 0.5) return 'bg-yellow-500';
    if (confidence >= 0.3) return 'bg-orange-500';
    return 'bg-red-500';
  };

  const percentage = Math.round(confidence * 100);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        {/* Progress bar */}
        <div className={`${sizeConfig.width} bg-muted rounded-full overflow-hidden`}>
          <div
            className={`${sizeConfig.bar} ${getBarColor()} transition-all duration-300`}
            style={{ width: `${percentage}%` }}
          />
        </div>
        
        {/* Percentage */}
        <span className={`${sizeConfig.text} font-mono text-muted-foreground`}>
          {percentage}%
        </span>
      </div>
      
      {/* CRAG label */}
      {showLabel && (
        <span className={`${sizeConfig.text} ${cragConfig.color}`}>
          {cragConfig.label}
        </span>
      )}
    </div>
  );
}

/**
 * Circular confidence indicator variant
 */
interface CircularConfidenceProps {
  confidence: number;
  size?: number;
  strokeWidth?: number;
}

export function CircularConfidence({
  confidence,
  size = 48,
  strokeWidth = 4,
}: CircularConfidenceProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - confidence * circumference;
  
  const getColor = () => {
    if (confidence >= 0.7) return '#22c55e'; // green-500
    if (confidence >= 0.5) return '#eab308'; // yellow-500
    if (confidence >= 0.3) return '#f97316'; // orange-500
    return '#ef4444'; // red-500
  };

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-muted"
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={getColor()}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-300"
        />
      </svg>
      {/* Center text */}
      <span className="absolute text-xs font-semibold text-foreground">
        {Math.round(confidence * 100)}
      </span>
    </div>
  );
}

export default ConfidenceIndicator;
