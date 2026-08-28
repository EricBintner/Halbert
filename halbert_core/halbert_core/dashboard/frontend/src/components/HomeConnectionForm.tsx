// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiUrl } from '@/lib/apiBase'

interface HomeConnectionFormProps {
  onConnected: () => void
}

export function HomeConnectionForm({ onConnected }: HomeConnectionFormProps) {
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [verifySsl, setVerifySsl] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    if (!url || !token) {
      setError('Both URL and token are required')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(apiUrl('/api/home/config'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, token, verify_ssl: verifySsl }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Failed to save config')
      }

      // Test connection
      const statusRes = await fetch(apiUrl('/api/home/status'))
      const status = await statusRes.json()
      if (status.connected) {
        onConnected()
      } else {
        setError('Config saved but connection failed. Check URL and token.')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="max-w-lg mx-auto mt-12">
      <CardHeader>
        <CardTitle>Connect to Home Assistant</CardTitle>
        <CardDescription>
          Enter your Home Assistant URL and long-lived access token.
          You can generate a token in HA under Settings → People → Your Profile → Long-Lived Access Tokens.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="ha-url">Home Assistant URL</Label>
          <Input
            id="ha-url"
            placeholder="http://homeassistant.local:8123"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="ha-token">Access Token</Label>
          <Input
            id="ha-token"
            type="password"
            placeholder="eyJ..."
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </div>
        <div className="flex items-center gap-2">
          <input
            id="ha-ssl"
            type="checkbox"
            checked={verifySsl}
            onChange={(e) => setVerifySsl(e.target.checked)}
            className="rounded border-border"
          />
          <Label htmlFor="ha-ssl" className="text-sm font-normal cursor-pointer">
            Verify SSL certificate
          </Label>
        </div>
        {error && (
          <div className="text-sm text-error bg-error/10 border border-error/30 rounded p-3">
            {error}
          </div>
        )}
        <Button onClick={handleSave} disabled={saving} className="w-full">
          {saving ? 'Connecting...' : 'Connect'}
        </Button>
      </CardContent>
    </Card>
  )
}
