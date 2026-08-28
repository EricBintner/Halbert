// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { HomeConnectionForm } from '@/components/HomeConnectionForm'
import { EntityList } from '@/components/EntityList'
import { apiUrl } from '@/lib/apiBase'

interface Entity {
  entity_id: string
  state: string
  attributes: Record<string, unknown>
  last_changed: string
}

export function Home() {
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)
  const [entities, setEntities] = useState<Entity[]>([])

  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/home/status'))
      const data = await res.json()
      setConnected(data.connected)
      return data.connected
    } catch {
      setConnected(false)
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  const loadEntities = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/home/entities'))
      const data = await res.json()
      setEntities(data.entities || [])
    } catch (e) {
      console.error('Failed to load entities:', e)
    }
  }, [])

  useEffect(() => {
    (async () => {
      const isConnected = await checkStatus()
      if (isConnected) {
        await loadEntities()
      }
    })()
  }, [checkStatus, loadEntities])

  const handleConnected = async () => {
    setConnected(true)
    await loadEntities()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    )
  }

  if (!connected) {
    return <HomeConnectionForm onConnected={handleConnected} />
  }

  return (
    <div className="space-y-6">
      {/* Connection status banner */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Home</h2>
          <Badge variant="default" className="bg-success text-success-foreground">
            Connected
          </Badge>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={async () => {
            await checkStatus()
            if (connected) await loadEntities()
          }}
        >
          Refresh
        </Button>
      </div>

      {/* Entity browser */}
      <EntityList entities={entities} />
    </div>
  )
}
