// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * D-6: Settings -> AI Models, mounted on @halbert/model-picker's drawer.
 *
 * The drawer owns the surface and every behaviour inside it: the assignment
 * grid, the providers accordion, the auto-open, the offers for engines
 * running here but not saved, and the "nothing is using it yet" nudge. This
 * file passes in only what is Halbert's and cannot live in a package with no
 * role names and no I/O:
 *
 *  - Halbert's design language, through the drawer's `classNames` seams
 *  - the vision slot's "Auto: inherit from the chat model" copy when it is
 *    unassigned, so the UI never claims a dedicated vision model exists
 *    when there isn't one (never a model name — see UI-SPEC Q3)
 *  - the UI-SPEC §7.4 privacy badges: whether traffic leaves this machine is
 *    a permanent fact about a slot, and only the host knows what its own
 *    runtime does with a configured endpoint
 *  - the LEG-MOD-02 cloud-provider disclosure gate carried over from the
 *    deleted EndpointManager, implemented by wrapping saveEndpoint rather
 *    than forking ProviderCard
 *  - an "add a provider" control: the package auto-offers only the engines it
 *    discovered locally, so adding a cloud endpoint has to come from here
 *
 * Anything this file re-implements from the drawer is a seam the package is
 * missing — the last time that judgement went the other way, all of it was
 * copied in here and the drawer lost its only consumer.
 */

import { useCallback, useMemo, useState } from 'react'
import type { HTMLAttributes, ReactNode } from 'react'
import {
  ModelSettingsDrawer,
  ProviderCard,
  PROVIDERS,
  providerDescriptor,
  useModelPicker,
} from '@halbert/model-picker'
import type {
  EndpointTestResult,
  ModelSettingsDrawerClassNames,
  ProviderId,
  SavedEndpoint,
  UseModelPickerResult,
} from '@halbert/model-picker'
import { Brain, Check, ChevronDown, Cloud, HardDrive, X } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { CloudDisclosureModal } from '@/components/legal'
import { HALBERT_MODEL_ROLES, modelPickerTransport } from '@/lib/halbertModelRoles'
import { cn } from '@/lib/utils'

const VISION_INHERIT_COPY =
  'Auto: inherit from the chat model. Assign a dedicated model only if your chat model is text-only.'

// LEG-MOD-02: a provider triggers the cloud data-flow disclosure when it is a
// known cloud vendor, or an Ollama endpoint pointed at Ollama Cloud rather
// than a local daemon. Carried over from the deleted EndpointManager.
const DISCLOSURE_PROVIDERS = new Set<ProviderId>([
  'openai', 'anthropic', 'google', 'azure-openai', 'openai-compatible',
])

export function needsDisclosure(endpoint: Pick<SavedEndpoint, 'provider' | 'url'>): boolean {
  if (DISCLOSURE_PROVIDERS.has(endpoint.provider)) return true
  if (endpoint.provider === 'ollama') {
    try {
      const host = new URL(endpoint.url).hostname.toLowerCase()
      return host === 'ollama.com' || host.endsWith('.ollama.com')
    } catch {
      return false
    }
  }
  return false
}

function providerLabel(id: ProviderId): string {
  return PROVIDERS.find((p) => p.id === id)?.label ?? id
}

const SECTION_HEADING = 'text-xs font-medium uppercase tracking-wide text-muted-foreground'

const CONTROL =
  'h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus'

/**
 * The one grid template the assignment table is built on. Shared so the column
 * captions and the package's own rows land on the same lines — they are
 * separate grids, and a `1fr` here against an `auto` there reads as a
 * misaligned table.
 */
const ROLE_COLUMNS = 'md:grid-cols-[minmax(9rem,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_6rem]'

/**
 * RoleAssignmentRow's children, in order: the role label, its description,
 * the endpoint select, the model select, the Test button, and the live region
 * carrying the summary plus whatever `renderRoleStatus` returns. None of them
 * takes a className of its own, so each is placed and typed from here.
 */
const ROLE_ROW = cn(
  'grid gap-x-4 gap-y-3 p-4 md:items-center md:gap-y-2',
  ROLE_COLUMNS,
  'data-[assigned=no]:bg-muted/20',
  '[&>label]:text-sm [&>label]:font-medium [&>label]:text-foreground',
  'md:[&>label]:col-start-1 md:[&>label]:row-start-1',
  '[&>p]:text-xs [&>p]:leading-snug [&>p]:text-muted-foreground',
  'md:[&>p]:col-start-1 md:[&>p]:row-start-2 md:[&>p]:self-start',
  // Every state stays inside the bracket: a trailing `:hover`/`:disabled`
  // variant attaches to the row rather than the child, so the whole row would
  // restyle on the wrong element's event.
  '[&>select]:h-9 [&>select]:w-full [&>select]:min-w-0 [&>select]:rounded-md [&>select]:border',
  '[&>select]:border-input [&>select]:bg-background [&>select]:px-2 [&>select]:text-sm [&>select]:text-foreground',
  '[&>select:focus-visible]:outline-none [&>select:focus-visible]:ring-2 [&>select:focus-visible]:ring-focus',
  '[&>select:disabled]:cursor-not-allowed [&>select:disabled]:opacity-50',
  '[&>select[aria-invalid=true]]:border-warning',
  'md:[&>select:first-of-type]:col-start-2 md:[&>select:first-of-type]:row-start-1',
  'md:[&>select:last-of-type]:col-start-3 md:[&>select:last-of-type]:row-start-1',
  '[&>button]:h-9 [&>button]:w-full [&>button]:rounded-md [&>button]:border [&>button]:border-input',
  '[&>button]:bg-background [&>button]:px-3 [&>button]:text-sm [&>button]:font-medium [&>button]:text-foreground',
  '[&>button:hover]:bg-muted [&>button:disabled]:cursor-not-allowed [&>button:disabled]:opacity-50',
  '[&>button:focus-visible]:outline-none [&>button:focus-visible]:ring-2 [&>button:focus-visible]:ring-focus',
  'md:[&>button]:col-start-4 md:[&>button]:row-start-1',
  '[&>div]:flex [&>div]:flex-wrap [&>div]:items-center [&>div]:gap-x-2 [&>div]:gap-y-1',
  '[&>div]:text-xs [&>div]:text-muted-foreground',
  'md:[&>div]:col-span-4 md:[&>div]:row-start-3 md:[&>div]:mt-1',
)

/**
 * ProviderCard's children, in order: the title, the privacy badge, an optional
 * not-chat-capable notice, label/input pairs for name, address and key, the
 * local engine's status block, the reveal toggle, the action buttons and a
 * live region. Laid out as a wrapping stack: labels and inputs claim a whole
 * line each so the reveal toggle cannot drift into the button bar.
 *
 * The badge is excluded from the card's own span rules by hand: a
 * `.card > span` rule outbids the badge's classes on specificity and would
 * repaint it in the muted body colour it exists to contrast with.
 */
const PROVIDER_CARD = cn(
  'flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border bg-background p-4',
  '[&>span:not([data-locality])]:basis-full [&>span:not([data-locality])]:text-xs',
  '[&>span:not([data-locality])]:text-muted-foreground',
  '[&>span:first-child:not([data-locality])]:basis-auto',
  '[&>span:first-child:not([data-locality])]:text-sm [&>span:first-child:not([data-locality])]:font-medium',
  '[&>span:first-child:not([data-locality])]:text-foreground',
  '[&>[data-locality]]:ml-auto',
  '[&>[data-badge]]:rounded-md [&>[data-badge]]:bg-warning-muted [&>[data-badge]]:px-2 [&>[data-badge]]:py-1 [&>[data-badge]]:text-warning',
  '[&>label]:basis-full [&>label]:text-[10px] [&>label]:font-medium [&>label]:uppercase [&>label]:tracking-wide [&>label]:text-muted-foreground',
  '[&>input]:h-9 [&>input]:basis-full [&>input]:min-w-0 [&>input]:rounded-md [&>input]:border [&>input]:border-input',
  '[&>input]:bg-background [&>input]:px-3 [&>input]:text-sm [&>input]:text-foreground',
  '[&>input:focus-visible]:outline-none [&>input:focus-visible]:ring-2 [&>input:focus-visible]:ring-focus',
  '[&>div]:basis-full [&>div]:flex [&>div]:flex-wrap [&>div]:items-center [&>div]:gap-x-3 [&>div]:gap-y-1',
  '[&>div]:rounded-md [&>div]:border [&>div]:bg-muted [&>div]:px-3 [&>div]:py-2 [&>div]:text-xs [&>div]:text-muted-foreground',
  '[&>div[data-engine=running]]:border-success/40 [&>div[data-engine=stopped]]:border-border',
  '[&>div[data-engine=running]>span:first-child]:text-success',
  '[&>div>span:first-child]:font-medium [&>div>span:first-child]:text-foreground',
  '[&>div>button]:ml-auto [&>div>button]:rounded-md [&>div>button]:border [&>div>button]:border-input',
  '[&>div>button]:bg-background [&>div>button]:px-2 [&>div>button]:py-1 [&>div>button]:text-xs [&>div>button]:text-foreground',
  '[&>div>button:hover]:bg-muted [&>div>button:disabled]:cursor-not-allowed [&>div>button:disabled]:opacity-50',
  '[&>button]:h-9 [&>button]:rounded-md [&>button]:border [&>button]:border-input [&>button]:bg-background',
  '[&>button]:px-3 [&>button]:text-sm [&>button]:font-medium [&>button]:text-foreground',
  '[&>button:hover]:bg-muted [&>button:disabled]:cursor-not-allowed [&>button:disabled]:opacity-50',
  '[&>button:focus-visible]:outline-none [&>button:focus-visible]:ring-2 [&>button:focus-visible]:ring-focus',
  // The reveal toggle takes a whole line: sharing one with Save and Remove
  // would read as a fourth action on the endpoint rather than on the key.
  '[&>button[aria-pressed]]:basis-full [&>button[aria-pressed]]:h-auto',
  '[&>button[aria-pressed]]:border-transparent [&>button[aria-pressed]]:bg-transparent [&>button[aria-pressed]]:px-0',
  '[&>button[aria-pressed]]:text-xs [&>button[aria-pressed]]:text-muted-foreground',
  '[&>button[aria-pressed]:hover]:bg-transparent [&>button[aria-pressed]:hover]:text-foreground',
  // The live region collapses out of the layout but is never display:none — a
  // region hidden at the moment it gains text is not reliably announced, which
  // is why the package renders it on every pass in the first place.
  '[&>p]:basis-full [&>p]:text-xs [&>p]:text-muted-foreground [&>p:empty]:sr-only',
)

/**
 * The drawer's "saved but nothing is using it yet" offer: a line of copy and
 * two buttons, in that order. Accepting is the weighted control; declining
 * stays quiet, because the offer is a guess.
 */
const ASSIGN_PROMPT = cn(
  'flex flex-wrap items-center gap-3 rounded-lg border border-info/40 bg-info-muted p-3',
  '[&>p]:text-sm [&>p]:text-foreground',
  '[&>button]:h-9 [&>button]:rounded-md [&>button]:px-3 [&>button]:text-sm',
  '[&>button:focus-visible]:outline-none [&>button:focus-visible]:ring-2 [&>button:focus-visible]:ring-focus',
  '[&>button:first-of-type]:ml-auto [&>button:first-of-type]:border [&>button:first-of-type]:border-input',
  '[&>button:first-of-type]:bg-background [&>button:first-of-type]:font-medium [&>button:first-of-type]:text-foreground',
  '[&>button:first-of-type:hover]:bg-muted',
  '[&>button:first-of-type:disabled]:cursor-not-allowed [&>button:first-of-type:disabled]:opacity-50',
  '[&>button:last-of-type]:text-muted-foreground [&>button:last-of-type:hover]:text-foreground',
)

const DRAWER_CLASSES: ModelSettingsDrawerClassNames = {
  root: 'space-y-4',
  rolesSection: 'overflow-hidden rounded-lg border border-border',
  roleGrid: 'divide-y divide-border',
  roleRow: ROLE_ROW,
  assignPrompt: ASSIGN_PROMPT,
  providersSection: 'overflow-hidden rounded-lg border border-border',
  providersTrigger: cn(
    'flex w-full items-center justify-between gap-3 bg-muted/40 px-4 py-3 text-left hover:bg-muted',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus',
  ),
  providersRegion: 'space-y-6 border-t border-border p-4',
  providerGroup: 'space-y-3',
  providerGroupHeading: cn('flex flex-wrap items-center gap-2', SECTION_HEADING),
  providerCard: PROVIDER_CARD,
  note: 'text-xs text-muted-foreground',
  announcement: 'sr-only',
}

/**
 * UI-SPEC §7.4. Whether a slot's traffic leaves this machine is a standing
 * fact about it rather than an event, so it is stated on every row and card
 * instead of only at the moment a cloud provider is added.
 */
function LocalityBadge({
  isLocal,
  className,
  ...rest
}: { isLocal: boolean } & HTMLAttributes<HTMLSpanElement>) {
  const Icon = isLocal ? HardDrive : Cloud
  return (
    <span
      {...rest}
      data-locality={isLocal ? 'local' : 'cloud'}
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5',
        'text-[10px] font-medium uppercase tracking-wide',
        isLocal ? 'border-success/40 text-success' : 'border-warning/40 text-warning',
        className,
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {isLocal ? 'Local' : 'Cloud'}
      <span className="sr-only">
        {isLocal ? ' — runs on this machine' : ' — prompts leave this machine'}
      </span>
    </span>
  )
}

/** The card states its own locality; beside a heading that already says it,
 *  the badge is decoration and would only pad the section's name. */
const groupBadge = (group: 'local' | 'cloud'): ReactNode => (
  <LocalityBadge isLocal={group === 'local'} aria-hidden="true" />
)

const providerBadge = (
  endpoint: SavedEndpoint | undefined,
  provider: ProviderId,
): ReactNode => (
  <LocalityBadge isLocal={providerDescriptor(endpoint?.provider ?? provider).isLocal} />
)

/**
 * Where a role's traffic goes, or null when the slot is empty. An endpoint
 * that is down lists no models, so the provider answers for the assignment
 * rather than the badge silently vanishing whenever the engine is stopped.
 */
function roleLocality(picker: UseModelPickerResult, roleId: string): boolean | null {
  const assignment = picker.assignmentFor(roleId)
  if (!assignment?.enabled || !assignment.model) return null
  const model = picker.models.find(
    (m) => m.endpointId === assignment.endpointId && m.id === assignment.model,
  )
  if (model) return model.isLocal
  const endpoint = picker.endpointFor(assignment.endpointId)
  return endpoint ? providerDescriptor(endpoint.provider).isLocal : null
}

function RoleStatus({
  isLocal,
  result,
}: {
  isLocal: boolean | null
  result: EndpointTestResult | undefined
}) {
  return (
    <>
      {isLocal === null ? null : <LocalityBadge isLocal={isLocal} />}
      {result ? (
        <span
          data-result={result.ok ? 'ok' : 'failed'}
          className={cn(
            'inline-flex items-center gap-1 font-medium',
            result.ok ? 'text-success' : 'text-error',
          )}
        >
          {result.ok ? (
            <Check className="h-3 w-3" aria-hidden="true" />
          ) : (
            <X className="h-3 w-3" aria-hidden="true" />
          )}
          {/* Colour alone must not be what says whether the test passed. */}
          <span className="sr-only">{result.ok ? 'Passed:' : 'Failed:'}</span>
          {result.message}
        </span>
      ) : null}
    </>
  )
}

/** The provider picker for a brand-new cloud endpoint: the package auto-offers
 *  only the engines it discovered on this machine, so a vendor that has to be
 *  typed in has to be reached from here. */
function AddProviderControl({ picker }: { picker: UseModelPickerResult }) {
  const [selected, setSelected] = useState<ProviderId | ''>('')
  const configured = new Set(picker.config.endpoints.map((e) => e.provider))
  const offerable = PROVIDERS.filter((p) => !configured.has(p.id))

  if (offerable.length === 0 && !selected) return null

  return (
    <div className="space-y-3 rounded-lg border border-dashed border-border p-4">
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="model-settings-add-provider" className={SECTION_HEADING}>
          Add a provider
        </label>
        <select
          id="model-settings-add-provider"
          value={selected}
          onChange={(event) => setSelected(event.target.value as ProviderId | '')}
          className={cn(CONTROL, 'min-w-[12rem] flex-1 px-2')}
        >
          <option value="">Choose a provider…</option>
          {offerable.map((p) => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
      </div>

      {selected ? (
        <ProviderCard
          picker={picker}
          provider={selected}
          onSaved={() => setSelected('')}
          renderBadge={providerBadge}
          className={PROVIDER_CARD}
        />
      ) : null}
    </div>
  )
}

interface PendingSave {
  endpoint: SavedEndpoint
  resolve: () => void
}

export function ModelSettings() {
  const picker = useModelPicker({
    transport: modelPickerTransport,
    roles: HALBERT_MODEL_ROLES,
  })
  const [pending, setPending] = useState<PendingSave | null>(null)

  const gatedSaveEndpoint = useCallback(
    (endpoint: SavedEndpoint) => {
      if (!needsDisclosure(endpoint)) return picker.saveEndpoint(endpoint)
      return new Promise<void>((resolve) => {
        setPending({ endpoint, resolve })
      })
    },
    [picker],
  )

  const handleAccept = useCallback(async () => {
    if (pending) {
      await picker.saveEndpoint(pending.endpoint)
      pending.resolve()
    }
    setPending(null)
  }, [pending, picker])

  const handleDecline = useCallback(() => {
    pending?.resolve()
    setPending(null)
  }, [pending])

  const visionAssignment = picker.assignmentFor('vision_model')
  const visionUnassigned = !visionAssignment?.enabled

  const displayRoles = useMemo(
    () =>
      HALBERT_MODEL_ROLES.map((role) =>
        role.id === 'vision_model' && visionUnassigned
          ? { ...role, description: VISION_INHERIT_COPY }
          : role,
      ),
    [visionUnassigned],
  )

  const gatedPicker: UseModelPickerResult = useMemo(
    () => ({ ...picker, roles: displayRoles, saveEndpoint: gatedSaveEndpoint }),
    [picker, displayRoles, gatedSaveEndpoint],
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5" />
          AI Models
        </CardTitle>
        <CardDescription>
          Which model answers what, and where those models come from. Nothing leaves
          this machine unless a cloud provider is configured below.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {picker.error ? (
          <p
            role="alert"
            className="rounded-md border border-error/40 bg-error-muted px-3 py-2 text-sm text-error"
          >
            {picker.error}
          </p>
        ) : null}

        <ModelSettingsDrawer
          picker={gatedPicker}
          groupProviders
          classNames={DRAWER_CLASSES}
          rolesHeader={
            <div
              aria-hidden="true"
              className={cn(
                'hidden gap-x-4 border-b border-border bg-muted/40 px-4 py-2 md:grid',
                ROLE_COLUMNS,
                SECTION_HEADING,
              )}
            >
              <span>Role</span>
              <span>Endpoint</span>
              <span>Model</span>
              <span>Test</span>
            </div>
          }
          renderRoleStatus={(role, result) => (
            <RoleStatus isLocal={roleLocality(picker, role.id)} result={result} />
          )}
          renderProviderBadge={providerBadge}
          renderGroupBadge={groupBadge}
          renderProvidersLabel={(open, count) => (
            <>
              <span className="flex items-center gap-2 text-sm font-medium text-foreground">
                Providers
                <span className="rounded-full bg-background px-2 py-0.5 text-xs font-normal text-muted-foreground">
                  {count}
                </span>
              </span>
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  'h-4 w-4 shrink-0 text-muted-foreground transition-transform',
                  open && 'rotate-180',
                )}
              />
            </>
          )}
          providersFooter={<AddProviderControl picker={gatedPicker} />}
        />

        <CloudDisclosureModal
          open={pending !== null}
          onOpenChange={(open) => {
            if (!open) handleDecline()
          }}
          onAccept={() => void handleAccept()}
          onDecline={handleDecline}
          providerName={pending ? providerLabel(pending.endpoint.provider) : undefined}
        />
      </CardContent>
    </Card>
  )
}
