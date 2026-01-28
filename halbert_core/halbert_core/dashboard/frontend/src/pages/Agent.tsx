/**
 * Agent Page
 * 
 * Cascade-style agent chat interface.
 * Based on research2.md: State machine that streams internal logs to user.
 */

import { PageHeader } from '@/components/domain';
import { AgentChat } from '@/components/agent';
import { Bot, Settings, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useState } from 'react';

export function Agent() {
  const [showHistory, setShowHistory] = useState(false);

  return (
    <div className="flex flex-col h-full">
      <PageHeader
        title="Halbert Agent"
        description="AI-powered system assistant with state machine workflow"
        icon={<Bot className="h-6 w-6" />}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowHistory(!showHistory)}
              className="gap-2"
            >
              <History className="h-4 w-4" />
              History
            </Button>
            <Button variant="outline" size="sm" className="gap-2">
              <Settings className="h-4 w-4" />
              Settings
            </Button>
          </div>
        }
      />
      
      <div className="flex-1 min-h-0">
        <AgentChat className="h-full" />
      </div>
    </div>
  );
}

export default Agent;
