# Design Review: G12 — Frontend Devices Page & Pairing Flow (P7b/P7c)

**To:** Design Review / Implementation AI
**From:** GLM session (singular-entity worktree)
**Date:** 2026-08-31
**Status:** Ready for design review before implementation

---

## 1. Objective

Build the Settings -> Devices page and pairing flow modal so a user can manage their paired Halbert devices ("bodies") from a single UI surface. This is the user-facing half of the singular-entity product language: devices and bodies, not nodes and peers.

**Two sub-tasks:**
- **P7b — Devices page**: A new Settings tab showing paired devices, entity mode toggle, body name, WoL toggle, capability discovery, and device removal.
- **P7c — Pairing modal**: "Add a device to Halbert" flow — mDNS scan or manual URL entry, PIN confirmation, singular/independent mode choice.

---

## 2. Backend API surface (already shipped — P7a by Opus)

All endpoints are live and tested (`tests/test_device_routes.py`, 20 tests passing). The frontend consumes these; no backend work is needed.

### Devices router (`routes/devices.py`, mounted at `/api`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/devices` | List paired devices + this node's entity identity (mode, body_name, canonical URLs) |
| `PUT` | `/api/devices/entity-mode` | Toggle singular vs independent (writes `being.yml`: `canonical_memory_url`, `canonical_thread_url`) |
| `PUT` | `/api/devices/body-name` | Set this node's body name ("desk", "home", "kitchen") |
| `PUT` | `/api/devices/{node_id}/capabilities` | Manually set a device's capabilities (P5c vocabulary) |
| `POST` | `/api/devices/{node_id}/discover` | Live MCP `tools/list` probe -> capability inference |
| `PUT` | `/api/devices/{node_id}/wol` | Toggle Wake-on-LAN (thin alias of `/api/peers/{node_id}/wol`) |
| `DELETE` | `/api/devices/{node_id}` | Remove device (surgical token revocation, record retained) |

### Peers router (`routes/peers.py` — pairing handshake, already exists)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/peers/pair` | Request pairing -> returns PIN |
| `POST` | `/api/peers/verify` | Confirm PIN -> returns bearer token |
| `GET` | `/api/peers/discovered` | mDNS-discovered peers (LAN only) |

### `GET /api/devices` response shape

```json
{
  "status": "ok",
  "entity_mode": "independent",       // "singular" | "independent"
  "body_name": "workstation",          // this node's body label
  "canonical_memory_url": "",          // empty in independent mode
  "canonical_thread_url": "",
  "devices": [
    {
      "node_id": "desk",
      "node_name": "Mac Studio",
      "role": "compute_provider",
      "endpoint": "http://desk.lan:8000",
      "capabilities": ["gpu_llm", "mcp", "terminal"],
      "compute_direction": "outbound",
      "wol_enabled": false,
      "wol_mac": null,
      "wol_broadcast": null,
      "paired_at": "2026-08-31T12:00:00Z",
      "last_seen": "2026-08-31T20:00:00Z",
      "revoked": false
    }
  ]
}
```

---

## 3. Existing frontend patterns to follow

### Settings tab system (`pages/Settings.tsx`)

The Settings page uses a `NavRail` from `@halbert/design-system` with grouped sections. Each tab is a URL param (`?tab=devices`). The tab list is a `const` tuple and a `settingsTabFromParam()` helper. New tabs are added by:

1. Adding the tab id to `SETTINGS_TABS`
2. Adding a `SettingsNavItem` to `SETTINGS_SECTIONS`
3. Rendering `<TabsContent value="devices">` in the page body

**Current tab groups:**
- Personality: being
- Intelligence: ai, knowledge
- System & Security: safety, alerts, security, vision, audio
- General: system, about
- Developer: debug

**Proposed placement:** A new "Devices" section between "Personality" and "Intelligence", or as the first item in a new "Federation" section. The product language is "your Halbert devices" — this is identity-level, not system-level.

### Tab component pattern (`components/settings/tabs/BeingTab.tsx`)

Each tab is a self-contained component in `components/settings/tabs/`. Pattern:
- `useState` for config, loading, saving, toast
- `useEffect` to load on mount via `fetch(`${API_BASE}/...`)`
- `Card` / `CardHeader` / `CardContent` from `@/components/ui/card`
- `Button` from `@/components/ui/button`
- `Input` / `Label` from `@/components/ui/input` and `label`
- Icons from `lucide-react` (no emojis — global rule)
- Toast via the shared `Toast` component from `@/components/ui/confirm-dialog`

### Existing fleet components (reuse, don't duplicate)

| Component | Location | Reuse strategy |
|-----------|----------|----------------|
| `PeerPairingModal` | `components/fleet/PeerPairingModal.tsx` | **Reuse as-is** for P7c. Already has Discovered/Manual tabs, PIN flow, `onPaired` callback. The Devices page's "Add Device" button opens this modal. |
| `DiscoveredPeerCard` | `components/fleet/DiscoveredPeerCard.tsx` | Used inside `PeerPairingModal`. No changes needed. |
| `ComputePeerCard` | `components/llm/ComputePeerCard.tsx` | The AI tab's home-variant surface. Stays in the AI tab. The Devices page shows a read-only summary of the compute link, not a duplicate of this card. |
| `peerApi.ts` | `lib/peerApi.ts` | **Extend** with device API functions. Existing `requestPairing`, `verifyPairing`, `listDiscoveredPeers`, `setPeerToken` are reused. Add `listDevices`, `setEntityMode`, `setBodyName`, `toggleWol`, `removeDevice`, `discoverCapabilities`. |

### UI primitives (shadcn/ui pattern)

All UI primitives are in `components/ui/`:
- `dialog.tsx` — Radix Dialog wrapper (used by `PeerPairingModal`)
- `switch.tsx` — toggle switch (for WoL, entity mode)
- `badge.tsx` — capability badges
- `confirm-dialog.tsx` — confirmation dialog + `Toast`
- `card.tsx`, `button.tsx`, `input.tsx`, `label.tsx`, `tabs.tsx`

### Test pattern (`ComputePeerCard.test.tsx`)

Vitest + `@testing-library/react` + `userEvent`. Mocks `fetch` with `vi.fn()` returning `jsonResponse()` helpers. Tests render the component, interact, and assert on DOM text and fetch calls.

---

## 4. Proposed component tree

```
Settings.tsx
  └─ TabsContent value="devices"
       └─ <DevicesTab />                          (new — P7b)

DevicesTab
  ├─ EntityIdentityCard                           (new)
  │    ├─ body_name display + edit
  │    ├─ entity_mode toggle (singular/independent)
  │    └─ canonical URL display (read-only when singular)
  │
  ├─ DeviceList                                   (new)
  │    └─ DeviceCard * N                          (new)
  │         ├─ node_name, endpoint, paired_at
  │         ├─ capability badges
  │         ├─ WoL toggle (Switch)
  │         ├─ "Discover Capabilities" button
  │         └─ "Remove" button (ConfirmDialog)
  │
  └─ "Add Device" button
       └─ <PeerPairingModal onPaired={refresh} /> (existing — P7c)
```

### File layout

```
components/settings/tabs/
  DevicesTab.tsx              (new — P7b main tab)
  DevicesTab.test.tsx         (new — P7d tests)

components/settings/devices/  (new directory)
  EntityIdentityCard.tsx      (new)
  DeviceCard.tsx              (new)
  DeviceCard.test.tsx         (new)

lib/
  peerApi.ts                  (extend — add device API functions)
  deviceApi.ts                (new — or extend peerApi, see design question below)
```

---

## 5. Design decisions to review

### Q1: New `deviceApi.ts` or extend `peerApi.ts`?

`peerApi.ts` already has pairing, fleet, and compute-peer functions. The devices API is a thin alias layer over peers. Two options:

- **Option A: Extend `peerApi.ts`** — add `listDevices()`, `setEntityMode()`, etc. to the existing file. Pro: one file for all peer/device API calls. Con: the file grows large.
- **Option B: New `deviceApi.ts`** — separate file for the devices surface. Pro: clean separation. Con: two files for closely related APIs.

**Recommendation:** Option A (extend `peerApi.ts`). The devices API IS the peers API with different naming. Splitting them creates import confusion.

### Q2: Should the entity mode toggle be a Switch or a Radio group?

The backend accepts `"singular"` or `"independent"`. A Switch implies boolean on/off. A Radio group makes both states explicit.

**Recommendation:** Switch with clear labels. "Singular entity" = on, "Independent" = off. The singular mode is the default/recommended state, so "on" = default is the right polarity. Include a helper text explaining what each state means.

### Q3: Where does the "Add Device" button live?

Three options:
- **A:** Inside the Devices tab, above the device list (like a standard list+add pattern).
- **B:** In the NavRail as a separate action.
- **C:** In the shell header (like InstanceSwitch currently does).

**Recommendation:** Option A. The Devices tab is the management surface. The InstanceSwitch in the shell header is for quick-switching between already-paired instances; the Devices tab is for pairing and configuration. The existing `PeerPairingModal` is reused as-is.

### Q4: Should the Devices tab be visible on all variants?

Currently the AI tab swaps `ModelSettings` for `ComputePeerCard` based on variant. Should the Devices tab be variant-gated?

**Recommendation:** No. Every variant can have paired devices. A lone install with no peers shows an empty state with "Add your first device" CTA. The tab is always visible.

### Q5: How to handle the canonical URL input in singular mode?

When toggling to singular mode, the backend needs `base_url` (or explicit `memory_url` + `thread_url`). The UI should:
- Default to `base_url` input (simplest path: `http://n150.lan:8001`)
- Show an "Advanced" collapsible for explicit per-service URLs
- Derive `memory_url` and `thread_url` from `base_url` automatically

**Recommendation:** Simple `base_url` input with an "Advanced" disclosure for explicit overrides. The backend already handles this (`EntityModeRequest` accepts `base_url` and derives the paths).

### Q6: WoL toggle UX — inline or modal?

WoL requires a MAC address to enable. The toggle should:
- Show current state (enabled/disabled)
- If enabling and no MAC is set, prompt for MAC + optional broadcast
- If enabling and MAC is already set, just toggle

**Recommendation:** Inline expandable section under the Switch. When enabling without a MAC, an Input appears (not a modal — this is a small form, not a multi-step flow). The `WolToggleRequest` model accepts `mac` and `broadcast` alongside `enabled`.

### Q7: Capability discovery — button or automatic?

The `POST /api/devices/{node_id}/discover` endpoint probes the device's MCP server. This is a network call that can fail (device offline, no MCP server, no token).

**Recommendation:** Explicit "Discover Capabilities" button per device card. Shows loading state, then result: "Found 12 tools -> [gpu_llm, mcp, terminal]" or "Device unreachable" or "No token configured". Auto-discovery on page load would be slow and fail noisily for offline devices.

---

## 6. State management

The Devices tab is a self-contained component with local state — no global context needed. State:

```typescript
interface DevicesTabState {
  loading: boolean
  entityMode: 'singular' | 'independent'
  bodyName: string
  canonicalMemoryUrl: string
  canonicalThreadUrl: string
  devices: DeviceInfo[]
  showPairingModal: boolean
  savingEntityMode: boolean
  savingBodyName: boolean
  toast: { open: boolean; message: string; variant: 'success' | 'error' | 'info' }
}
```

Refresh strategy: `loadDevices()` on mount, after pairing modal closes (`onPaired` callback), after any mutation (entity mode, body name, WoL, remove, discover).

---

## 7. Error handling

- **Network errors:** Show toast with error message. The list state is preserved (don't clear devices on a failed mutation).
- **Device offline for discovery:** The backend returns `{"status": "unreachable", ...}` — render as info, not error. Discovery outcomes are results, not errors.
- **Pairing failure:** The `PeerPairingModal` already handles this internally (error state in the DiscoveredPeerCard and ManualPairingForm).
- **Entity mode toggle failure:** Show toast. The switch reverts to its previous state (optimistic update with rollback).

---

## 8. Accessibility

- All interactive elements are keyboard-navigable (Radix primitives handle this).
- Switch has `aria-label` describing what it toggles.
- Device cards are in a semantic list (`<ul>` / `<li>` or ARIA `role="list"`).
- Toast announcements use `aria-live="polite"` (already handled by the `Toast` component).
- Capability badges have `title` attributes with full descriptions.
- Confirm dialog for device removal includes the device name.

---

## 9. Test plan (P7d)

### Frontend component tests (Vitest + Testing Library)

**`DevicesTab.test.tsx`:**
- Renders empty state with "Add Device" CTA when no devices
- Renders device list with correct fields
- Entity mode toggle: switches to singular, sends `PUT /api/devices/entity-mode` with `base_url`
- Entity mode toggle: switches to independent, sends PUT with empty URLs
- Body name edit: sends `PUT /api/devices/body-name`
- "Add Device" button opens `PeerPairingModal`
- `onPaired` callback triggers list refresh
- Error state: failed fetch shows toast

**`DeviceCard.test.tsx`:**
- Renders device info (name, endpoint, capabilities, paired_at)
- WoL toggle: enabling without MAC shows MAC input
- WoL toggle: enabling with existing MAC sends PUT directly
- "Discover Capabilities" button: loading state, success with capabilities, unreachable state
- "Remove" button: shows confirm dialog, confirms sends DELETE
- Revoked devices show a "revoked" badge and disable interactive controls

### Backend tests (already shipped — P7a, 20 tests in `test_device_routes.py`)

No new backend tests needed unless the frontend discovers a contract gap.

---

## 10. What we are NOT building

- **No new pairing flow.** The existing `PeerPairingModal` is reused. The manual pairing TODO (`TODO(federation-9.1)`) in `ManualPairingForm` is a pre-existing gap — it's not part of G12.
- **No fleet cockpit.** The `NodeFleetCockpit` is a separate fleet management surface. The Devices page is configuration, not live monitoring.
- **No variant gating.** The Devices tab is visible on all variants.
- **No auto-discovery on page load.** Capability discovery is a manual button click.
- **No real-time device status.** The `last_seen` field is a timestamp, not a live presence indicator. Live status is the fleet cockpit's job.

---

## 11. Open questions for review

1. **Tab placement:** Should "Devices" be its own NavRail section (e.g., "Federation" with just one item), or grouped under "Personality" (since entity identity is personality-adjacent)? Or a new top-level section "Devices & Bodies"?

2. **Singular mode onboarding:** When a user toggles to singular mode for the first time, should there be a confirmation dialog explaining the implications ("This device will share memory and conversations with the canonical host")? Or is the helper text sufficient?

3. **Body name UX:** Should body name be a free-text input or a dropdown of suggested values ("desk", "home", "kitchen", "laptop")? Free-text is more flexible; a dropdown is more discoverable.

4. **`peer_token` configuration:** The `PeerConversationStore` and `PeerMemoryBackend` need a bearer token to authenticate to the canonical host. The `being.yml` now has a `peer_token` field. Should the Devices page expose this for manual entry, or should it be automatically populated during the pairing handshake? (Currently the pairing handshake stores the token in `peers.json` as a hash — the raw token is only returned from `/api/peers/verify` and stored in `localStorage` by the frontend. There's a gap: the backend needs the raw token in `being.yml`, but the frontend stores it in `localStorage`. This may need a backend endpoint to persist the peer token to `being.yml` after successful pairing.)

5. **Revoked device display:** Should revoked devices be shown in the list (greyed out with a "revoked" badge) or hidden? The backend returns them with `revoked: true`. Showing them with a "Re-pair" option could be useful; hiding them is cleaner.

---

## 12. Implementation order

1. Extend `peerApi.ts` with device API functions + types
2. Build `EntityIdentityCard` (entity mode + body name)
3. Build `DeviceCard` (device row with WoL, discover, remove)
4. Build `DevicesTab` (composes the above + "Add Device" -> `PeerPairingModal`)
5. Wire into `Settings.tsx` (add tab to `SETTINGS_TABS` + `SETTINGS_SECTIONS`)
6. Write `DevicesTab.test.tsx` and `DeviceCard.test.tsx`
7. Run `npm test` and `npm run build` to verify

---

## 13. Dependencies and blockers

- **P7a (Opus):** DONE — devices API is live and tested.
- **P3a (Opus):** DONE — `PeerConversationStore` is available.
- **P2a (Fable):** NOT DONE — `PeerMemoryBackend` is not yet implemented. This does NOT block the Devices page UI — the entity mode toggle writes `being.yml` config fields that the backend reads. The memory proxying itself is P2c (G2), which is blocked by P2a. The UI can ship before the memory backend is wired.
- **Frontend tooling:** Vitest, React Testing Library, and the existing UI primitives are all in place. No new dependencies needed.

---

## 14. Files to create/modify

| File | Action | Purpose |
|------|--------|---------|
| `lib/peerApi.ts` | Modify | Add device API functions + `DeviceInfo` type |
| `components/settings/tabs/DevicesTab.tsx` | New | Main tab component |
| `components/settings/tabs/DevicesTab.test.tsx` | New | Tab tests |
| `components/settings/devices/EntityIdentityCard.tsx` | New | Entity mode + body name card |
| `components/settings/devices/DeviceCard.tsx` | New | Per-device row card |
| `components/settings/devices/DeviceCard.test.tsx` | New | Device card tests |
| `pages/Settings.tsx` | Modify | Add "devices" tab to `SETTINGS_TABS` + `SETTINGS_SECTIONS` + render `<DevicesTab />` |

**No backend changes.** All API endpoints are already shipped (P7a).

---

## 15. Design Review Feedback & Architecture Resolutions

**Review Status:** **APPROVED WITH MINOR REFINEMENTS**  
**Reviewer:** Architecture & UI Design System Team  
**Date:** 2026-08-31  

The proposed design for G12 (Devices Page & Pairing Flow) is exceptionally well structured and faithfully aligns with the "Singular Entity" product ethos (*devices and bodies, not nodes and peers*). Below are the binding resolutions for the 5 open questions, plus 4 critical design refinements.

---

### 15.1 Binding Decisions on Open Questions

#### Q1: Tab Placement in Settings NavRail
* **Decision:** Place in a dedicated **"Identity & Devices"** section right below "Personality" (or rename "Personality" to "Personality & Identity" housing `being` and `devices`).
* **Rationale:** A paired device in Halbert is not a peripheral sysadmin gadget (like a USB drive under System); it is a physical extension ("body") of the singular being. Placing it directly adjacent to `being` reinforces the core narrative: *One Mind (`being`), Multiple Bodies (`devices`)*.

#### Q2: Singular Mode Onboarding & Confirmation
* **Decision:** **Require a `ConfirmDialog` when toggling from Independent $\rightarrow$ Singular mode.** (Toggling back from Singular $\rightarrow$ Independent does not require confirmation).
* **Rationale:** Switching to Singular mode shifts the source of truth for episodic memories and conversation history to a remote canonical host (`canonical_memory_url`, `canonical_thread_url`). The confirmation dialog must clearly state:
  1. *Shared Consciousness:* Memories and conversation turns will be proxied to the canonical host.
  2. *Offline Resiliency:* If the canonical host becomes unreachable, Halbert operates with local fallbacks.
  3. *Reversible:* You can revert to Independent mode at any time.

#### Q3: Body Name UX
* **Decision:** **Hybrid Input with Quick-Select Suggestion Chips.**
* **Rationale:** Provide a clean text input with preset suggestion pills underneath:
  `[ Workstation ]` `[ Desk ]` `[ Living Room ]` `[ Kitchen ]` `[ Laptop ]` `[ Server Rack ]`
  - Clicking a chip fills the input instantly.
  - Users can type custom names (e.g. `n150-homelab`, `garage-display`).
  - Add client-side validation enforcing lowercase slug format (`^[a-z0-9-_]+$`) so names are URL/routing-safe.

#### Q4: `peer_token` Persistence & Authentication Gap
* **Critical Finding & Resolution:**
  - When the Python backend (`halbert_core`) proxies conversations (`PeerConversationStore`) or memories (`PeerMemoryBackend`) to the canonical host, it requires the raw bearer token in `being.yml`.
  - **Resolution:**
    1. During the pairing flow (`/api/peers/verify`), ensure the returned token is saved to the local host's secure configuration (`being.yml: peer_token`).
    2. In `EntityIdentityCard`, under an **"Advanced Configuration"** collapsible disclosure, provide a masked input for `Bearer Token / Peer Secret` with a toggle to reveal/edit. This allows manual token rotation or out-of-band headless setup without re-running mDNS pairing.

#### Q5: Revoked Device Display
* **Decision:** **Show in a collapsed secondary section: "Revoked / Archived Devices (N)".**
* **Rationale:** Hiding revoked devices completely leads to "ghost record" collisions if a user tries to re-pair a machine with the same hostname. Displaying them with a muted badge (`Revoked`) and two explicit actions:
  - `[ Re-pair ]`: Re-opens `PeerPairingModal` pre-filled with the device's endpoint.
  - `[ Permanently Forget ]`: Deletes the record entirely from `peers.json`.

---

### 15.2 Key UI/UX Specifications for Implementation

```
┌────────────────────────────────────────────────────────────────────────┐
│ Settings > Identity & Devices                                          │
├────────────────────────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ THIS DEVICE IDENTITY                                               │ │
│ │ Body Name:  [ workstation          ]                               │ │
│ │             Suggestions: [Desk] [Living Room] [Kitchen] [Laptop]   │ │
│ │                                                                    │ │
│ │ Entity Mode: (•) Singular Entity    ( ) Independent Node           │ │
│ │              Shares consciousness, memory & conversations with     │ │
│ │              the canonical host.                                   │ │
│ │                                                                    │ │
│ │ Canonical Host Base URL: [ http://n150.lan:8001                  ] │ │
│ │ ▾ Advanced (Explicit Endpoints & Peer Token)                       │ │
│ └────────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ PAIRED BODIES & COMPUTE PROVIDERS (2)          [ + Add Device ]    │ │
│ ├────────────────────────────────────────────────────────────────────┤ │
│ │ [🖥️ Mac Studio]  desk.lan:8000           [Online • 4ms]  [Edit] [⋮] │ │
│ │ Capabilities: [gpu_llm] [mcp: 14 tools] [terminal]                 │ │
│ │ Wake-on-LAN:  (•) Enabled  [MAC: 00:1A:2B:3C:4D:5E]                │ │
│ │ Actions:      [ Discover Capabilities ]       [ Remove Device ]    │ │
│ │────────────────────────────────────────────────────────────────────│ │
│ │ [⚡ N150 Appliance]  n150.lan:8001       [Canonical Host]          │ │
│ │ Capabilities: [canonical_memory] [canonical_threads] [audio]       │ │
│ │ Wake-on-LAN:  ( ) Disabled                                         │ │
│ └────────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│ ▸ Revoked / Archived Devices (1)                                       │
└────────────────────────────────────────────────────────────────────────┘
```

### 15.3 Polish & Engineering Checklist

1. **Empty State Component:**
   - If `devices.length === 0`, render an elegant empty state card explaining the Singular Entity concept with a prominent `[ Add First Device ]` CTA button.
2. **Capability Badge Color Mapping:**
   - `gpu_llm`: Purple/Violet (`text-purple-400 bg-purple-500/10 border-purple-500/30`)
   - `mcp`: Blue (`text-blue-400 bg-blue-500/10 border-blue-500/30`) — display tool count when available (`mcp (14 tools)`)
   - `terminal`: Amber (`text-amber-400 bg-amber-500/10 border-amber-500/30`)
   - `canonical_memory` / `canonical_threads`: Emerald (`text-emerald-400 bg-emerald-500/10 border-emerald-500/30`)
3. **Optimistic UI with Automatic Rollback:**
   - All toggle switches (`entity_mode`, `wol_enabled`) must update UI state optimistically, but immediately roll back to previous state and emit an error `Toast` if the backend API call rejects.
4. **WoL Expandable Sub-form:**
   - Toggling WoL to `enabled` when `wol_mac` is null must smoothly expand an inline MAC input (`00:00:00:00:00:00` format) and optional broadcast address (`255.255.255.255` default) with validation before firing the PUT request.

---
