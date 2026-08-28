// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState, useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { apiUrl } from '@/lib/apiBase'

interface Entity {
  entity_id: string
  state: string
  attributes: Record<string, unknown>
  last_changed: string
}

interface EntityListProps {
  entities: Entity[]
}

const DOMAIN_ICONS: Record<string, string> = {
  light: 'lightbulb',
  switch: 'power',
  climate: 'thermometer',
  lock: 'lock',
  cover: 'blinds',
  fan: 'fan',
  media_player: 'speaker',
  vacuum: 'vacuum',
  binary_sensor: 'sensor',
  sensor: 'sensor',
  person: 'person',
  device_tracker: 'person',
  alarm_control_panel: 'alarm',
}

export function EntityList({ entities }: EntityListProps) {
  const [search, setSearch] = useState('')
  const [domainFilter, setDomainFilter] = useState<string | null>(null)

  const domains = useMemo(() => {
    const set = new Set<string>()
    entities.forEach((e) => {
      const d = e.entity_id.split('.')[0]
      set.add(d)
    })
    return Array.from(set).sort()
  }, [entities])

  const filtered = useMemo(() => {
    return entities.filter((e) => {
      if (domainFilter && !e.entity_id.startsWith(domainFilter + '.')) return false
      if (search) {
        const name = (e.attributes.friendly_name as string) || e.entity_id
        return name.toLowerCase().includes(search.toLowerCase())
      }
      return true
    })
  }, [entities, search, domainFilter])

  const toggleEntity = async (entityId: string, currentState: string) => {
    const domain = entityId.split('.')[0]
    const service = currentState === 'on' ? 'turn_off' : 'turn_on'
    try {
      await fetch(apiUrl('/api/home/service'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain, service, entity_id: entityId }),
      })
    } catch (e) {
      console.error('Service call failed:', e)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Entities ({filtered.length})</CardTitle>
        <div className="flex gap-2 mt-2">
          <Input
            placeholder="Search entities..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          <button
            onClick={() => setDomainFilter(null)}
            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
              !domainFilter
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-accent'
            }`}
          >
            All
          </button>
          {domains.map((d) => (
            <button
              key={d}
              onClick={() => setDomainFilter(d)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                domainFilter === d
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-accent'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-1 max-h-[60vh] overflow-auto">
          {filtered.length === 0 ? (
            <div className="text-muted-foreground text-center py-8">No entities found</div>
          ) : (
            filtered.map((e) => {
              const name = (e.attributes.friendly_name as string) || e.entity_id
              const isOn = e.state === 'on'
              const domain = e.entity_id.split('.')[0]
              const canToggle = ['light', 'switch', 'fan', 'cover', 'media_player'].includes(domain)
              return (
                <div
                  key={e.entity_id}
                  className="flex items-center justify-between px-3 py-2 rounded-md hover:bg-accent/50 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-xs text-muted-foreground font-mono shrink-0">
                      {DOMAIN_ICONS[domain] || 'circle'}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{name}</div>
                      <div className="text-xs text-muted-foreground font-mono truncate">
                        {e.entity_id}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant={isOn ? 'default' : 'secondary'} className="text-xs">
                      {e.state}
                    </Badge>
                    {canToggle && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs"
                        onClick={() => toggleEntity(e.entity_id, e.state)}
                      >
                        {isOn ? 'Off' : 'On'}
                      </Button>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </CardContent>
    </Card>
  )
}
