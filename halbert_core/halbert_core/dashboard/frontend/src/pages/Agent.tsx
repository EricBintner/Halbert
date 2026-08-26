// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Agent Page
 *
 * The conversation with the host, reachable from the browsing navigation.
 * It is the same canvas the engaged surface gives the whole window —
 * this page is the way in while you are browsing dashboard pages, so it also
 * offers the jump to the full surface.
 */

import { PageHeader } from '@/components/domain';
import { AgentChat } from '@/components/agent';
import { MessageSquare, Maximize2, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useShellMode } from '@/contexts/ShellModeContext';
import { useHostIdentity } from '@/hooks/useHostIdentity';
import { useState } from 'react';

export function Agent() {
  const [showHistory, setShowHistory] = useState(false);
  const { setMode } = useShellMode();
  // Slow poll: this page only needs the machine's name for the button label.
  const { identity } = useHostIdentity(60_000);
  const hostName = identity?.display_name || 'Halbert';

  return (
    <div className="flex flex-col h-full">
      <PageHeader
        title="Talk to this machine"
        description="The host speaks for itself — vitals, configuration and terminals in one conversation"
        icon={<MessageSquare className="h-6 w-6" />}
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
            <Button
              variant="default"
              size="sm"
              onClick={() => setMode('engaged')}
              className="gap-2"
              title={`Open ${hostName} full screen (Cmd/Ctrl+B)`}
            >
              <Maximize2 className="h-4 w-4" />
              {hostName}
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
