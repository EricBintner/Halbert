// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { useDebug } from '@/contexts/DebugContext'
import { cn } from '@/lib/utils'
import { Bug } from 'lucide-react'

/** The Debug tab: diagnostic logging toggle and captured log entries. */
export function DebugTab() {
  const { isDebugMode, setDebugMode, logs, clearLogs } = useDebug()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bug className="h-5 w-5" />
          Debug Mode
        </CardTitle>
        <CardDescription>
          Toggle diagnostic logging and inspect captured log entries.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <Label htmlFor="debug-toggle">Enable debug logging</Label>
            <p className="text-xs text-muted-foreground mt-1">
              When on, request, response, timing, and error events are captured below.
            </p>
          </div>
          <Button
            id="debug-toggle"
            variant={isDebugMode ? 'default' : 'outline'}
            size="sm"
            onClick={() => setDebugMode(!isDebugMode)}
          >
            {isDebugMode ? 'Debug ON' : 'Debug OFF'}
          </Button>
        </div>

        <div className="border border-border rounded-md flex flex-col max-h-96">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-card">
            <span className="text-sm text-foreground">Logs ({logs.length})</span>
            <button onClick={clearLogs} className="text-muted-foreground hover:text-foreground text-[10px]">Clear</button>
          </div>
          <div className="flex-1 overflow-auto p-2 text-xs font-mono">
            {logs.length === 0 ? (
              <div className="text-muted-foreground text-center py-4">No logs yet. Interact with the app to see logs.</div>
            ) : (
              logs.slice().reverse().map(log => (
                <div key={log.id} className={cn(
                  "py-0.5",
                  log.type === 'error' && "text-error",
                  log.type === 'timing' && "text-warning",
                  log.type === 'request' && "text-info",
                  log.type === 'response' && "text-success",
                  log.type === 'info' && "text-foreground"
                )}>
                  <span className="text-muted-foreground">[{log.timestamp.toLocaleTimeString()}]</span>
                  <span className="text-muted-foreground ml-1">[{log.category}]</span>
                  <span className="ml-1">{log.message}</span>
                  {log.duration && <span className="text-muted-foreground ml-1">({log.duration.toFixed(0)}ms)</span>}
                </div>
              ))
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}