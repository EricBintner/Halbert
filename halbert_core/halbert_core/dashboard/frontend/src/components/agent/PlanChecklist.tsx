/**
 * PlanChecklist Component
 * 
 * Displays the agent's plan as an interactive checklist.
 * Based on research5.md Part 8.3.
 */

import { type PlanStep } from '../../hooks/useAgentStream';

interface PlanChecklistProps {
  plan: PlanStep[];
  currentStep: number;
}

const STATUS_ICONS: Record<PlanStep['status'], string> = {
  pending: '○',
  in_progress: '◐',
  completed: '●',
  failed: '✗',
};

const STATUS_COLORS: Record<PlanStep['status'], string> = {
  pending: 'text-muted-foreground',
  in_progress: 'text-blue-600 dark:text-blue-400',
  completed: 'text-green-600 dark:text-green-400',
  failed: 'text-destructive',
};

export function PlanChecklist({ plan, currentStep }: PlanChecklistProps) {
  if (plan.length === 0) {
    return (
      <div className="text-xs text-muted-foreground italic">
        No plan yet...
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <h4 className="text-xs font-medium text-muted-foreground">Plan</h4>
      <ul className="space-y-0.5">
        {plan.map((step, index) => (
          <li 
            key={index}
            className={`
              flex items-start gap-1.5 text-xs
              ${index === currentStep ? 'font-medium' : ''}
            `}
          >
            <span className={`${STATUS_COLORS[step.status]} flex-shrink-0 mt-0.5`}>
              {STATUS_ICONS[step.status]}
            </span>
            <span className={step.status === 'completed' ? 'text-muted-foreground' : 'text-foreground'}>
              {step.step}
            </span>
            {step.tool && (
              <span className="text-[10px] text-muted-foreground bg-muted px-1 py-0.5 rounded">
                {step.tool}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default PlanChecklist;
