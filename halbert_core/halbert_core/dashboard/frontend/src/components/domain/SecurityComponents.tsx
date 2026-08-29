// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * Security tab components — MCP Trust Boundary UI.
 *
 * Implements the Daylight Mid-Century Modern design system:
 * - Mechanical segmented rocker switches (not generic buttons)
 * - Dual-state physical vault card for Tier 2
 * - High-friction escape hatch modal with phrase typing + TTL
 * - Machined tag chip arrays (not unbounded textareas)
 * - Live telemetry bar with tabular mono counts
 *
 * Design spec: .handoff/SECURITY-TAB-VISUAL-DESIGN-AND-HANDOFF-2026-08-29.md
 * Token reference: shared-tokens/tokens.css (via tailwind.config.js)
 */
import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Globe,
  SlidersHorizontal,
  ShieldCheck,
  Lock,
  Unlock,
  AlertOctagon,
  Plus,
  X,
  Info,
  Clock,
} from 'lucide-react'

// ─────────────────────────────────────────────────────────────────────────────
// 1. TrustBoundaryTelemetryBar — live scope instrument
// ─────────────────────────────────────────────────────────────────────────────

export interface TelemetryCounts {
  tier_0: number
  tier_1: number
  tier_2: number
  total: number
  secret_tier: string
  operational_tier: string
  cloud_ok_keys_count: number
}

interface TelemetryBarProps {
  counts: TelemetryCounts | null
  loading?: boolean
}

export function TrustBoundaryTelemetryBar({ counts, loading }: TelemetryBarProps) {
  const meters = [
    {
      icon: Globe,
      label: 'PUBLIC',
      value: counts?.tier_0 ?? '--',
      color: 'text-status-nominal',
      bg: 'bg-status-nominal-bg',
    },
    {
      icon: SlidersHorizontal,
      label: 'OPERATIONAL',
      value: counts?.tier_1 ?? '--',
      color: 'text-status-warning',
      bg: 'bg-status-warning-bg',
    },
    {
      icon: ShieldCheck,
      label: 'PROTECTED',
      value: counts?.tier_2 ?? '--',
      color: 'text-status-critical',
      bg: 'bg-status-critical-bg',
    },
  ]

  return (
    <div className="bg-surface-subtle border border-border rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          Telemetry Scope
        </span>
        {loading && (
          <span className="font-mono text-[11px] text-muted-foreground animate-pulse">
            scanning...
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-6">
        {meters.map((m) => {
          const Icon = m.icon
          return (
            <div key={m.label} className="flex items-center gap-2.5">
              <div className={cn('flex items-center justify-center w-8 h-8 rounded-md', m.bg)}>
                <Icon className={cn('h-4 w-4', m.color)} />
              </div>
              <div className="flex flex-col">
                <span className="font-mono font-bold text-lg tabular-nums text-foreground leading-none">
                  {m.value}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">
                  {m.label}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. Tier1RockerControl — mechanical segmented switch
// ─────────────────────────────────────────────────────────────────────────────

type Tier1Value = 'cloud_ok' | 'local_only' | 'redact'

interface Tier1RockerProps {
  value: Tier1Value
  onChange: (v: Tier1Value) => void
  disabled?: boolean
  count?: number
}

export function Tier1RockerControl({ value, onChange, disabled, count }: Tier1RockerProps) {
  const segments: { key: Tier1Value; label: string; sub: string }[] = [
    { key: 'cloud_ok', label: 'Cloud OK', sub: 'Raw to cloud' },
    { key: 'local_only', label: 'Local Only', sub: 'Describe only' },
    { key: 'redact', label: 'Redact', sub: 'Strip value' },
  ]

  return (
    <div>
      <div className="bg-surface-subtle p-1 rounded-lg border border-border grid grid-cols-3 gap-1">
        {segments.map((seg) => {
          const active = value === seg.key
          return (
            <button
              key={seg.key}
              type="button"
              disabled={disabled}
              onClick={() => onChange(seg.key)}
              className={cn(
                'flex flex-col items-center py-2.5 px-3 rounded-md transition-all',
                'border',
                active
                  ? 'bg-surface text-foreground font-medium shadow-sm border-border/60'
                  : 'text-muted-foreground hover:text-foreground border-transparent',
                disabled && 'opacity-50 cursor-not-allowed',
              )}
            >
              <span className="font-sans text-sm font-semibold">{seg.label}</span>
              <span className="font-mono text-[11px] text-muted-foreground mt-0.5">{seg.sub}</span>
            </button>
          )
        })}
      </div>
      <div className="flex items-center gap-1.5 mt-2">
        <Info className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <p className="text-xs text-muted-foreground">
          {value === 'cloud_ok' &&
            `Cloud models see operational values directly.${count != null ? ` ${count} values accessible.` : ''}`}
          {value === 'local_only' &&
            `A deterministic description (length, charset, entropy) is returned instead of the raw value.`}
          {value === 'redact' &&
            `Values are stripped entirely. Only the key name and tier are returned.`}
        </p>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. Tier2StateCard — dual-state physical vault
// ─────────────────────────────────────────────────────────────────────────────

interface Tier2StateCardProps {
  locked: boolean
  onUnlock: () => void
  onRelock: () => void
  disabled?: boolean
  protectedCount?: number
}

export function Tier2StateCard({
  locked,
  onUnlock,
  onRelock,
  disabled,
  protectedCount,
}: Tier2StateCardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border p-5 transition-all',
        locked
          ? 'bg-surface border-border'
          : 'bg-status-critical-bg/40 border-2 border-status-critical shadow-sm',
      )}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {locked ? (
            <Lock className="h-5 w-5 text-status-nominal" />
          ) : (
            <Unlock className="h-5 w-5 text-status-critical animate-pulse" />
          )}
          <div>
            <h4 className="font-semibold text-foreground">Tier 2 — Secrets &amp; Credentials</h4>
            <p className="text-xs text-muted-foreground mt-0.5">
              Passwords, private keys, tokens, authorization headers.
            </p>
          </div>
        </div>
        <span
          className={cn(
            'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md font-mono text-xs font-semibold border',
            locked
              ? 'bg-status-nominal-bg text-status-nominal border-status-nominal-line'
              : 'bg-status-critical text-white border-status-critical animate-pulse',
          )}
        >
          {locked ? 'LOCKED (LOCAL ONLY)' : 'SECRETS EXPOSED'}
        </span>
      </div>

      {/* Body description */}
      <p className="text-sm text-muted-foreground mb-4">
        {locked ? (
          <>
            Deterministic metadata only (length, charset, entropy, breach risk, view command).
            No model in the boundary — a template cannot be talked into quoting a value.
            {protectedCount != null && (
              <span className="font-mono tabular-nums text-foreground ml-1">{protectedCount} secrets protected.</span>
            )}
          </>
        ) : (
          <>
            Raw secrets are transmitted to your cloud LLM vendor's inference logging pipelines.
            Re-lock immediately when cloud reasoning is no longer needed.
          </>
        )}
      </p>

      {/* Action area */}
      {locked ? (
        <div className="rounded-md border border-status-warning-line bg-status-warning-bg p-3">
          <div className="flex items-start gap-2">
            <AlertOctagon className="h-4 w-4 text-status-warning mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-foreground">
                <span className="font-medium">Advanced Override:</span>{' '}
                Allow cloud models to read raw secrets in plaintext.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={onUnlock}
                disabled={disabled}
                className="mt-2"
              >
                <Unlock className="h-3.5 w-3.5 mr-1.5" />
                Unlock Cloud Access...
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <Button
          onClick={onRelock}
          disabled={disabled}
          className="bg-status-critical text-white hover:bg-status-critical/90 font-semibold"
        >
          <Lock className="h-4 w-4 mr-2" />
          Re-lock Secrets Immediately
        </Button>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. EscapeHatchConfirmationModal — high-friction shutter
// ─────────────────────────────────────────────────────────────────────────────

type TTLChoice = '1h' | 'restart' | 'permanent'

interface EscapeHatchModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (ttl: TTLChoice) => void
  disabled?: boolean
}

const REQUIRED_PHRASE = 'EXPOSE SECRETS'

export function EscapeHatchConfirmationModal({
  open,
  onClose,
  onConfirm,
  disabled,
}: EscapeHatchModalProps) {
  const [phrase, setPhrase] = useState('')
  const [ttl, setTTL] = useState<TTLChoice>('1h')
  const confirmBtnRef = useRef<HTMLButtonElement>(null)

  // Reset state when modal opens/closes
  useEffect(() => {
    if (open) {
      setPhrase('')
      setTTL('1h')
    }
  }, [open])

  const phraseValid = phrase.trim() === REQUIRED_PHRASE

  const ttlOptions: { key: TTLChoice; label: string; sub: string; recommended?: boolean }[] = [
    { key: '1h', label: '1 Hour', sub: 'Auto-relocks', recommended: true },
    { key: 'restart', label: 'Until restart', sub: 'Reverts on next launch' },
    { key: 'permanent', label: 'Permanent', sub: 'Stays unlocked until manually re-locked' },
  ]

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg border-2 border-status-critical-line">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <AlertOctagon className="h-6 w-6 text-status-critical" />
            <DialogTitle className="text-status-critical">
              Expose Machine Secrets to Cloud LLMs?
            </DialogTitle>
          </div>
          <DialogDescription>
            This will transmit raw passwords, private keys, and API tokens to external
            inference vendor logging pipelines. The trust boundary will be disabled for
            all Tier 2 values.
          </DialogDescription>
        </DialogHeader>

        {/* TTL selection */}
        <div className="space-y-2 my-4">
          <Label className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            Duration
          </Label>
          <div className="space-y-1.5">
            {ttlOptions.map((opt) => (
              <label
                key={opt.key}
                className={cn(
                  'flex items-center gap-3 p-2.5 rounded-md border cursor-pointer transition-all',
                  ttl === opt.key
                    ? 'border-status-critical-line bg-status-critical-bg/50'
                    : 'border-border bg-surface-subtle hover:border-border/80',
                )}
              >
                <input
                  type="radio"
                  name="ttl"
                  checked={ttl === opt.key}
                  onChange={() => setTTL(opt.key)}
                  className="accent-status-critical"
                />
                <div className="flex-1">
                  <span className="text-sm font-medium text-foreground">{opt.label}</span>
                  {opt.recommended && (
                    <span className="ml-2 font-mono text-[10px] uppercase tracking-wider text-status-nominal">
                      Recommended
                    </span>
                  )}
                  <p className="text-xs text-muted-foreground">{opt.sub}</p>
                </div>
                {opt.key === '1h' && <Clock className="h-4 w-4 text-muted-foreground" />}
              </label>
            ))}
          </div>
        </div>

        {/* Phrase input */}
        <div className="space-y-2">
          <Label className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
            To proceed, type <span className="text-status-critical font-bold">{REQUIRED_PHRASE}</span> below:
          </Label>
          <Input
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            onKeyDown={(e: KeyboardEvent) => {
              if (e.key === 'Enter' && phraseValid && !disabled) {
                onConfirm(ttl)
              }
            }}
            placeholder={REQUIRED_PHRASE}
            className={cn(
              'font-mono tracking-wide',
              phrase && !phraseValid
                ? 'border-status-critical/50 focus:border-status-critical focus:ring-status-critical'
                : phraseValid
                  ? 'border-status-critical bg-status-critical-bg/30'
                  : 'border-status-critical/50 focus:border-status-critical focus:ring-status-critical',
            )}
            autoFocus
          />
        </div>

        {/* Buttons */}
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={onClose} autoFocus>
            Cancel &amp; Keep Locked
          </Button>
          <Button
            ref={confirmBtnRef}
            disabled={!phraseValid || disabled}
            onClick={() => onConfirm(ttl)}
            className={cn(
              'bg-status-critical text-white hover:bg-status-critical/90 font-semibold',
              !phraseValid && 'opacity-40 cursor-not-allowed',
            )}
          >
            I Accept the Risk — Expose Secrets
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. MachinedTagInput — tag chips replacing textareas
// ─────────────────────────────────────────────────────────────────────────────

interface MachinedTagInputProps {
  values: string[]
  onChange: (values: string[]) => void
  placeholder?: string
  disabled?: boolean
  /** Show a green dot on each chip (e.g. file verified on host) */
  verified?: boolean
  /** Label for the add button */
  addLabel?: string
}

export function MachinedTagInput({
  values,
  onChange,
  placeholder,
  disabled,
  verified,
  addLabel = 'Add',
}: MachinedTagInputProps) {
  const [input, setInput] = useState('')

  const addTag = () => {
    const trimmed = input.trim()
    if (trimmed && !values.includes(trimmed)) {
      onChange([...values, trimmed])
    }
    setInput('')
  }

  const removeTag = (tag: string) => {
    onChange(values.filter((v) => v !== tag))
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addTag()
    } else if (e.key === 'Backspace' && !input && values.length > 0) {
      removeTag(values[values.length - 1])
    }
  }

  return (
    <div className="bg-surface-subtle border border-border rounded-lg p-3 space-y-2">
      {/* Chips */}
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {values.map((tag) => (
            <div
              key={tag}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface border border-border text-xs font-mono shadow-2xs"
            >
              <span className="text-foreground">{tag}</span>
              {verified && (
                <span
                  className="w-1.5 h-1.5 rounded-full bg-status-nominal"
                  title="Verified on host"
                />
              )}
              <button
                type="button"
                onClick={() => removeTag(tag)}
                disabled={disabled}
                className="text-muted-foreground hover:text-foreground ml-0.5 disabled:opacity-50"
                aria-label={`Remove ${tag}`}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-center gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="font-mono text-xs bg-surface border border-input"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addTag}
          disabled={disabled || !input.trim()}
          className="shrink-0"
        >
          <Plus className="h-3.5 w-3.5 mr-1" />
          {addLabel}
        </Button>
      </div>
    </div>
  )
}
